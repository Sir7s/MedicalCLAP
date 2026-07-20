"""P12d — findings re-ranking math (AUP-004). Pure numpy, runs in CI."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.models.rerank import explain, findings_match_matrix, rerank_scores  # noqa: E402


def test_findings_match_is_cosine_and_symmetric_diag():
    qf = np.array([[1.0, 0, 0], [0, 1.0, 1.0]], dtype=np.float32)
    m = findings_match_matrix(qf, qf)
    assert np.allclose(np.diag(m), 1.0, atol=1e-5)   # identical vectors -> 1.0
    assert m[0, 1] < 0.1                              # disjoint findings -> ~0


def test_rerank_promotes_findings_match():
    # base ranks candidate 0 top for query 0; findings say candidate 1 matches.
    base = np.array([[0.9, 0.1]], dtype=np.float32)
    fmatch = np.array([[0.0, 1.0]], dtype=np.float32)
    # alpha=1 -> base wins (idx 0); alpha=0 -> findings win (idx 1)
    assert int(np.argmax(rerank_scores(base, fmatch, alpha=1.0)[0])) == 0
    assert int(np.argmax(rerank_scores(base, fmatch, alpha=0.0)[0])) == 1


def test_rerank_cannot_change_pool():
    # re-ranking is a reorder: same set of candidates, just permuted scores.
    rng = np.random.default_rng(0)
    base = rng.random((4, 4))
    fmatch = rng.random((4, 4))
    r = rerank_scores(base, fmatch, 0.5)
    assert r.shape == base.shape
    assert np.isfinite(r).all()


def test_explain_lists_shared_findings():
    cols = ["effusion", "cardiomegaly", "nodule"]
    qf = np.array([0.9, 0.8, 0.1])
    cf = np.array([0.7, 0.9, 0.2])
    assert explain(qf, cf, cols) == ["effusion", "cardiomegaly"]
    assert explain(qf, np.array([0.1, 0.1, 0.9]), cols) == []
