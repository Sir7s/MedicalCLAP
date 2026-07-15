"""P12d Stage A — 18-finding multi-label classifier (AUP-004).

A small MLP head on cached CT-FM foundation features predicts the 18 CT-RATE
abnormalities. Provides (a) the "findings vector" used by the re-ranker
(`rerank.py`) and (b) a standalone, well-posed model with honest precision /
recall / AUROC — the reliable deliverable that does not depend on CT-CLIP.

CLI:  python -m ml.models.findings --out runs/findings
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def load_split_features(config, teacher_cache: Path):
    """Return {split: (X[N,512], Y[N,18], vols)} from the cached CT-FM features."""
    from .data import load_labels, select_subset
    subset = select_subset(config)
    labels, cols = load_labels()
    out = {}
    for split, vols in subset.items():
        X, Y, keep = [], [], []
        for v in vols:
            f = teacher_cache / f"{v}.npy"
            if f.is_file() and v in labels:
                X.append(np.load(f))
                Y.append(labels[v])
                keep.append(v)
        out[split] = (np.asarray(X, np.float32), np.asarray(Y, np.float32), keep)
    return out, cols


def auroc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p), float)
    ranks[order] = np.arange(1, len(p) + 1)
    npos = float(y.sum())
    nneg = float(len(y) - npos)
    if npos == 0 or nneg == 0:
        return float("nan")
    return (ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


class FindingsClassifier:
    """Thin wrapper around the trained MLP + feature standardization."""

    def __init__(self, net, mu, sd, cols):
        self.net = net
        self.mu = mu
        self.sd = sd
        self.cols = cols

    def predict_proba(self, feats: np.ndarray) -> np.ndarray:
        import torch
        x = torch.tensor((feats - self.mu) / self.sd, dtype=torch.float32,
                         device=next(self.net.parameters()).device)
        with torch.no_grad():
            return torch.sigmoid(self.net(x)).cpu().numpy()


def train(config, out_dir: Path, *, epochs: int = 300, allow_cpu: bool = False) -> dict:
    import torch
    from torch import nn

    from .ctfm_teacher import CACHE_DIR

    data, cols = load_split_features(config, CACHE_DIR)
    Xtr, Ytr, _ = data["train"]
    Xte, Yte, _ = data["test"]
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    _ = allow_cpu  # CPU is always an acceptable fallback here
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.seed)

    net = nn.Sequential(nn.Linear(512, 256), nn.GELU(), nn.Dropout(0.3),
                        nn.Linear(256, 18)).to(dev)
    pos = Ytr.sum(0)
    pw = torch.tensor((len(Ytr) - pos) / np.clip(pos, 1, None), dtype=torch.float32, device=dev)
    crit = nn.BCEWithLogitsLoss(pos_weight=pw)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    xtr = torch.tensor((Xtr - mu) / sd, device=dev)
    ytr = torch.tensor(Ytr, device=dev)

    for _ in range(epochs):
        net.train()
        perm = torch.randperm(len(xtr), device=dev)
        for i in range(0, len(xtr), 128):
            idx = perm[i:i + 128]
            opt.zero_grad()
            crit(net(xtr[idx]), ytr[idx]).backward()
            opt.step()

    clf = FindingsClassifier(net.eval(), mu, sd, cols)
    prob = clf.predict_proba(Xte)
    aucs = np.array([auroc(Yte[:, k], prob[:, k]) for k in range(18)])
    pred = (prob >= 0.5).astype(int)
    tp = (pred * Yte).sum(0)
    fp = (pred * (1 - Yte)).sum(0)
    fn = ((1 - pred) * Yte).sum(0)
    prec = tp / np.clip(tp + fp, 1, None)
    rec = tp / np.clip(tp + fn, 1, None)
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-6, None)

    metrics = {
        "n_test": int(len(Yte)),
        "macro_auroc": float(np.nanmean(aucs)),
        "classes_auroc_ge_0.70": int((aucs >= 0.70).sum()),
        "classes_auroc_ge_0.80": int((aucs >= 0.80).sum()),
        "macro_precision": float(np.nanmean(prec)),
        "macro_recall": float(np.nanmean(rec)),
        "macro_f1": float(np.nanmean(f1)),
        "micro_precision": float(tp.sum() / max(tp.sum() + fp.sum(), 1)),
        "micro_recall": float(tp.sum() / max(tp.sum() + fn.sum(), 1)),
        "per_class": {cols[k]: {"auroc": float(aucs[k]), "precision": float(prec[k]),
                                "recall": float(rec[k])} for k in range(18)},
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    torch.save({"state": net.state_dict(), "mu": mu, "sd": sd, "cols": cols},
               out_dir / "findings.pt")
    return metrics


def main() -> None:
    from .train_config import DEFAULT, TrainConfig
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="runs/findings")
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--allow-cpu", action="store_true")
    args = ap.parse_args()
    cfg = TrainConfig(**{**DEFAULT.to_dict(), "n_train": 2112, "n_val": 428, "n_test": 463})
    m = train(cfg, Path(args.out), epochs=args.epochs, allow_cpu=args.allow_cpu)
    print(f"macro AUROC {m['macro_auroc']:.3f} | classes AUROC>=0.70: "
          f"{m['classes_auroc_ge_0.70']}/18 >=0.80: {m['classes_auroc_ge_0.80']}/18")
    print(f"macro P {m['macro_precision']:.3f} R {m['macro_recall']:.3f} F1 {m['macro_f1']:.3f}"
          f" | micro P {m['micro_precision']:.3f} R {m['micro_recall']:.3f}")


if __name__ == "__main__":
    main()
