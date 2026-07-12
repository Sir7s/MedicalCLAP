"""P13 tests — placeholder embedding contract (§8.2/§8.3).

Gates: 512-d, float32, L2-normalized, finite, deterministic, paired CT/report.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.retrieval import EMBED_DIM  # noqa: E402
from ml.retrieval.embeddings import load_embeddings  # noqa: E402


def test_vector_contract():
    for r in load_embeddings(n_cases=8):
        assert r.vector.shape == (EMBED_DIM,)
        assert r.vector.dtype == np.float32
        assert np.isfinite(r.vector).all()
        assert np.isclose(np.linalg.norm(r.vector), 1.0, atol=1e-5)


def test_paired_ct_and_report_per_case():
    recs = load_embeddings(n_cases=8)
    assert len(recs) == 16
    by_case: dict[str, set[str]] = {}
    for r in recs:
        by_case.setdefault(r.payload.case_id, set()).add(r.payload.modality)
    assert all(m == {"ct", "report"} for m in by_case.values())


def test_determinism_same_seed():
    a = load_embeddings(n_cases=4, seed=13)
    b = load_embeddings(n_cases=4, seed=13)
    for ra, rb in zip(a, b, strict=True):
        assert ra.point_id == rb.point_id
        assert np.array_equal(ra.vector, rb.vector)


def test_different_seed_differs():
    a = load_embeddings(n_cases=4, seed=13)
    b = load_embeddings(n_cases=4, seed=99)
    assert not np.array_equal(a[0].vector, b[0].vector)


def test_matching_pair_closer_than_random():
    # Shared-latent design => a case's CT and report should be more similar
    # (cosine) than a CT and an unrelated report. Gives eval real signal.
    recs = load_embeddings(n_cases=16, seed=7)
    ct = {r.payload.case_id: r.vector for r in recs if r.payload.modality == "ct"}
    rep = {r.payload.case_id: r.vector for r in recs if r.payload.modality == "report"}
    cases = list(ct)
    same = float(ct[cases[0]] @ rep[cases[0]])
    other = float(ct[cases[0]] @ rep[cases[1]])
    assert same > other
