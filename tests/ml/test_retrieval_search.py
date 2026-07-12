"""P13 tests — bidirectional search (§2.2/§8.4).

Gates: correct modality filtering; top_k respected; scores descending; on
placeholder data a query's own case ranks at the top.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.retrieval.embeddings import load_embeddings  # noqa: E402
from ml.retrieval.search import ct_to_text, text_to_ct  # noqa: E402


def test_ct_to_text_returns_only_reports():
    recs = load_embeddings(n_cases=16, seed=3)
    ct = next(r for r in recs if r.payload.modality == "ct")
    hits = ct_to_text(ct.vector, recs, top_k=5)
    assert len(hits) == 5
    assert all(h.modality == "report" for h in hits)


def test_text_to_ct_returns_only_cts():
    recs = load_embeddings(n_cases=16, seed=3)
    rep = next(r for r in recs if r.payload.modality == "report")
    hits = text_to_ct(rep.vector, recs, top_k=5)
    assert all(h.modality == "ct" for h in hits)


def test_scores_descending():
    recs = load_embeddings(n_cases=16, seed=3)
    ct = recs[0]
    hits = ct_to_text(ct.vector, recs, top_k=10)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_self_match_ranks_first_on_placeholder():
    recs = load_embeddings(n_cases=16, seed=3, noise=0.15)
    ct = next(r for r in recs if r.payload.modality == "ct")
    top = ct_to_text(ct.vector, recs, top_k=1)[0]
    assert top.case_id == ct.payload.case_id
