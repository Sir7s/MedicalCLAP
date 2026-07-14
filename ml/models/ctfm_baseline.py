"""P12b diagnostic — CT-FM's *own* retrieval score (the "beat the foundation" bar).

Trains only a linear projection on the frozen CT-FM features (no PointNet++)
against Bio_ClinicalBERT report embeddings, with the same contrastive objective
and the same held-out test set as the P12 retrieval model. The resulting held-out
Recall@K is the concrete target our PointNet++-based model must exceed to claim it
beats the foundation model on this task.

Run:  python -m ml.models.ctfm_baseline [--epochs N] [--out runs/ctfm_baseline]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .data import load_labels, select_subset
from .losses import clip_contrastive_loss, multilabel_aux_loss
from .metrics import evaluate_bidirectional
from .train_config import DEFAULT, TrainConfig

RUN_DIR = Path("runs/ctfm_baseline")


class FeatReportDataset:
    def __init__(self, vols, reports, labels, tokenizer, seq_len, n_labels, teacher_cache):
        self.vols = vols
        self.reports = reports
        self.labels = labels
        self.tok = tokenizer
        self.seq_len = seq_len
        self.n_labels = n_labels
        self.cache = teacher_cache

    def __len__(self):
        return len(self.vols)

    def __getitem__(self, i):
        vol = self.vols[i]
        feat = np.load(self.cache / f"{vol}.npy").astype(np.float32)
        rep = self.reports.get(vol)
        enc = self.tok(rep.retrieval_text if rep else "", truncation=True,
                       max_length=self.seq_len, padding="max_length", return_tensors=None)
        label = self.labels.get(vol, np.zeros(self.n_labels, dtype=np.float32))
        return (feat, np.asarray(enc["input_ids"], dtype=np.int64),
                np.asarray(enc["attention_mask"], dtype=np.int64), label)


def collate(items):
    feat = torch.from_numpy(np.stack([it[0] for it in items])).float()
    ids = torch.from_numpy(np.stack([it[1] for it in items])).long()
    mask = torch.from_numpy(np.stack([it[2] for it in items])).long()
    labels = torch.from_numpy(np.stack([it[3] for it in items])).float()
    return feat, ids, mask, labels


class FeatureRetrieval(nn.Module):
    """Linear projection on frozen CT-FM features + (frozen) Bio_ClinicalBERT."""

    def __init__(self, feat_dim, embed_dim, n_labels):
        super().__init__()
        from .text_encoder import build_bioclinicalbert
        self.ct_proj = nn.Sequential(nn.Linear(feat_dim, embed_dim), nn.GELU(),
                                     nn.Linear(embed_dim, embed_dim))
        self.text_encoder = build_bioclinicalbert(out_dim=embed_dim)
        for p in self.text_encoder.bert.parameters():
            p.requires_grad_(False)
        self.classifier = nn.Linear(embed_dim, n_labels)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))

    def encode(self, feat, ids, mask):
        ct = torch.nn.functional.normalize(self.ct_proj(feat), dim=-1)
        txt = self.text_encoder(ids, mask)
        return ct, txt


def build_datasets(config, teacher_cache):
    from ..text.report import load_reports
    from ..text.tokenizer import get_tokenizer
    subset = select_subset(config)
    reports = load_reports()
    labels, _ = load_labels()
    tok = get_tokenizer()
    ds = {k: FeatReportDataset(v, reports, labels, tok, config.seq_len, config.n_labels,
                               teacher_cache) for k, v in subset.items()}
    return ds, subset


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    cts, txts = [], []
    for feat, ids, mask, _ in loader:
        feat, ids, mask = feat.to(device), ids.to(device), mask.to(device)
        ct, txt = model.encode(feat, ids, mask)
        cts.append(ct.float().cpu().numpy())
        txts.append(txt.float().cpu().numpy())
    return evaluate_bidirectional(np.concatenate(cts), np.concatenate(txts))


def train(config: TrainConfig, out_dir: Path, *, allow_cpu: bool = False) -> dict:
    from .ctfm_teacher import CACHE_DIR, teacher_dim
    device = config.device
    if device == "cuda" and not torch.cuda.is_available():
        if not allow_cpu:
            raise SystemExit("CUDA requested but unavailable; pass --allow-cpu.")
        device = "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    datasets, subset = build_datasets(config, CACHE_DIR)
    loaders = {k: DataLoader(datasets[k], batch_size=config.batch_size,
                             shuffle=(k == "train"), num_workers=config.num_workers,
                             collate_fn=collate, drop_last=(k == "train"))
               for k in datasets}

    model = FeatureRetrieval(teacher_dim(), config.embed_dim, config.n_labels).to(device)
    model.text_encoder.bert.eval()
    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=config.lr, weight_decay=config.weight_decay)
    best, best_test = -1.0, None
    for epoch in range(config.epochs):
        model.train()
        model.text_encoder.bert.eval()
        for feat, ids, mask, labels in loaders["train"]:
            feat, ids, mask, labels = (feat.to(device), ids.to(device),
                                       mask.to(device), labels.to(device))
            opt.zero_grad(set_to_none=True)
            ct, txt = model.encode(feat, ids, mask)
            loss = (clip_contrastive_loss(ct, txt, model.logit_scale.exp().clamp(max=100.0))
                    + config.aux_weight * multilabel_aux_loss(model.classifier(ct), labels))
            loss.backward()
            opt.step()
        val = evaluate(model, loaders["val"], device)
        score = (val["ct2txt_recall@1"] + val["txt2ct_recall@1"]) / 2
        if score > best:
            best = score
            best_test = evaluate(model, loaders["test"], device)
        print(f"[b{epoch:02d}] val R@1={val['ct2txt_recall@1']:.3f} "
              f"R@10={val['ct2txt_recall@10']:.3f}", flush=True)

    manifest = {"stage": "CT-FM frozen-feature retrieval baseline (goal to beat)",
                "counts": {k: len(v) for k, v in subset.items()},
                "test": best_test}
    (out_dir / "metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    t = best_test or {}
    print(f"\nCT-FM BASELINE test CT->text R@1={t.get('ct2txt_recall@1'):.3f} "
          f"R@5={t.get('ct2txt_recall@5'):.3f} R@10={t.get('ct2txt_recall@10'):.3f} "
          f"mAP={t.get('ct2txt_map'):.3f}", flush=True)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default=str(RUN_DIR))
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--allow-cpu", action="store_true")
    args = ap.parse_args()
    config = TrainConfig(**{**DEFAULT.to_dict(), "n_train": 556, "n_val": 127,
                            "n_test": 118, "epochs": args.epochs})
    train(config, Path(args.out), allow_cpu=args.allow_cpu)


if __name__ == "__main__":
    main()
