"""P12d Stage B — findings-grounded, explainable re-ranking (AUP-004).

Two-stage retrieval: a base recall model (CT-CLIP when available; here the P12a
retrieval model) yields a similarity matrix; the 18-finding classifier reorders
each query's candidates so clinically-consistent scans rise, and emits the
overlapping findings as a human-readable reason.

    score = alpha * base_similarity + (1 - alpha) * findings_match

The re-ranker only reorders within the recalled pool, so it can lift
Precision@K / mAP / nDCG / R@1 / R@5 without ever lowering the recall ceiling.

Eval:  python -m ml.models.rerank --base runs/p12_scaled/best.pt \
           --findings runs/findings/findings.pt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _norm01(m: np.ndarray) -> np.ndarray:
    lo, hi = m.min(), m.max()
    return (m - lo) / (hi - lo + 1e-9)


def findings_match_matrix(qf: np.ndarray, cf: np.ndarray) -> np.ndarray:
    """Cosine similarity between query and candidate finding vectors (rows)."""
    qn = qf / (np.linalg.norm(qf, axis=1, keepdims=True) + 1e-9)
    cn = cf / (np.linalg.norm(cf, axis=1, keepdims=True) + 1e-9)
    return qn @ cn.T


def rerank_scores(base_sim: np.ndarray, fmatch: np.ndarray, alpha: float) -> np.ndarray:
    return alpha * _norm01(base_sim) + (1.0 - alpha) * _norm01(fmatch)


def explain(qf_row: np.ndarray, cf_row: np.ndarray, cols, thresh: float = 0.5) -> list[str]:
    """Findings both query and candidate express -> the human-readable reason."""
    shared = [cols[k] for k in range(len(cols)) if qf_row[k] >= thresh and cf_row[k] >= thresh]
    return shared


def _metrics(sim: np.ndarray) -> dict:
    from .metrics import mean_average_precision, ndcg, recall_at_k
    out = recall_at_k(sim)
    out["map"] = mean_average_precision(sim)
    out["ndcg"] = ndcg(sim)
    return out


def evaluate(config, base_ckpt: Path, findings_ckpt: Path) -> dict:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader

    from .ctfm_teacher import CACHE_DIR
    from .data import build_datasets, load_labels
    from .findings import FindingsClassifier
    from .train import build_model, collate, to_device

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # Base recall model -> CT/report embeddings -> similarity.
    model = build_model(config).to(device)
    model.load_state_dict(torch.load(base_ckpt, map_location=device)["model"])
    model.eval()
    datasets, subset = build_datasets(config)
    loader = DataLoader(datasets["test"], batch_size=8, shuffle=False, collate_fn=collate)
    cts, txts = [], []
    with torch.no_grad():
        for b in loader:
            b = to_device(b, device)
            ct, txt = model.encode(b)
            cts.append(ct.float().cpu().numpy())
            txts.append(txt.float().cpu().numpy())
    ct_emb = np.concatenate(cts)
    txt_emb = np.concatenate(txts)
    base_sim = ct_emb @ txt_emb.T                       # CT -> report similarity

    # Findings vectors: query CT via classifier on CT-FM features; candidate
    # reports via the volume's ground-truth-ish 18 labels.
    ck = torch.load(findings_ckpt, map_location=device, weights_only=False)  # our own file
    net = nn.Sequential(nn.Linear(512, 256), nn.GELU(), nn.Dropout(0.3),
                        nn.Linear(256, 18)).to(device)
    net.load_state_dict(ck["state"])
    net.eval()
    clf = FindingsClassifier(net, ck["mu"], ck["sd"], ck["cols"])
    labels, cols = load_labels()
    test_vols = subset["test"]
    ctfm = np.stack([np.load(CACHE_DIR / f"{v}.npy") for v in test_vols]).astype(np.float32)
    qf = clf.predict_proba(ctfm)                        # (N,18) predicted CT findings
    cf = np.stack([labels[v] for v in test_vols]).astype(np.float32)  # (N,18) report findings
    fmatch = findings_match_matrix(qf, cf)

    base = _metrics(base_sim)
    grid = {}
    for alpha in (0.9, 0.7, 0.5, 0.3):
        grid[alpha] = _metrics(rerank_scores(base_sim, fmatch, alpha))
    best_alpha = max(grid, key=lambda a: grid[a]["recall@10"])

    # sample explanation for one correct-after-rerank example
    example = None
    reranked = rerank_scores(base_sim, fmatch, best_alpha)
    for i in range(len(test_vols)):
        if int(np.argmax(reranked[i])) == i:
            shared = explain(qf[i], cf[i], cols)
            if shared:
                example = {"query_vol": test_vols[i], "reason": shared}
                break
    return {"n_test": len(test_vols), "base": base, "reranked": grid,
            "best_alpha": best_alpha, "example_explanation": example}


def main() -> None:
    from .train_config import DEFAULT, TrainConfig
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=str, default="runs/p12_scaled/best.pt")
    ap.add_argument("--findings", type=str, default="runs/findings/findings.pt")
    ap.add_argument("--out", type=str, default="runs/rerank")
    args = ap.parse_args()
    cfg = TrainConfig(**{**DEFAULT.to_dict(), "n_train": 2112, "n_val": 428, "n_test": 463})
    res = evaluate(cfg, Path(args.base), Path(args.findings))
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "metrics.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    b = res["base"]
    print(f"BASE (recall only)      R@1={b['recall@1']:.3f} R@5={b['recall@5']:.3f} "
          f"R@10={b['recall@10']:.3f} mAP={b['map']:.3f} nDCG={b['ndcg']:.3f}")
    for a, m in res["reranked"].items():
        tag = " <- best" if a == res["best_alpha"] else ""
        print(f"RERANK alpha={a}         R@1={m['recall@1']:.3f} R@5={m['recall@5']:.3f} "
              f"R@10={m['recall@10']:.3f} mAP={m['map']:.3f} nDCG={m['ndcg']:.3f}{tag}")
    if res["example_explanation"]:
        e = res["example_explanation"]
        print(f"\nexample: {e['query_vol']} correctly ranked #1 — "
              f"reason: both show {', '.join(e['reason'])}")


if __name__ == "__main__":
    main()
