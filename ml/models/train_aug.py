"""P12 experiment — augmented retrieval training (squeeze more from 556 pairs).

Three training-methodology levers on top of the P12a-pretrained encoder (no
architecture change):
  1. stochastic point-cloud augmentation (train only) — fights the immediate
     overfitting seen in P12 (best val epoch was 1);
  2. a large FIFO negative queue — hundreds of contrastive negatives without a
     large batch (fits 6 GB);
  3. label multi-positive InfoNCE — items sharing the exact 18-dim abnormality
     label (non-empty) share positive mass, turning sparse pairs into denser
     supervision.

Run:  python -m ml.models.train_aug --init-ct-encoder runs/p12a/encoder.pt --out runs/p12_aug
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader

from .data import build_datasets
from .losses import multilabel_aux_loss
from .train import build_model, collate, encode_split, to_device
from .train_config import DEFAULT, TrainConfig

RUN_DIR = Path("runs/p12_aug")


class EmbQueue:
    """FIFO ring buffer of detached (embedding, label) pairs for extra negatives."""

    def __init__(self, size: int, dim: int, n_labels: int, device: str):
        self.size = size
        self.emb = torch.zeros(size, dim, device=device)
        self.lab = torch.zeros(size, n_labels, device=device)
        self.ptr = 0
        self.full = False

    def add(self, emb: Tensor, lab: Tensor) -> None:
        b = emb.shape[0]
        idx = (torch.arange(b, device=emb.device) + self.ptr) % self.size
        self.emb[idx] = emb.detach()
        self.lab[idx] = lab.detach()
        self.ptr = int((self.ptr + b) % self.size)
        self.full = self.full or self.ptr < b

    def get(self):
        n = self.size if self.full else self.ptr
        return self.emb[:n], self.lab[:n]


def _multipos_loss(anchor: Tensor, cand: Tensor, cand_lab: Tensor, anchor_lab: Tensor,
                   scale: Tensor, beta: float) -> Tensor:
    """InfoNCE where the first B candidates align with the batch (diagonal is the
    true pair) and same-exact-label (non-empty) candidates share positive mass."""
    b = anchor.shape[0]
    logits = scale * anchor @ cand.t()                 # (B, M)
    target = torch.zeros_like(logits)
    target[torch.arange(b), torch.arange(b)] = 1.0     # true pair
    shared = anchor_lab @ cand_lab.t()                 # (B, M) count of shared labels
    a_sum = anchor_lab.sum(1, keepdim=True)            # (B, 1)
    c_sum = cand_lab.sum(1, keepdim=True).t()          # (1, M)
    same = (shared == a_sum) & (shared == c_sum) & (a_sum > 0)  # exact, non-empty match
    target = target + beta * same.float()
    target = target / target.sum(1, keepdim=True).clamp_min(1e-6)
    return -(target * torch.log_softmax(logits, dim=1)).sum(1).mean()


def train_aug(config: TrainConfig, out_dir: Path, *, init_ct_encoder: Path | None,
              queue_size: int = 512, beta: float = 0.3, allow_cpu: bool = False) -> dict:
    device = config.device
    if device == "cuda" and not torch.cuda.is_available():
        if not allow_cpu:
            raise SystemExit("CUDA requested but unavailable; pass --allow-cpu.")
        device = "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    datasets, subset = build_datasets(config, augment_train=True)
    loaders = {k: DataLoader(datasets[k], batch_size=config.batch_size,
                             shuffle=(k == "train"), num_workers=config.num_workers,
                             collate_fn=collate, drop_last=(k == "train"))
               for k in datasets}

    model = build_model(config).to(device)
    if init_ct_encoder is not None:
        model.ct_encoder.load_state_dict(torch.load(init_ct_encoder, map_location=device))
        print(f"[init] CT encoder from {init_ct_encoder}", flush=True)
    # Discriminative LR: pretrained BERT at a low LR, from-scratch CT/proj at full LR.
    bert_params: list = []
    other_params: list = []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (bert_params if name.startswith("text_encoder.bert") else other_params).append(p)
    groups = [{"params": other_params, "lr": config.lr}]
    if bert_params:
        groups.append({"params": bert_params, "lr": config.lr * 0.1})
    opt = torch.optim.AdamW(groups, weight_decay=config.weight_decay)
    print(f"trainable: CT/proj={sum(p.numel() for p in other_params):,} "
          f"BERT={sum(p.numel() for p in bert_params):,}", flush=True)
    use_amp = config.amp and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    # Cosine LR schedule with linear warmup (per optimizer step).
    steps_per_epoch = max(1, len(loaders["train"]))
    total_steps = config.epochs * steps_per_epoch
    warmup = max(1, int(0.05 * total_steps))

    def lr_scale(step: int) -> float:
        if step < warmup:
            return step / warmup
        prog = (step - warmup) / max(1, total_steps - warmup)
        return 0.5 * (1.0 + math.cos(math.pi * prog))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_scale)
    txt_q = EmbQueue(queue_size, config.embed_dim, config.n_labels, device)
    ct_q = EmbQueue(queue_size, config.embed_dim, config.n_labels, device)

    best, best_epoch, best_test = -1.0, -1, None
    log_fh = (out_dir / "train_log.jsonl").open("w", encoding="utf-8")
    for epoch in range(config.epochs):
        model.train()
        if config.freeze_text_backbone:
            model.text_encoder.bert.eval()  # type: ignore[union-attr]
        t0, losses = time.time(), []
        for batch in loaders["train"]:
            batch = to_device(batch, device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=use_amp):
                ct, txt = model.encode(batch)
                scale = model.logit_scale.exp().clamp(max=100.0)
                qtxt, qtxt_lab = txt_q.get()
                qct, qct_lab = ct_q.get()
                cand_txt = torch.cat([txt, qtxt]) if qtxt.numel() else txt
                cand_txt_lab = torch.cat([batch.labels, qtxt_lab]) if qtxt.numel() else batch.labels
                cand_ct = torch.cat([ct, qct]) if qct.numel() else ct
                cand_ct_lab = torch.cat([batch.labels, qct_lab]) if qct.numel() else batch.labels
                loss_i = _multipos_loss(ct, cand_txt, cand_txt_lab, batch.labels, scale, beta)
                loss_t = _multipos_loss(txt, cand_ct, cand_ct_lab, batch.labels, scale, beta)
                aux = multilabel_aux_loss(model.classifier(ct), batch.labels)
                loss = 0.5 * (loss_i + loss_t) + config.aux_weight * aux
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            scaler.step(opt)
            scaler.update()
            sched.step()
            txt_q.add(txt, batch.labels)
            ct_q.add(ct, batch.labels)
            losses.append(float(loss.detach()))
        val = encode_split(model, loaders["val"], device, use_amp)
        score = (val["ct2txt_recall@1"] + val["txt2ct_recall@1"]) / 2
        if score > best:
            best, best_epoch = score, epoch
            best_test = encode_split(model, loaders["test"], device, use_amp)
            torch.save({"model": model.state_dict(), "epoch": epoch, "val": val},
                       out_dir / "best.pt")
        rec = {"epoch": epoch, "loss": float(np.mean(losses)),
               "val_ct2txt_recall@10": val["ct2txt_recall@10"],
               "sec": round(time.time() - t0, 1)}
        log_fh.write(json.dumps(rec) + "\n")
        log_fh.flush()
        print(f"[a{epoch:02d}] loss={rec['loss']:.3f} val R@10={val['ct2txt_recall@10']:.3f} "
              f"({rec['sec']}s)", flush=True)
    log_fh.close()

    manifest = {"stage": "P12 augmented retrieval (resample+queue+multipos)",
                "init_ct_encoder": str(init_ct_encoder), "queue_size": queue_size,
                "beta": beta, "counts": {k: len(v) for k, v in subset.items()},
                "best_epoch": best_epoch, "test": best_test}
    (out_dir / "metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    t = best_test or {}
    print(f"\nAUG BEST e{best_epoch} test R@1={t.get('ct2txt_recall@1'):.3f} "
          f"R@5={t.get('ct2txt_recall@5'):.3f} R@10={t.get('ct2txt_recall@10'):.3f} "
          f"mAP={t.get('ct2txt_map'):.3f}", flush=True)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default=str(RUN_DIR))
    ap.add_argument("--init-ct-encoder", type=str, default="runs/p12a/encoder.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--n-train", type=int, default=556)
    ap.add_argument("--n-val", type=int, default=127)
    ap.add_argument("--n-test", type=int, default=118)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--queue", type=int, default=512)
    ap.add_argument("--beta", type=float, default=0.3)
    ap.add_argument("--unfreeze-text", action="store_true",
                    help="fine-tune BERT too (discriminative LR); needs more data")
    ap.add_argument("--allow-cpu", action="store_true")
    args = ap.parse_args()
    overrides = {"n_train": args.n_train, "n_val": args.n_val, "n_test": args.n_test,
                 "epochs": args.epochs}
    if args.batch is not None:
        overrides["batch_size"] = args.batch
    if args.lr is not None:
        overrides["lr"] = args.lr
    if args.unfreeze_text:
        overrides["freeze_text_backbone"] = False
    config = TrainConfig(**{**DEFAULT.to_dict(), **overrides})
    init = Path(args.init_ct_encoder) if args.init_ct_encoder else None
    train_aug(config, Path(args.out), init_ct_encoder=init, queue_size=args.queue,
              beta=args.beta, allow_cpu=args.allow_cpu)


if __name__ == "__main__":
    main()
