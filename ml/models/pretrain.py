"""P12a — supervised pretraining of the CT encoder (AUP-001).

Gives the from-scratch PointNet++ CT encoder a warm start by training it (plus a
linear head) on the 18-dim CT-RATE multi-abnormality labels, then exporting the
encoder weights for the P12 retrieval model to initialize from
(`train.py --init-ct-encoder`).

Leakage guard: uses the **train split only**; a held-out slice of the train split
(`pretrain-val`) is used for model selection so the retrieval val/test sets are
never touched. No external weights are loaded (CT-CLIP policy honored).

Run:  python -m ml.models.pretrain [--epochs N] [--out runs/p12a] [--resume]
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

from .data import CACHE, load_labels, select_subset
from .train_config import DEFAULT, TrainConfig

RUN_DIR = Path("runs/p12a")
PRETRAIN_VAL_FRACTION = 0.15


class PointLabelDataset:
    """(points, 18-dim label) for a list of volumes — no reports/tokenizer."""

    def __init__(self, vols: list[str], labels: dict[str, np.ndarray], n_labels: int):
        self.vols = vols
        self.labels = labels
        self.n_labels = n_labels

    def __len__(self) -> int:
        return len(self.vols)

    def __getitem__(self, i: int):
        vol = self.vols[i]
        points = np.load(CACHE / f"{vol}.npz")["points"].astype(np.float32)
        label = self.labels.get(vol, np.zeros(self.n_labels, dtype=np.float32))
        return points, label


def collate(items):
    pts = torch.from_numpy(np.stack([it[0] for it in items])).float()
    labels = torch.from_numpy(np.stack([it[1] for it in items])).float()
    return pts, labels


class CtClassifier(nn.Module):
    """PointNet++ encoder + linear multi-label head (the pretraining model)."""

    def __init__(self, encoder: nn.Module, embed_dim: int, n_labels: int):
        super().__init__()
        self.encoder = encoder
        self.head = nn.Linear(embed_dim, n_labels)

    def forward(self, points: torch.Tensor) -> torch.Tensor:
        return self.head(self.encoder(points))


def build_classifier(config: TrainConfig) -> CtClassifier:
    from .pointnet2 import PointNet2Encoder
    return CtClassifier(PointNet2Encoder(out_dim=config.embed_dim),
                        config.embed_dim, config.n_labels)


def build_pretrain_datasets(config: TrainConfig):
    """Split the train split into pretrain-train / pretrain-val (no val/test leak)."""
    subset = select_subset(config)
    train_vols = list(subset["train"])
    labels, _cols = load_labels()
    n_hold = max(1, int(len(train_vols) * PRETRAIN_VAL_FRACTION))
    pv = train_vols[-n_hold:]
    pt = train_vols[:-n_hold]
    return (PointLabelDataset(pt, labels, config.n_labels),
            PointLabelDataset(pv, labels, config.n_labels),
            {"pretrain_train": len(pt), "pretrain_val": len(pv)})


@torch.no_grad()
def _val_loss(model: CtClassifier, loader: DataLoader, device: str, amp: bool) -> float:
    model.eval()
    crit = nn.BCEWithLogitsLoss()
    tot, n = 0.0, 0
    for pts, labels in loader:
        pts, labels = pts.to(device), labels.to(device)
        with torch.autocast(device_type="cuda", enabled=amp and device == "cuda"):
            loss = crit(model(pts), labels)
        tot += float(loss) * len(pts)
        n += len(pts)
    return tot / max(n, 1)


def pretrain(config: TrainConfig, out_dir: Path, *, allow_cpu: bool = False,
             resume: bool = False) -> dict:
    device = config.device
    if device == "cuda" and not torch.cuda.is_available():
        if not allow_cpu:
            raise SystemExit("CUDA requested but unavailable; pass --allow-cpu to override.")
        device = "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    ds_tr, ds_val, counts = build_pretrain_datasets(config)
    tr = DataLoader(ds_tr, batch_size=config.batch_size, shuffle=True,
                    num_workers=config.num_workers, collate_fn=collate,
                    drop_last=True)  # BatchNorm needs >1 sample per (training) batch
    va = DataLoader(ds_val, batch_size=config.batch_size, shuffle=False,
                    num_workers=config.num_workers, collate_fn=collate)

    model = build_classifier(config).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
    use_amp = config.amp and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    crit = nn.BCEWithLogitsLoss()

    enc_path = out_dir / "encoder.pt"
    last_path = out_dir / "last.pt"
    best_val = float("inf")
    best_epoch = -1
    start_epoch = 0
    if resume and last_path.is_file():
        ck = torch.load(last_path, map_location=device)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        scaler.load_state_dict(ck["scaler"])
        start_epoch = ck["epoch"] + 1
        best_val = ck["best_val"]
        best_epoch = ck["best_epoch"]
        print(f"[resume] epoch {start_epoch} (best e{best_epoch} val={best_val:.4f})", flush=True)

    log_fh = (out_dir / "pretrain_log.jsonl").open("a" if start_epoch else "w", encoding="utf-8")
    for epoch in range(start_epoch, config.epochs):
        model.train()
        t0 = time.time()
        losses = []
        for pts, labels in tr:
            pts, labels = pts.to(device), labels.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=use_amp):
                loss = crit(model(pts), labels)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            scaler.step(opt)
            scaler.update()
            losses.append(float(loss.detach()))
        val = _val_loss(model, va, device, use_amp)
        rec = {"epoch": epoch, "train_bce": float(np.mean(losses)), "val_bce": val,
               "sec": round(time.time() - t0, 1)}
        log_fh.write(json.dumps(rec) + "\n")
        log_fh.flush()
        print(f"[p{epoch:02d}] train_bce={rec['train_bce']:.4f} val_bce={val:.4f} "
              f"({rec['sec']}s)", flush=True)
        if val < best_val:
            best_val = val
            best_epoch = epoch
            torch.save(model.encoder.state_dict(), enc_path)  # CT-encoder weights only
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                    "scaler": scaler.state_dict(), "epoch": epoch,
                    "best_val": best_val, "best_epoch": best_epoch}, last_path)
    log_fh.close()

    manifest = {
        "stage": "P12a supervised CT-encoder pretraining (AUP-001)",
        "config": config.to_dict(),
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else platform.processor(),
        "torch": torch.__version__,
        "counts": counts,
        "best_epoch": best_epoch,
        "best_val_bce": best_val,
        "encoder_weights": str(enc_path),
    }
    (out_dir / "pretrain_metrics.json").write_text(json.dumps(manifest, indent=2),
                                                   encoding="utf-8")
    print(f"\nBEST epoch {best_epoch} val_bce={best_val:.4f} -> {enc_path}", flush=True)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="P12a supervised CT-encoder pretraining.")
    ap.add_argument("--out", type=str, default=str(RUN_DIR))
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--n-train", type=int, default=None)
    ap.add_argument("--points", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    args = ap.parse_args()
    overrides = {}
    for cli, field in [("epochs", "epochs"), ("n_train", "n_train"),
                       ("points", "n_points"), ("batch", "batch_size"), ("lr", "lr")]:
        v = getattr(args, cli)
        if v is not None:
            overrides[field] = v
    config = TrainConfig(**{**DEFAULT.to_dict(), **overrides})
    pretrain(config, Path(args.out), allow_cpu=args.allow_cpu, resume=args.resume)


if __name__ == "__main__":
    main()
