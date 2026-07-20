"""P13 — serving-side re-rank + explanation invariants (pure Python, runs in CI)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.retrieval.rerank import (  # noqa: E402
    DEFAULT_ALPHA,
    FINDING_NAMES,
    rerank,
    shared_findings,
)


@dataclass
class FakeHit:
    volume: str
    score: float
    findings: list
    report: str = ""


def _hits():
    n = len(FINDING_NAMES)
    eff = [0.0] * n
    eff[FINDING_NAMES.index("Pleural effusion")] = 0.9
    card = [0.0] * n
    card[FINDING_NAMES.index("Cardiomegaly")] = 0.9
    both = [0.0] * n
    both[FINDING_NAMES.index("Pleural effusion")] = 0.9
    both[FINDING_NAMES.index("Cardiomegaly")] = 0.9
    return [FakeHit("a", 0.90, card), FakeHit("b", 0.80, both), FakeHit("c", 0.70, eff)], both


def test_reranking_is_a_permutation_recall_ceiling_preserved():
    """The re-ranker may reorder but must never drop or invent candidates."""
    hits, q = _hits()
    out = rerank(q, hits, alpha=0.5)
    assert len(out) == len(hits)
    assert {r.volume for r in out} == {h.volume for h in hits}


def test_findings_agreement_promotes_matching_candidate():
    """With findings weighted, the candidate sharing both findings should rise."""
    hits, q = _hits()
    base_top = max(hits, key=lambda h: h.score).volume        # 'a' by recall alone
    reranked_top = rerank(q, hits, alpha=0.0)[0].volume        # findings only
    assert base_top == "a"
    assert reranked_top == "b"


def test_alpha_one_preserves_recall_order():
    hits, q = _hits()
    out = rerank(q, hits, alpha=1.0)
    assert [r.volume for r in out] == ["a", "b", "c"]


def test_explanation_only_cites_shared_findings():
    """An explanation must never claim a finding one side does not express."""
    hits, q = _hits()
    for r in rerank(q, hits, alpha=DEFAULT_ALPHA):
        for name in r.explanation:
            k = FINDING_NAMES.index(name)
            assert q[k] >= 0.5
            src = next(h for h in hits if h.volume == r.volume)
            assert src.findings[k] >= 0.5


def test_shared_findings_empty_when_disjoint():
    n = len(FINDING_NAMES)
    a = [0.0] * n
    a[0] = 0.9
    b = [0.0] * n
    b[1] = 0.9
    assert shared_findings(a, b) == []


def test_rerank_handles_empty_pool():
    assert rerank([0.1] * len(FINDING_NAMES), []) == []
