"""P12 retrieval training loop (local RTX 4050, AMP).

Trains the PointNet++/BioClinicalBERT CLIP model on a CT-RATE subset, selects
the checkpoint with the best validation CT->text Recall@1, then reports held-out
test metrics. Emits a reproducible run manifest, metrics.json and a model card.

Run:  python -m ml.models.train  [--epochs N] [--out runs/p12]
Requires a working CUDA torch (see ml/requirements-model.txt). CPU is refused
unless --allow-cpu is passed, so a GPU run is never silently downgraded.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader

from .data import build_datasets
from .metrics import evaluate_bidirectional
from .retrieval import Batch, RetrievalModel
from .train_config import DEFAULT, TrainConfig

RUN_DIR = Path("runs/p12")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def collate(items) -> Batch:
    pts = torch.from_numpy(np.stack([it[0] for it in items])).float()
    ids = torch.from_numpy(np.stack([it[1] for it in items])).long()
    mask = torch.from_numpy(np.stack([it[2] for it in items])).long()
    labels = torch.from_numpy(np.stack([it[3] for it in items])).float()
    return Batch(pts, ids, mask, labels)


def to_device(batch: Batch, device: str) -> Batch:
    return Batch(batch.points.to(device), batch.input_ids.to(device),
                 batch.attention_mask.to(device), batch.labels.to(device))


def build_model(config: TrainConfig) -> RetrievalModel:
    from .pointnet2 import PointNet2Encoder
    from .text_encoder import build_bioclinicalbert
    ct = PointNet2Encoder(out_dim=config.embed_dim)
    txt = build_bioclinicalbert(out_dim=config.embed_dim)
    if config.freeze_text_backbone:
        txt.bert.eval()
        for p in txt.bert.parameters():
            p.requires_grad_(False)  # projection stays trainable
    return RetrievalModel(ct, txt, n_labels=config.n_labels,
                          out_dim=config.embed_dim, aux_weight=config.aux_weight)


@torch.no_grad()
def encode_split(model: RetrievalModel, loader: DataLoader, device: str,
                 amp: bool) -> dict[str, float]:
    model.eval()
    cts: list[Tensor] = []
    txts: list[Tensor] = []
    for batch in loader:
        batch = to_device(batch, device)
        with torch.autocast(device_type="cuda", enabled=amp and device == "cuda"):
            ct, txt = model.encode(batch)
        cts.append(ct.float().cpu())
        txts.append(txt.float().cpu())
    ct_all = torch.cat(cts).numpy()
    txt_all = torch.cat(txts).numpy()
    return evaluate_bidirectional(ct_all, txt_all)


def train(config: TrainConfig, out_dir: Path, *, allow_cpu: bool = False,
          resume: bool = False) -> dict:
    device = config.device
    if device == "cuda" and not torch.cuda.is_available():
        if not allow_cpu:
            raise SystemExit(
                "CUDA requested but torch.cuda.is_available() is False. "
                "Install a CUDA torch build or pass --allow-cpu to override."
            )
        device = "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    set_seed(config.seed)

    datasets, subset = build_datasets(config)
    train_loader = DataLoader(datasets["train"], batch_size=config.batch_size,
                              shuffle=True, num_workers=config.num_workers, collate_fn=collate)
    val_loader = DataLoader(datasets["val"], batch_size=config.batch_size,
                            shuffle=False, num_workers=config.num_workers, collate_fn=collate)
    test_loader = DataLoader(datasets["test"], batch_size=config.batch_size,
                             shuffle=False, num_workers=config.num_workers, collate_fn=collate)

    model = build_model(config).to(device)
    trainable = [p for p in model.parameters() if p.requires_grad]
    n_train_p = sum(p.numel() for p in trainable)
    n_total_p = sum(p.numel() for p in model.parameters())
    print(f"trainable params: {n_train_p:,} / {n_total_p:,}", flush=True)
    opt = torch.optim.AdamW(trainable, lr=config.lr, weight_decay=config.weight_decay)
    use_amp = config.amp and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    best_r1 = -1.0
    best_epoch = -1
    start_epoch = 0
    ckpt_path = out_dir / "best.pt"
    last_path = out_dir / "last.pt"

    # Resume from the last full checkpoint (survives Colab/Kaggle disconnects).
    if resume and last_path.is_file():
        ck = torch.load(last_path, map_location=device)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        scaler.load_state_dict(ck["scaler"])
        start_epoch = ck["epoch"] + 1
        best_r1 = ck["best_r1"]
        best_epoch = ck["best_epoch"]
        print(f"[resume] from epoch {start_epoch} (best so far e{best_epoch} "
              f"score={best_r1:.3f})", flush=True)

    log_path = out_dir / "train_log.jsonl"
    log_fh = log_path.open("a" if start_epoch else "w", encoding="utf-8")

    for epoch in range(start_epoch, config.epochs):
        model.train()
        if config.freeze_text_backbone:
            model.text_encoder.bert.eval()  # type: ignore[union-attr]  # frozen backbone deterministic
        t0 = time.time()
        losses = []
        for batch in train_loader:
            batch = to_device(batch, device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=use_amp):
                loss, stats = model(batch)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            scaler.step(opt)
            scaler.update()
            losses.append(stats)
        val = encode_split(model, val_loader, device, use_amp)
        rec = {
            "epoch": epoch,
            "train_loss": float(np.mean([s["loss"] for s in losses])),
            "train_contrastive": float(np.mean([s["contrastive"] for s in losses])),
            "train_aux": float(np.mean([s["aux"] for s in losses])),
            "val_ct2txt_recall@1": val["ct2txt_recall@1"],
            "val_txt2ct_recall@1": val["txt2ct_recall@1"],
            "val_ct2txt_map": val["ct2txt_map"],
            "sec": round(time.time() - t0, 1),
        }
        log_fh.write(json.dumps(rec) + "\n")
        log_fh.flush()
        print(f"[e{epoch:02d}] loss={rec['train_loss']:.3f} "
              f"val R@1(ct->txt)={val['ct2txt_recall@1']:.3f} ({rec['sec']}s)", flush=True)
        score = (val["ct2txt_recall@1"] + val["txt2ct_recall@1"]) / 2
        if score > best_r1:
            best_r1 = score
            best_epoch = epoch
            torch.save({"model": model.state_dict(), "config": config.to_dict(),
                        "epoch": epoch, "val": val}, ckpt_path)
        # Full resumable checkpoint after every epoch.
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                    "scaler": scaler.state_dict(), "epoch": epoch,
                    "best_r1": best_r1, "best_epoch": best_epoch,
                    "config": config.to_dict()}, last_path)
    log_fh.close()

    # Final held-out test with the best checkpoint.
    state = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(state["model"])
    test = encode_split(model, test_loader, device, use_amp)

    gpu = torch.cuda.get_device_name(0) if device == "cuda" else platform.processor()
    scope = (f"{len(subset['train'])} training volumes, {config.n_points} points, "
             f"on {gpu}"
             + (", text backbone frozen." if config.freeze_text_backbone
                else ", full fine-tune."))
    manifest = {
        "config": config.to_dict(),
        "device": device,
        "gpu": gpu,
        "scope": scope,
        "torch": torch.__version__,
        "counts": {k: len(v) for k, v in subset.items()},
        "best_epoch": best_epoch,
        "best_val_score": best_r1,
        "val_at_best": state["val"],
        "test": test,
        "subset_volumes": subset,
    }
    (out_dir / "metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_model_card(out_dir, manifest)
    print(f"\nBEST epoch {best_epoch}  test R@1(ct->txt)={test['ct2txt_recall@1']:.3f} "
          f"R@5={test['ct2txt_recall@5']:.3f} mAP={test['ct2txt_map']:.3f}", flush=True)
    return manifest


def _row(name: str, d: dict, pre: str) -> str:
    def g(k: str) -> str:
        return f"{d[f'{pre}_{k}']:.3f}"
    return (f"| {name} | {g('recall@1')} | {g('recall@5')} | {g('recall@10')} "
            f"| {g('map')} | {g('ndcg')} |")


def _write_model_card(out_dir: Path, m: dict) -> None:
    c = m["config"]
    t = m["test"]
    counts = m["counts"]
    ct_row = _row("CT -> text", t, "ct2txt")
    txt_row = _row("text -> CT", t, "txt2ct")
    rand = 1.0 / counts["test"]
    card = f"""# Model Card — 3D Medical CLIP retrieval (P12)

