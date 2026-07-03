"""P3 critical tests — command dispatch, event publish, dead-letter, dedup.

Covers Freeze Profile FR-EXEC-001 (commit crash), FR-EXEC-002 (send-before-mark),
FR-EXEC-005 (duplicate message), FR-EXEC-011 (dead-letter), plus pending-claim
recovery and event publishing.

Auto-skips unless PostgreSQL + Redis are up and the schema is migrated. Runs in
the compose CI lane. Failpoints are enabled process-wide for this module only.
"""
from __future__ import annotations

import os
import socket
import uuid

import pytest

os.environ["MEDCLIP_FAILPOINTS"] = "1"  # enable crash injection for this module

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

        _READY = inspect(get_engine()).has_table("workspace_sessions")
    except Exception:  # noqa: BLE001
        _READY = False

pytestmark = pytest.mark.skipif(
    not _READY, reason="postgres/redis not up or schema not migrated"
)

if _READY:
    from app import failpoints
    from app.db import repository as repo
    from app.db import service
    from app.db.base import get_sessionmaker
    from app.db.models import CommandOutbox, DeadLetterCommand, OutboxEvent
    from app.queue import consumer as consumer_mod
    from app.queue import dispatcher, publisher
    from app.queue.redis_client import (
        EVENT_STREAM,
        EXEC_STREAM,
        SUPERVISOR_GROUP,
        ensure_group,
        get_redis,
    )

    SessionLocal = get_sessionmaker()
    R = get_redis()


@pytest.fixture(autouse=True)
def _reset_streams():
    failpoints.clear()
    R.delete(EXEC_STREAM, EVENT_STREAM)
    ensure_group(R)
    yield
    failpoints.clear()


def _new_command() -> uuid.UUID:
    with SessionLocal() as s, s.begin():
        ws = repo.create_workspace(s)
        wid = ws.id
    with SessionLocal() as s:
        created = service.create_task(s, workspace_id=wid, task_type="retrieval")
    return uuid.UUID(created.command_id)


def _command_state(cid: uuid.UUID) -> str:
    with SessionLocal() as s:
        return s.get(CommandOutbox, cid).state


def _pending_count() -> int:
    return R.xpending(EXEC_STREAM, SUPERVISOR_GROUP)["pending"]


def test_commit_crash_command_not_lost():
    """FR-EXEC-001: a committed 'pending' command survives and is delivered once."""
    cid = _new_command()
    assert _command_state(cid) == "pending"
    assert R.xlen(EXEC_STREAM) == 0
    with SessionLocal() as s:
        assert dispatcher.dispatch_one(s, R, cid) is True
    assert _command_state(cid) == "dispatched"
    assert R.xlen(EXEC_STREAM) == 1


def test_scanner_recovers_pending_commands():
    """The dispatcher scan picks up committed 'pending' commands (recovery)."""
    cid = _new_command()
    with SessionLocal() as s:
        sent = dispatcher.dispatch_pending(s, R)
    assert sent >= 1  # shared DB may hold other pending commands too
    assert _command_state(cid) == "dispatched"


def test_send_before_mark_recovers_single_effect():
    """FR-EXEC-002: crash after XADD before 'dispatched' -> recovered, one effect."""
    cid = _new_command()
    failpoints.arm("FP-EXEC-AFTER-QUEUE-SEND")
    with SessionLocal() as s:
        with pytest.raises(failpoints.Failpoint):
            dispatcher.dispatch_one(s, R, cid)
    # Message was sent but the command is still 'dispatching'.
    assert _command_state(cid) == "dispatching"
    assert R.xlen(EXEC_STREAM) == 1

    # Recovery re-dispatches the stuck command (second delivery) and marks it done.
    with SessionLocal() as s:
        assert dispatcher.dispatch_one(s, R, cid) is True
    assert _command_state(cid) == "dispatched"
    assert R.xlen(EXEC_STREAM) == 2  # duplicate delivery

    with SessionLocal() as s:
        outcomes = consumer_mod.consume_once(s, R)
    assert outcomes.count("processed") == 1, outcomes
    assert outcomes.count("duplicate") == 1, outcomes


def test_duplicate_message_deduped():
    """FR-EXEC-005: duplicate delivery -> exactly one processed."""
    cid = _new_command()
    with SessionLocal() as s:
        dispatcher.dispatch_one(s, R, cid)
    # Inject a duplicate of the same command message.
    R.xadd(EXEC_STREAM, {
        "command_id": str(cid), "model_job_id": "x", "attempt_id": "x",
        "command_generation": "0", "payload": "{}",
    })
    assert R.xlen(EXEC_STREAM) == 2
    with SessionLocal() as s:
        outcomes = consumer_mod.consume_once(s, R)
    assert outcomes.count("processed") == 1
    assert outcomes.count("duplicate") == 1


def test_dead_letter_missing_command():
    """FR-EXEC-011: message for a non-existent command -> dead-letter + ACK."""
    ghost = uuid.uuid4()
    R.xadd(EXEC_STREAM, {
        "command_id": str(ghost), "model_job_id": "x", "attempt_id": "x",
        "command_generation": "0", "payload": "{}",
    })
    with SessionLocal() as s:
        outcomes = consumer_mod.consume_once(s, R)
    assert outcomes == ["dead_letter"]
    with SessionLocal() as s:
        row = s.query(DeadLetterCommand).filter_by(command_id=ghost).one()
        assert row.error_code == "COMMAND_NOT_FOUND"
        assert row.resolution_status == "unresolved"
    assert _pending_count() == 0  # message was ACKed, no infinite retry


def test_dead_letter_unparseable_payload():
    R.xadd(EXEC_STREAM, {"command_id": "not-a-uuid", "payload": "{}"})
    with SessionLocal() as s:
        outcomes = consumer_mod.consume_once(s, R)
    assert outcomes == ["dead_letter"]
    assert _pending_count() == 0


def test_pending_claim_reprocesses_abandoned_message():
    """A message read by a crashed consumer is reclaimed and processed."""
    cid = _new_command()
    with SessionLocal() as s:
        dispatcher.dispatch_one(s, R, cid)
    # Consumer "A" reads but never ACKs (simulated crash).
    R.xreadgroup(SUPERVISOR_GROUP, "A", {EXEC_STREAM: ">"}, count=1)
    assert _pending_count() == 1
    # Recovery consumer reclaims and processes it.
    with SessionLocal() as s:
        outcomes = consumer_mod.claim_pending(s, R, min_idle_ms=0)
    assert outcomes == ["processed"]
    assert _pending_count() == 0


def test_publisher_publishes_events():
    with SessionLocal() as s, s.begin():
        ws = repo.create_workspace(s)
        wid = ws.id
    with SessionLocal() as s:
        service.create_task(s, workspace_id=wid, task_type="retrieval")
    before = R.xlen(EVENT_STREAM)
    with SessionLocal() as s:
        sent = publisher.publish_pending(s, R)
    assert sent >= 1
    assert R.xlen(EVENT_STREAM) == before + sent
    with SessionLocal() as s:
        unpublished = s.query(OutboxEvent).filter_by(workspace_id=wid, published=False).count()
    assert unpublished == 0
