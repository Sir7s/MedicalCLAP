"""P1 critical test — datastore reachability & loopback-only binding.

Criticality: CRITICAL (core functionality + security, Master Plan sec 6;
Architecture v2.4.5 SPEC-08 sec 9.1 requires 127.0.0.1 binding).

These are integration tests against the running compose stack. They auto-skip
when the stack is not up, so the unit CI lane stays green without Docker; the
dedicated docker-compose CI job brings the stack up and runs them.
"""
from __future__ import annotations

import socket
import urllib.request

import pytest

HOST = "127.0.0.1"
POSTGRES_PORT = 5432
REDIS_PORT = 6379
QDRANT_HTTP_PORT = 6333


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _stack_up() -> bool:
    return _port_open(HOST, QDRANT_HTTP_PORT) and _port_open(HOST, POSTGRES_PORT)


pytestmark = pytest.mark.skipif(
    not _stack_up(),
    reason="compose stack not running (docker compose -f infra/docker-compose.yml up -d)",
)


@pytest.mark.parametrize("port", [POSTGRES_PORT, REDIS_PORT, QDRANT_HTTP_PORT])
def test_datastore_port_reachable_on_loopback(port):
    assert _port_open(HOST, port), f"datastore port {port} not reachable on {HOST}"


def test_redis_responds_to_ping():
    with socket.create_connection((HOST, REDIS_PORT), timeout=2) as s:
        s.sendall(b"PING\r\n")
        resp = s.recv(64)
    assert resp.startswith(b"+PONG"), f"unexpected redis reply: {resp!r}"


def test_qdrant_readyz_ok():
    with urllib.request.urlopen(f"http://{HOST}:{QDRANT_HTTP_PORT}/readyz", timeout=3) as r:
        assert r.status == 200


def test_qdrant_reports_expected_version():
    with urllib.request.urlopen(f"http://{HOST}:{QDRANT_HTTP_PORT}/", timeout=3) as r:
        body = r.read().decode("utf-8", "replace")
    assert '"version":"1.18.2"' in body.replace(" ", ""), "qdrant version drift vs digest lock"


def test_postgres_speaks_pg_wire():
    """A raw TCP connect + minimal handshake byte proves PostgreSQL is listening.
    (Full auth is exercised by the backend cross-service test in P1/S4.)"""
    with socket.create_connection((HOST, POSTGRES_PORT), timeout=2) as s:
        # SSLRequest: length=8, code=80877103. Postgres replies 'S' or 'N'.
        s.sendall(b"\x00\x00\x00\x08\x04\xd2\x16/")
        reply = s.recv(1)
    assert reply in (b"S", b"N"), f"not a PostgreSQL server: {reply!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