**Task:** bidirectional CT volume <-> radiology report retrieval (CT-RATE chest CT).

## Architecture
- CT encoder: PointNet++ set-abstraction over {c['n_points']} pts -> {c['embed_dim']}-d.
- Text encoder: Bio_ClinicalBERT -> {c['embed_dim']}-d projection.
- Objective: symmetric CLIP InfoNCE + multi-label auxiliary (weight {c['aux_weight']}).

## Training data
- Split: train {counts['train']} / val {counts['val']} / test {counts['test']} volumes,
  patient-level CT-RATE split (seed {c['seed']}), zero patient leakage.
- Point count {c['n_points']} (spec full-scale target 32768).
- **Scope:** {m.get('scope', 'see run manifest')}

## Run
- Device: {m['device']} ({m['gpu']}), torch {m['torch']}, AMP={c['amp']}.
- Epochs {c['epochs']}, batch {c['batch_size']}, lr {c['lr']}, wd {c['weight_decay']},
  grad_clip {c['grad_clip']}.
- Model selection: best mean(val CT->txt, txt->CT Recall@1); best epoch {m['best_epoch']}.

## Held-out test metrics
| direction | R@1 | R@5 | R@10 | mAP | nDCG |
|-----------|-----|-----|------|-----|------|
{ct_row}
{txt_row}

Random baseline for R@1 at this test size is ~{rand:.3f}.

## Reproducibility
- Config frozen in `ml/models/train_config.py`; run manifest in `metrics.json`.
- Deterministic preprocessing (seed {c['seed']}) via the P9 pipeline;
  point-cloud cache under `data/ct_rate/pointcloud_cache/`.
"""
    (out_dir / "model_card.md").write_text(card, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="P12 CT<->report retrieval training.")
    ap.add_argument("--out", type=str, default=str(RUN_DIR))
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="continue from <out>/last.pt (survives Colab disconnects)")
    # Scaling knobs for cloud training (default = local subset in TrainConfig).
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--n-train", type=int, default=None)
    ap.add_argument("--n-val", type=int, default=None)
    ap.add_argument("--n-test", type=int, default=None)
    ap.add_argument("--points", type=int, default=None, help="points per volume")
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--no-freeze", action="store_true",
                    help="full fine-tune the text backbone (needs lots of data)")
    args = ap.parse_args()

    overrides = {}
    for cli, field in [("epochs", "epochs"), ("n_train", "n_train"), ("n_val", "n_val"),
                       ("n_test", "n_test"), ("points", "n_points"), ("batch", "batch_size"),
                       ("lr", "lr")]:
        val = getattr(args, cli)
        if val is not None:
            overrides[field] = val
    if args.no_freeze:
        overrides["freeze_text_backbone"] = False
    config = TrainConfig(**{**DEFAULT.to_dict(), **overrides})
    train(config, Path(args.out), allow_cpu=args.allow_cpu, resume=args.resume)


if __name__ == "__main__":
    main()
