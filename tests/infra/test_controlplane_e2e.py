"""P6 critical tests — full control-plane end-to-end validation.

Master Plan P6 key tests: end-to-end mock retrieval, supervisor crash recovery,
event gap recovery, history save/reopen — driven through the public API surface
plus the deterministic runner tick.

Auto-skips unless PostgreSQL + Redis are up and the P5 schema is migrated.
"""
from __future__ import annotations

import os
import socket
import time
import uuid

import pytest

os.environ["MEDCLIP_FAILPOINTS"] = "1"

HOST = "127.0.0.1"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=1):
            return True
    except OSError:
        return False


_READY = False
if _port_open(5432) and _port_open(6379):
    try:
        from app.db.base import get_engine
        from sqlalchemy import inspect

        _READY = inspect(get_engine()).has_table("history_records")
    except Exception:  # noqa: BLE001
        _READY = False

pytestmark = pytest.mark.skipif(not _READY, reason="stack down or schema missing")

if _READY:
    from app import failpoints
    from app.controlplane import runner
    from app.db.base import get_sessionmaker
    from app.main import app
    from app.queue.redis_client import EXEC_STREAM, ensure_group, get_redis
    from app.supervisor import consumer as sup
    from fastapi.testclient import TestClient

    client = TestClient(app)
    SessionLocal = get_sessionmaker()
    R = get_redis()


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    failpoints.clear()
    os.environ["MEDCLIP_WORKSPACE_ROOT"] = str(tmp_path / "ws")
    R.delete(EXEC_STREAM)
    ensure_group(R)
    yield
    failpoints.clear()


def _run_until(task_id: str, want: str, ticks: int = 30) -> dict:
    """Tick the control plane until the task reaches `want` (or give up)."""
    status: dict = {}
    for _ in range(ticks):
        runner.tick(SessionLocal, R)
        status = client.get(f"/api/tasks/{task_id}").json()
        if status["task_state"] == want:
            return status
        time.sleep(0.1)
    return status


def test_e2e_mock_retrieval_completes():
    """API create -> dispatch -> lease -> spawned worker -> completed, with a
    gapless event trail."""
    ws = client.post("/api/workspaces").json()
    task = client.post("/api/tasks", json={"workspace_id": ws["workspace_id"]}).json()

    status = _run_until(task["task_id"], "completed")
    assert status["task_state"] == "completed", status
    assert status["attempt_state"] == "succeeded"
    assert status["job_state"] == "completed"

    events = client.get(f"/api/workspaces/{ws['workspace_id']}/events").json()
    seqs = [e["event_sequence"] for e in events]
    assert seqs == sorted(seqs) and seqs[0] == 1
    assert seqs == list(range(1, len(seqs) + 1)), "event sequence must be gapless"
    assert all(e["published"] for e in events), "publisher must have flushed all events"


def test_e2e_supervisor_crash_recovery():
    """Crash after lease-commit before ACK; the next ticks recover and finish
    with exactly one lease acquisition (no duplicate execution)."""
    ws = client.post("/api/workspaces").json()
    task = client.post("/api/tasks", json={"workspace_id": ws["workspace_id"]}).json()

    with SessionLocal() as s:
        from app.queue import dispatcher
        dispatcher.dispatch_pending(s, R)
    failpoints.arm("FP-EXEC-BEFORE-QUEUE-ACK")
    with SessionLocal() as s:
        with pytest.raises(failpoints.Failpoint):
            sup.consume_execution_queue(s, R, supervisor_id=runner.SUPERVISOR_ID)

    status = _run_until(task["task_id"], "completed")
    assert status["task_state"] == "completed", status
    assert status["lease_revision"] == 1, "recovery must not double-lease"


def test_event_gap_recovery_via_replay():
    ws = client.post("/api/workspaces").json()
    task = client.post("/api/tasks", json={"workspace_id": ws["workspace_id"]}).json()
    _run_until(task["task_id"], "completed")

    all_events = client.get(f"/api/workspaces/{ws['workspace_id']}/events").json()
    assert len(all_events) >= 2
    # A client that saw only event 1 recovers the rest, in order, gapless.
    tail = client.get(f"/api/workspaces/{ws['workspace_id']}/events", params={"after": 1}).json()
    assert [e["event_sequence"] for e in tail] == list(range(2, len(all_events) + 1))


def test_websocket_streams_events_with_replay():
    ws = client.post("/api/workspaces").json()
    task = client.post("/api/tasks", json={"workspace_id": ws["workspace_id"]}).json()
    _run_until(task["task_id"], "completed")

    with client.websocket_connect(f"/ws/{ws['workspace_id']}?after=0") as sock:
        first = sock.receive_json()
        second = sock.receive_json()
    assert first["event_sequence"] == 1
    assert second["event_sequence"] == 2

    # Unknown workspace is refused.
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{uuid.uuid4()}"):
            pass


def test_history_save_and_reopen_via_api():
    ws = client.post("/api/workspaces").json()
    saved = client.post("/api/history/save", json={
        "workspace_id": ws["workspace_id"], "title": "e2e case",
        "payload": {"finding": "mock"},
    }).json()
    rid = saved["history_record_id"]

    listed = client.get("/api/history", params={"workspace_id": ws["workspace_id"]}).json()
    assert [r["id"] for r in listed] == [rid]

    reopened = client.get(f"/api/history/{rid}").json()
    assert reopened["state"] == "ready" and reopened["title"] == "e2e case"

    # Non-existent record is invisible.
    assert client.get(f"/api/history/{uuid.uuid4()}").status_code == 404


def test_task_idempotency_via_api():
    ws = client.post("/api/workspaces").json()
    key = f"api-{uuid.uuid4()}"
    a = client.post("/api/tasks", json={
        "workspace_id": ws["workspace_id"], "idempotency_key": key}).json()
    b = client.post("/api/tasks", json={
        "workspace_id": ws["workspace_id"], "idempotency_key": key}).json()
    assert b["idempotent_reuse"] is True
    assert b["task_id"] == a["task_id"]
