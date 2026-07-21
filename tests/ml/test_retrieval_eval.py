"""P13 tests — retrieval metrics (§8.4).

Gates: hand-computed metric values on a known ranking; bidirectional report has
all metrics; placeholder embeddings beat random chance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.retrieval.embeddings import load_embeddings  # noqa: E402
from ml.retrieval.eval import (  # noqa: E402
    average_precision,
    evaluate_bidirectional,
    ndcg,
    recall_at_k,
)


def test_recall_at_k_hand_computed():
    ranked = ["c", "a", "b"]  # true "a" is at rank 2
    assert recall_at_k(ranked, "a", 1) == 0.0
    assert recall_at_k(ranked, "a", 2) == 1.0


def test_average_precision_is_reciprocal_rank():
    assert average_precision(["c", "a", "b"], "a") == 0.5   # rank 2 -> 1/2
    assert average_precision(["a", "b"], "a") == 1.0        # rank 1
    assert average_precision(["b", "c"], "a") == 0.0        # absent


def test_ndcg_hand_computed():
    # hit at rank 2 -> 1/log2(3); IDCG == 1
    assert np.isclose(ndcg(["c", "a", "b"], "a", 3), 1.0 / np.log2(3))
    assert ndcg(["c", "b"], "a", 3) == 0.0


def test_bidirectional_reports_all_metrics():
    recs = load_embeddings(n_cases=16, seed=5)
    out = evaluate_bidirectional(recs)
    for direction in ("ct_to_text", "text_to_ct"):
        m = out[direction]
        for key in ("recall@1", "recall@5", "recall@10", "mAP", "nDCG"):
            assert key in m and 0.0 <= m[key] <= 1.0


def test_metrics_above_chance_on_placeholder():
    recs = load_embeddings(n_cases=64, seed=5, noise=0.15)
    out = evaluate_bidirectional(recs)
    # 64 reports in the gallery => random recall@10 ~ 10/64 ~ 0.16. Shared-latent
    # placeholder should be far above that.
    assert out["ct_to_text"]["recall@10"] > 0.8
    assert out["text_to_ct"]["mAP"] > 0.5
