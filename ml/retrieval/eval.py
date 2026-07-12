"""Bidirectional retrieval metrics (P13, Architecture §8.4).

Reports **Recall@1/5/10, mAP, nDCG** for BOTH directions (CT->Report and
Report->CT), treated as equally important.

Ground truth: a CT point and its matching report point share the same
`case_id`. Each query therefore has exactly ONE relevant item in the gallery.
With a single relevant item and binary relevance the metrics simplify:

  - Recall@k        = 1 if the true case_id appears in the top-k, else 0.
  - Average Precision = 1 / rank_of_the_hit   (0 if not retrieved).
                      Mean AP over queries == MRR here (single relevant item).
  - nDCG@k          = (1 / log2(rank + 1)) / IDCG, and IDCG = 1 / log2(1 + 1) = 1,
                      so nDCG@k = 1 / log2(rank + 1) when the hit is in top-k.

Pure numpy, framework-free, so it runs in CI without Qdrant.
"""
from __future__ import annotations

import numpy as np

from .embeddings import EmbeddingRecord
from .search import ct_to_text, text_to_ct


def recall_at_k(ranked_case_ids: list[str], true_case_id: str, k: int) -> float:
    return 1.0 if true_case_id in ranked_case_ids[:k] else 0.0


def average_precision(ranked_case_ids: list[str], true_case_id: str) -> float:
    """AP for a single relevant item = 1 / rank of that item (0 if absent)."""
    for rank, cid in enumerate(ranked_case_ids, start=1):
        if cid == true_case_id:
            return 1.0 / rank
    return 0.0


def ndcg(ranked_case_ids: list[str], true_case_id: str, k: int) -> float:
    """Binary, single-relevant nDCG@k (IDCG == 1)."""
    for rank, cid in enumerate(ranked_case_ids[:k], start=1):
        if cid == true_case_id:
            return float(1.0 / np.log2(rank + 1))
    return 0.0


def evaluate_direction(queries, gallery, search_fn, k_values=(1, 5, 10)) -> dict:
    """Average the metrics over every query in one retrieval direction."""
    top_k = max(k_values)
    recalls: dict[int, list[float]] = {k: [] for k in k_values}
    aps: list[float] = []
    ndcgs: list[float] = []
    for q in queries:
        hits = search_fn(q.vector, gallery, top_k=top_k)
        ranked = [h.case_id for h in hits]
        true = q.payload.case_id
        for k in k_values:
            recalls[k].append(recall_at_k(ranked, true, k))
        aps.append(average_precision(ranked, true))
        ndcgs.append(ndcg(ranked, true, top_k))
    out = {f"recall@{k}": float(np.mean(recalls[k])) for k in k_values}
    out["mAP"] = float(np.mean(aps))
    out["nDCG"] = float(np.mean(ndcgs))
    return out


def evaluate_bidirectional(records: list[EmbeddingRecord],
                           k_values=(1, 5, 10)) -> dict:
    """Recall@k / mAP / nDCG for both directions (§8.4)."""
    cts = [r for r in records if r.payload.modality == "ct"]
    reports = [r for r in records if r.payload.modality == "report"]
    return {
        "ct_to_text": evaluate_direction(cts, records, ct_to_text, k_values),
        "text_to_ct": evaluate_direction(reports, records, text_to_ct, k_values),
    }
