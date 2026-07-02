"""Backend skeleton tests (P1/S3)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "backend"


def test_root_has_medical_disclaimer():
    r = client.get("/")
    assert r.status_code == 200
    assert "clinical diagnosis" in r.json()["disclaimer"].lower()


def test_openapi_available():
    assert client.get("/openapi.json").status_code == 200


def test_ready_endpoint_shape():
    """Readiness returns a well-formed per-dependency report (200 up / 503 down)."""
    r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body["dependencies"]) == {"postgres", "redis", "qdrant"}
    for dep in body["dependencies"].values():
        assert dep["status"] in ("ok", "error")


def test_cors_allows_configured_origin():
    origin = "http://127.0.0.1:5173"
    r = client.get("/health", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin
