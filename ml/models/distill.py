"""P12b — distill CT-FM features into the PointNet++ CT encoder (AUP-002).

Stage A: cache a 512-d CT-FM teacher embedding per train-split volume (offline).
Stage B: train PointNet++ so its (L2-normalized) 512-d embedding matches the
teacher's (cosine distillation), optionally combined with the 18-dim multi-label
BCE (reusing P12a supervision). Exports the CT-encoder weights for the retrieval
model (`train.py --init-ct-encoder`).

Leakage guard: train split only; a 15% held-out slice is the distill-val set.
Compliance: CT-FM (MIT) is not CT-CLIP, and we match its *features* — we never
load its weights into PointNet++.

Run:  python -m ml.models.distill [--epochs N] [--out runs/p12b] [--resume]
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .ctfm_teacher import cache_teacher_feature, teacher_dim
from .data import CACHE, load_labels, select_subset, volume_path
from .train_config import DEFAULT, TrainConfig

RUN_DIR = Path("runs/p12b")
VAL_FRACTION = 0.15


def cache_all_teacher_features(vols: list[str]) -> None:
    """Stage A: extract + cache CT-FM features for every volume (idempotent)."""
    n = len(vols)
    for i, vol in enumerate(vols, 1):
        cache_teacher_feature(vol, volume_path(vol))
        if i % 10 == 0 or i == n:
            (Path("data/ct_rate") / "ctfm_progress.json").write_text(
                json.dumps({"cached": i, "total": n}), encoding="utf-8")
            print(f"[teacher] {i}/{n}", flush=True)


class DistillDataset:
    """(points, teacher_feat, label) for a list of volumes."""

    def __init__(self, vols, labels, n_labels, teacher_cache):
        self.vols = vols
        self.labels = labels
        self.n_labels = n_labels
        self.teacher_cache = teacher_cache

    def __len__(self):
        return len(self.vols)

    def __getitem__(self, i):
        vol = self.vols[i]
        points = np.load(CACHE / f"{vol}.npz")["points"].astype(np.float32)
        tfeat = np.load(self.teacher_cache / f"{vol}.npy").astype(np.float32)
        label = self.labels.get(vol, np.zeros(self.n_labels, dtype=np.float32))
        return points, tfeat, label


def collate(items):
    pts = torch.from_numpy(np.stack([it[0] for it in items])).float()
    tfeat = torch.from_numpy(np.stack([it[1] for it in items])).float()
    labels = torch.from_numpy(np.stack([it[2] for it in items])).float()
    return pts, tfeat, labels


class CtDistillModel(nn.Module):
    """PointNet++ encoder + optional multi-label head (student)."""

    def __init__(self, encoder, embed_dim, n_labels):
        super().__init__()
        self.encoder = encoder
        self.head = nn.Linear(embed_dim, n_labels)

    def forward(self, points):
        emb = self.encoder(points)          # already L2-normalized, (B, embed_dim)
        return emb, self.head(emb)


def build_student(config):
    from .pointnet2 import PointNet2Encoder
    return CtDistillModel(PointNet2Encoder(out_dim=config.embed_dim),
                          config.embed_dim, config.n_labels)


def build_distill_datasets(config: TrainConfig):
    from .ctfm_teacher import CACHE_DIR as TEACHER_CACHE
    subset = select_subset(config)
    train_vols = list(subset["train"])
    labels, _ = load_labels()
    n_hold = max(1, int(len(train_vols) * VAL_FRACTION))
    pv, pt = train_vols[-n_hold:], train_vols[:-n_hold]

    def make(v):
        return DistillDataset(v, labels, config.n_labels, TEACHER_CACHE)
    return make(pt), make(pv), {"distill_train": len(pt), "distill_val": len(pv)}


def _distill_loss(emb, tfeat, logits, labels, aux_weight, bce):
    # emb is L2-normalized; match direction of the teacher embedding (cosine).
    tnorm = torch.nn.functional.normalize(tfeat, dim=-1)
    distill = (1.0 - (emb * tnorm).sum(dim=-1)).mean()
    aux = bce(logits, labels)
    return distill + aux_weight * aux, float(distill.detach()), float(aux.detach())


@torch.no_grad()
def _val_distill(model, loader, device, amp, aux_weight, bce):
    model.eval()
    tot, n = 0.0, 0
    for pts, tfeat, labels in loader:
        pts, tfeat, labels = pts.to(device), tfeat.to(device), labels.to(device)
        with torch.autocast(device_type="cuda", enabled=amp and device == "cuda"):
            emb, logits = model(pts)
            loss, _, _ = _distill_loss(emb, tfeat, logits, labels, aux_weight, bce)
        tot += float(loss) * len(pts)
        n += len(pts)
    return tot / max(n, 1)


def distill(config: TrainConfig, out_dir: Path, *, allow_cpu: bool = False,
            resume: bool = False, skip_extract: bool = False) -> dict:
    device = config.device
    if device == "cuda" and not torch.cuda.is_available():
        if not allow_cpu:
            raise SystemExit("CUDA requested but unavailable; pass --allow-cpu to override.")
        device = "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    subset = select_subset(config)
    if not skip_extract:
        cache_all_teacher_features(list(subset["train"]))  # Stage A

    ds_tr, ds_val, counts = build_distill_datasets(config)
    tr = DataLoader(ds_tr, batch_size=config.batch_size, shuffle=True,
                    num_workers=config.num_workers, collate_fn=collate, drop_last=True)
    va = DataLoader(ds_val, batch_size=config.batch_size, shuffle=False,
                    num_workers=config.num_workers, collate_fn=collate)

    model = build_student(config).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
    use_amp = config.amp and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    bce = nn.BCEWithLogitsLoss()

    enc_path, last_path = out_dir / "encoder.pt", out_dir / "last.pt"
    best_val, best_epoch, start_epoch = float("inf"), -1, 0
    if resume and last_path.is_file():
        ck = torch.load(last_path, map_location=device)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        scaler.load_state_dict(ck["scaler"])
        start_epoch, best_val, best_epoch = ck["epoch"] + 1, ck["best_val"], ck["best_epoch"]
        print(f"[resume] epoch {start_epoch} (best e{best_epoch} val={best_val:.4f})", flush=True)

    log_fh = (out_dir / "distill_log.jsonl").open("a" if start_epoch else "w", encoding="utf-8")
    for epoch in range(start_epoch, config.epochs):
        model.train()
        t0 = time.time()
        distill_losses, aux_losses = [], []
        for pts, tfeat, labels in tr:
            pts, tfeat, labels = pts.to(device), tfeat.to(device), labels.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=use_amp):
                emb, logits = model(pts)
                loss, d, a = _distill_loss(emb, tfeat, logits, labels, config.aux_weight, bce)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            scaler.step(opt)
            scaler.update()
            distill_losses.append(d)
            aux_losses.append(a)
        val = _val_distill(model, va, device, use_amp, config.aux_weight, bce)
        rec = {"epoch": epoch, "train_distill": float(np.mean(distill_losses)),
               "train_aux": float(np.mean(aux_losses)), "val_loss": val,
               "sec": round(time.time() - t0, 1)}
        log_fh.write(json.dumps(rec) + "\n")
        log_fh.flush()
        print(f"[d{epoch:02d}] distill={rec['train_distill']:.4f} aux={rec['train_aux']:.4f} "
              f"val={val:.4f} ({rec['sec']}s)", flush=True)
        if val < best_val:
            best_val = val
            best_epoch = epoch
            torch.save(model.encoder.state_dict(), enc_path)
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                    "scaler": scaler.state_dict(), "epoch": epoch,
                    "best_val": best_val, "best_epoch": best_epoch}, last_path)
    log_fh.close()

    manifest = {
        "stage": "P12b CT-FM distillation (AUP-002)",
        "teacher": "surajpaib/CT-FM-SegResNet (MIT); features distilled, weights not loaded",
        "config": config.to_dict(),
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else platform.processor(),
        "teacher_dim": teacher_dim(),
        "counts": counts,
        "best_epoch": best_epoch,
        "best_val_loss": best_val,
        "encoder_weights": str(enc_path),
    }
    (out_dir / "distill_metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nBEST epoch {best_epoch} val={best_val:.4f} -> {enc_path}", flush=True)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="P12b CT-FM distillation pretraining.")
    ap.add_argument("--out", type=str, default=str(RUN_DIR))
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-extract", action="store_true",
                    help="assume the teacher feature cache is already built")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--n-train", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    args = ap.parse_args()
    overrides = {}
    for cli, field in [("epochs", "epochs"), ("n_train", "n_train"),
                       ("batch", "batch_size"), ("lr", "lr")]:
        v = getattr(args, cli)
        if v is not None:
            overrides[field] = v
    config = TrainConfig(**{**DEFAULT.to_dict(), **overrides})
    distill(config, Path(args.out), allow_cpu=args.allow_cpu, resume=args.resume,
            skip_extract=args.skip_extract)


if __name__ == "__main__":
    main()
