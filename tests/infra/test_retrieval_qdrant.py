"""P13 — Qdrant index + two-stage retrieval against the real datastore (infra lane)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.retrieval.index import (  # noqa: E402
    VOLUME_COLLECTION,
    Hit,
    count,
    ensure_collections,
    get_client,
    search,
    upsert_volumes,
)
from app.retrieval.rerank import FINDING_NAMES, rerank  # noqa: E402

DIM = 512
N = len(FINDING_NAMES)


def _vec(seed: int) -> list[float]:
    """Deterministic unit-ish vector distinguishable by its leading component."""
    v = [0.0] * DIM
    v[seed % DIM] = 1.0
    return v


@pytest.fixture(scope="module")
def client():
    c = get_client()
    try:
        c.get_collections()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"qdrant unavailable: {exc}")
    ensure_collections(c)
    return c


def test_ensure_collections_is_idempotent(client):
    ensure_collections(client)
    ensure_collections(client)
    names = {c.name for c in client.get_collections().collections}
    assert VOLUME_COLLECTION in names


def test_upsert_then_search_returns_nearest(client):
    findings = [0.0] * N
    findings[FINDING_NAMES.index("Pleural effusion")] = 0.9
    recs = [
        {"id": 9001, "vector": _vec(1), "volume": "t_one.nii.gz",
         "report": "effusion present", "findings": findings},
        {"id": 9002, "vector": _vec(2), "volume": "t_two.nii.gz",
         "report": "clear study", "findings": [0.0] * N},
    ]
    assert upsert_volumes(client, recs) == 2
    assert count(client, VOLUME_COLLECTION) >= 2

    hits = search(client, VOLUME_COLLECTION, _vec(1), limit=5)
    assert hits, "expected at least one hit"
    assert hits[0].volume == "t_one.nii.gz"       # nearest by cosine
    assert isinstance(hits[0], Hit)
    assert len(hits[0].findings) == N


def test_end_to_end_rerank_preserves_pool_and_explains(client):
    findings = [0.0] * N
    findings[FINDING_NAMES.index("Pleural effusion")] = 0.9
    hits = search(client, VOLUME_COLLECTION, _vec(1), limit=5)
    ranked = rerank(findings, hits, alpha=0.5)
    assert len(ranked) == len(hits)               # re-rank never drops candidates
    top = ranked[0]
    for name in top.explanation:                  # explanations are grounded
        assert findings[FINDING_NAMES.index(name)] >= 0.5


def test_cleanup(client):
    client.delete(collection_name=VOLUME_COLLECTION,
                  points_selector=[9001, 9002], wait=True)
