"""Datastore readiness probes (P1/S4).

Each probe is defensive: any failure is captured and reported as an error entry
rather than raising, so /health/ready can return a structured per-dependency
report. No credentials are ever included in the response or logs (H-14).
"""
from __future__ import annotations

import httpx
import psycopg
import redis

from .config import Settings


def check_postgres(s: Settings) -> dict:
    try:
        with psycopg.connect(
            host=s.postgres_host,
            port=s.postgres_port,
            user=s.postgres_user,
            password=s.postgres_password,
            dbname=s.postgres_db,
            connect_timeout=2,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report, never crash readiness
        return {"status": "error", "detail": type(exc).__name__}


def check_redis(s: Settings) -> dict:
    try:
        client = redis.Redis(host=s.redis_host, port=s.redis_port, socket_timeout=2)
        if client.ping():
            return {"status": "ok"}
        return {"status": "error", "detail": "no PONG"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": type(exc).__name__}


def check_qdrant(s: Settings) -> dict:
    try:
        r = httpx.get(f"http://{s.qdrant_host}:{s.qdrant_port}/readyz", timeout=2)
        if r.status_code == 200:
            return {"status": "ok"}
        return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": type(exc).__name__}


def readiness(s: Settings) -> tuple[bool, dict]:
    deps = {
        "postgres": check_postgres(s),
        "redis": check_redis(s),
        "qdrant": check_qdrant(s),
    }
    ok = all(d["status"] == "ok" for d in deps.values())
    return ok, deps
