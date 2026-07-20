"""P19 — full-system integration: the real user journey, end to end (infra lane).

Exercises the path a user actually takes across every phase's contribution:

    workspace (P2) -> retrieval search (P13) -> re-ranked, explained results (P12d)
    -> save to history (P5/P15) -> export JSON/CSV (P15) -> backup + verify (P18)

Retrieval is driven through the real API with a stubbed embedder so the journey is
testable without a GPU; Qdrant, Postgres and Redis are real. Anything unavailable
skips rather than silently passing.
"""
from __future__ import annotations

import csv
import io
import json
import socket
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

HOST = "127.0.0.1"


def _port(p: int) -> bool:
    try:
        with socket.create_connection((HOST, p), timeout=1):
            return True
    except OSError:
        return False


_READY = _port(5432) and _port(6379) and _port(6333)
pytestmark = pytest.mark.skipif(
    not _READY, reason="postgres/redis/qdrant not up")

if _READY:
    from app.main import app
    from app.retrieval import service as svc
    from app.retrieval.index import (
        VOLUME_COLLECTION,
        ensure_collections,
        get_client,
        upsert_volumes,
    )
    from app.retrieval.rerank import FINDING_NAMES
    from fastapi.testclient import TestClient

    client = TestClient(app)

N = 18
DIM = 512


def _vec(seed: int) -> list[float]:
    v = [0.0] * DIM
    v[seed % DIM] = 1.0
    return v


def _findings(*names: str) -> list[float]:
    v = [0.0] * N
    for n in names:
        v[FINDING_NAMES.index(n)] = 0.9
    return v


class _StubEmbedder:
    """Stands in for the CT-CLIP GPU service so the journey runs without a GPU."""

    def __init__(self, vector, findings):
        self._v, self._f = vector, findings

    def embed_text(self, text):  # noqa: ARG002
        return self._v

    def embed_volume(self, path):  # noqa: ARG002
        from app.retrieval.embedder import VolumeEmbedding
        return VolumeEmbedding(vector=self._v, findings=self._f)


@pytest.fixture(scope="module")
def indexed_corpus():
    qc = get_client()
    ensure_collections(qc)
    base = 70000
    upsert_volumes(qc, [
        {"id": base + 1, "vector": _vec(11), "volume": "e2e_effusion.nii.gz",
         "report": "Large pleural effusion with cardiomegaly.",
         "findings": _findings("Pleural effusion", "Cardiomegaly")},
        {"id": base + 2, "vector": _vec(12), "volume": "e2e_clear.nii.gz",
         "report": "No acute abnormality.", "findings": [0.0] * N},
    ])
    yield
    qc.delete(collection_name=VOLUME_COLLECTION,
              points_selector=[base + 1, base + 2], wait=True)


def test_full_user_journey(indexed_corpus, monkeypatch, tmp_path):
    """Search -> explained results -> save -> export -> backup, as a user would."""
    # --- 1. retrieval through the real API (embedder stubbed) ------------------
    q_findings = _findings("Pleural effusion", "Cardiomegaly")
    monkeypatch.setattr(svc, "CtClipEmbedder",
                        lambda *a, **k: _StubEmbedder(_vec(11), q_findings))

    r = client.post("/api/retrieval/search/text",
                    json={"text": "large pleural effusion", "top": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["results"], "retrieval returned no results"
    top = body["results"][0]

    # the explanation must be grounded, not decorative
    assert "Pleural effusion" in top["explanation"]
    assert top["why"].startswith("Both show")

    # --- 2. persist the search (P5 history, P15 workflow) ---------------------
    ws = client.post("/api/workspaces")
    assert ws.status_code in (200, 201), ws.text
    workspace_id = ws.json()["workspace_id"]

    saved = client.post("/api/history/save", json={
        "workspace_id": workspace_id, "title": "e2e effusion search",
        "payload": {"query": body["query"], "results": body["results"]},
    })
    assert saved.status_code == 200, saved.text
    record_id = saved.json()["history_record_id"]

    # --- 3. it is visible in history and round-trips ------------------------
    listing = client.get("/api/history").json()
    assert any(item["id"] == record_id for item in listing)
    detail = client.get(f"/api/history/{record_id}").json()
    assert detail["payload"]["results"][0]["volume"] == top["volume"]

    # --- 4. export both formats (P15) ---------------------------------------
    js = client.get(f"/api/history/{record_id}/export", params={"format": "json"})
    assert js.status_code == 200
    assert "attachment" in js.headers["content-disposition"]
    assert json.loads(js.text)["payload"]["results"]

    cs = client.get(f"/api/history/{record_id}/export", params={"format": "csv"})
    assert cs.status_code == 200
    rows = list(csv.reader(io.StringIO(cs.text)))
    header = next(i for i, row in enumerate(rows) if row and row[0] == "rank")
    assert len([r for r in rows[header + 1:] if r]) == len(body["results"])

    # --- 5. back it up and verify integrity (P18) ---------------------------
    import backup
    target = backup.create_backup(tmp_path / "backups", workspace_root=tmp_path / "none")
    result = backup.verify_backup(target)
    assert result["ok"], result["problems"]
    manifest = json.loads((target / backup.MANIFEST).read_text(encoding="utf-8"))
    qd = next(c for c in manifest["components"] if c["name"] == "qdrant")
    assert qd["status"] == "ok", "qdrant is up, so the backup must capture its state"


def test_reranking_changes_order_but_not_membership(indexed_corpus, monkeypatch):
    """Regression for the core invariant: re-ranking permutes, never drops."""
    monkeypatch.setattr(svc, "CtClipEmbedder",
                        lambda *a, **k: _StubEmbedder(_vec(11), _findings("Pleural effusion")))
    hi = client.post("/api/retrieval/search/text",
                     json={"text": "q", "top": 5, "alpha": 1.0}).json()["results"]
    lo = client.post("/api/retrieval/search/text",
                     json={"text": "q", "top": 5, "alpha": 0.0}).json()["results"]
    assert {h["volume"] for h in hi} == {h["volume"] for h in lo}


def test_embedder_outage_is_reported_not_faked(indexed_corpus, monkeypatch):
    """System-level honesty: no engine -> 503, never invented results."""
    from app.retrieval.embedder import EmbedderUnavailable

    class Dead:
        def embed_text(self, text):  # noqa: ARG002
            raise EmbedderUnavailable("service down")

    monkeypatch.setattr(svc, "CtClipEmbedder", lambda *a, **k: Dead())
    r = client.post("/api/retrieval/search/text", json={"text": "anything"})
    assert r.status_code == 503


def test_history_record_ids_are_unique_per_save(indexed_corpus):
    ws = client.post("/api/workspaces").json()["workspace_id"]
    ids = {
        client.post("/api/history/save", json={
            "workspace_id": ws, "title": f"dup-{i}", "payload": {"results": []},
        }).json()["history_record_id"]
        for i in range(3)
    }
    assert len(ids) == 3
    assert all(uuid.UUID(i) for i in ids)
