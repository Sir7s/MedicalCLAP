"""Retrieval evaluation metrics (P11, SPEC-07 §8.4): Recall@K, mAP, nDCG.

Given a similarity matrix `sim` (queries x candidates) with the correct match on
the diagonal, compute standard single-positive retrieval metrics in one
direction. Bidirectional evaluation calls this on `sim` and `sim.T`.
"""
from __future__ import annotations

import numpy as np


def _ranks(sim: np.ndarray) -> np.ndarray:
    """Rank (0-based) of the diagonal (true match) for each query row."""
    n = sim.shape[0]
    order = np.argsort(-sim, axis=1)              # descending similarity
    ranks = np.empty(n, dtype=np.int64)
    for i in range(n):
        ranks[i] = int(np.where(order[i] == i)[0][0])
    return ranks


def recall_at_k(sim: np.ndarray, ks=(1, 5, 10)) -> dict[str, float]:
    ranks = _ranks(sim)
    n = len(ranks)
    return {f"recall@{k}": float((ranks < k).mean()) for k in ks if k <= n or True}


def mean_average_precision(sim: np.ndarray) -> float:
    """Single positive per query -> AP = 1/(rank+1); mAP is the mean."""
    ranks = _ranks(sim)
    return float((1.0 / (ranks + 1.0)).mean())


def ndcg(sim: np.ndarray) -> float:
    """Single positive, binary relevance -> nDCG = 1/log2(rank+2)."""
    ranks = _ranks(sim)
    return float((1.0 / np.log2(ranks + 2.0)).mean())


def evaluate_bidirectional(ct_emb: np.ndarray, txt_emb: np.ndarray) -> dict[str, float]:
    sim = ct_emb @ txt_emb.T
    out: dict[str, float] = {}
    for name, m in (("ct2txt", sim), ("txt2ct", sim.T)):
        out.update({f"{name}_{k}": v for k, v in recall_at_k(m).items()})
        out[f"{name}_map"] = mean_average_precision(m)
        out[f"{name}_ndcg"] = ndcg(m)
    return out
