"""P13 — retrieval API contract, with the embedder and Qdrant stubbed.

Runs in the backend CI lane: no GPU, no CT-CLIP, no Qdrant required. Verifies the
route contract, the explanation payload, and that an unavailable CT-CLIP service
degrades to a clear 503 instead of silently returning meaningless results.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.retrieval import service as svc
from app.retrieval.embedder import EmbedderUnavailable
from app.retrieval.rerank import FINDING_NAMES

N = len(FINDING_NAMES)
client = TestClient(app)


@dataclass
class StubHit:
    volume: str
    score: float
    findings: list
    report: str


class StubEmbedder:
    def __init__(self, vector=None, findings=None, fail=False):
        self.vector = vector or [0.1] * 512
        self.findings = findings if findings is not None else [0.0] * N
        self.fail = fail

    def embed_text(self, text):
        if self.fail:
            raise EmbedderUnavailable("service down")
        return self.vector

    def embed_volume(self, path):
        if self.fail:
            raise EmbedderUnavailable("service down")
        from app.retrieval.embedder import VolumeEmbedding
        return VolumeEmbedding(vector=self.vector, findings=self.findings)


def _stub_hits():
    eff = [0.0] * N
    eff[FINDING_NAMES.index("Pleural effusion")] = 0.9
    both = [0.0] * N
    both[FINDING_NAMES.index("Pleural effusion")] = 0.9
    both[FINDING_NAMES.index("Cardiomegaly")] = 0.9
    return [StubHit("a.nii.gz", 0.9, both, "effusion and cardiomegaly"),
            StubHit("b.nii.gz", 0.8, eff, "effusion only")]


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(svc, "search", lambda *a, **k: _stub_hits())
    monkeypatch.setattr(svc, "get_client", lambda: object())


def test_text_search_returns_ranked_results_with_explanations(monkeypatch):
    findings = [0.0] * N
    findings[FINDING_NAMES.index("Pleural effusion")] = 0.9
    findings[FINDING_NAMES.index("Cardiomegaly")] = 0.9
    monkeypatch.setattr(svc, "CtClipEmbedder", lambda *a, **k: StubEmbedder(findings=findings))

    r = client.post("/api/retrieval/search/text", json={"text": "pleural effusion", "top": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["query_type"] == "text"
    assert len(body["results"]) == 2
    top = body["results"][0]
    assert top["rank"] == 1
    assert {"volume", "score", "recall_score", "findings_match", "why"} <= set(top)
    # explanations must be grounded in shared findings
    assert isinstance(top["explanation"], list)
    assert top["why"]


def test_volume_search_uses_zero_shot_findings(monkeypatch):
    findings = [0.0] * N
    findings[FINDING_NAMES.index("Pleural effusion")] = 0.95
    monkeypatch.setattr(svc, "CtClipEmbedder", lambda *a, **k: StubEmbedder(findings=findings))

    r = client.post("/api/retrieval/search/volume", json={"path": "x.nii.gz", "top": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["query_type"] == "volume"
    assert any("Pleural effusion" in res["explanation"] for res in body["results"])


def test_embedder_unavailable_returns_503(monkeypatch):
    monkeypatch.setattr(svc, "CtClipEmbedder", lambda *a, **k: StubEmbedder(fail=True))
    r = client.post("/api/retrieval/search/text", json={"text": "anything"})
    assert r.status_code == 503
    assert "failed" in r.json()["detail"].lower() or "down" in r.json()["detail"].lower()


def test_alpha_one_keeps_recall_order(monkeypatch):
    monkeypatch.setattr(svc, "CtClipEmbedder", lambda *a, **k: StubEmbedder())
    r = client.post("/api/retrieval/search/text",
                    json={"text": "q", "top": 2, "alpha": 1.0})
    assert [x["volume"] for x in r.json()["results"]] == ["a.nii.gz", "b.nii.gz"]


def test_query_validation_rejects_empty_text():
    assert client.post("/api/retrieval/search/text", json={"text": ""}).status_code == 422
