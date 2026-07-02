"""P1 critical test — backend ↔ datastore cross-service reachability.

Criticality: CRITICAL (core functionality, Master Plan sec 6). Verifies the
backend container can actually reach PostgreSQL, Redis, and Qdrant over the
compose network via /health/ready.

Auto-skips when the backend port is not open, so the unit lane stays green
without the stack; the docker-compose CI job runs it against the live stack.
"""
from __future__ import annotations

import json
import socket
import urllib.request

import pytest

HOST = "127.0.0.1"
BACKEND_PORT = 8000


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _port_open(HOST, BACKEND_PORT),
    reason="backend not running (docker compose up -d)",
)


def _get(path: str):
    req = urllib.request.Request(f"http://{HOST}:{BACKEND_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # 503 still carries a JSON body
        return e.code, json.loads(e.read().decode())


def test_backend_liveness():
    status, body = _get("/health")
    assert status == 200
    assert body["status"] == "ok"


def test_backend_readiness_all_datastores_ok():
    status, body = _get("/health/ready")
    assert status == 200, f"readiness degraded: {body}"
    deps = body["dependencies"]
    assert deps["postgres"]["status"] == "ok"
    assert deps["redis"]["status"] == "ok"
    assert deps["qdrant"]["status"] == "ok"
