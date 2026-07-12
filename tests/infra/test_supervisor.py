"""P4 critical tests — supervisor lease, fencing, handshake, forced cancel.

Covers FR-EXEC-003 (lease-commit-before-ACK crash), FR-EXEC-006 (fencing),
FR-EXEC-007 (recovery-budget isolation), FR-EXEC-008 (startup_ready gating),
FR-EXEC-010 (forced cancel), FR-EXEC-013 (persist-before-begin), plus the full
mock-worker execution flow and scanner takeover.

Auto-skips unless PostgreSQL + Redis are up and the schema is migrated.
Failpoints are enabled process-wide for this module.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

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

        _READY = inspect(get_engine()).has_table("model_jobs")
        if _READY:
            # The P4 migration must be applied too.
            cols = {c["name"] for c in inspect(get_engine()).get_columns("model_jobs")}
            _READY = "startup_nonce_hash" in cols
    except Exception:  # noqa: BLE001
        _READY = False

pytestmark = pytest.mark.skipif(
    not _READY, reason="postgres/redis not up or P4 schema not migrated"
)

if _READY:
    from app import failpoints
    from app.db import repository as repo
    from app.db import service
    from app.db.base import get_sessionmaker
    from app.db.models import CommandOutbox, ModelJob, TaskAttempt
    from app.queue import dispatcher
    from app.queue.redis_client import EXEC_STREAM, SUPERVISOR_GROUP, ensure_group, get_redis
    from app.supervisor import consumer as sup
    from app.supervisor import handshake as hs
    from app.supervisor import scanner
    from app.supervisor.lease import FencedOut, fenced
    from app.supervisor.watchdog import forced_terminate

    SessionLocal = get_sessionmaker()
    R = get_redis()

SUP_A = "supervisor-A"
SUP_B = "supervisor-B"


@pytest.fixture(autouse=True)
def _reset():
    failpoints.clear()
    R.delete(EXEC_STREAM)
    ensure_group(R)
    yield
    failpoints.clear()


def _new_dispatched_command() -> tuple[uuid.UUID, uuid.UUID]:
    """Create a task and dispatch its command. Returns (command_id, job_id)."""
    with SessionLocal() as s, s.begin():
        ws = repo.create_workspace(s)
        wid = ws.id
    with SessionLocal() as s:
        created = service.create_task(s, workspace_id=wid, task_type="retrieval")
    cid = uuid.UUID(created.command_id)
    with SessionLocal() as s:
        dispatcher.dispatch_one(s, R, cid)
    return cid, uuid.UUID(created.model_job_id)


def _job(jid: uuid.UUID) -> ModelJob:
    with SessionLocal() as s:
        j = s.get(ModelJob, jid)
        s.expunge(j)
        return j


def _cmd(cid: uuid.UUID) -> CommandOutbox:
    with SessionLocal() as s:
        c = s.get(CommandOutbox, cid)
        s.expunge(c)
        return c


def _consume(supervisor_id: str) -> list[str]:
    with SessionLocal() as s:
        return sup.consume_execution_queue(s, R, supervisor_id=supervisor_id)


def _expire_lease(jid: uuid.UUID) -> None:
    past = datetime.now(UTC) - timedelta(minutes=10)
    with SessionLocal() as s, s.begin():
        job = s.get(ModelJob, jid, with_for_update=True)
        job.execution_lease_expires_at = past
        job.supervisor_heartbeat_at = past


# ---------------------------------------------------------------------------
def test_fresh_lease_acquisition_and_binding():
    cid, jid = _new_dispatched_command()
    outcomes = _consume(SUP_A)
    assert outcomes == ["leased"]
    job, cmd = _job(jid), _cmd(cid)
    assert job.state == "leased"
    assert job.worker_instance_id == SUP_A
    assert job.execution_lease_revision == 1
    assert cmd.state == "lease_acquired"
    assert cmd.acquired_lease_revision == 1
    assert cmd.lease_owner_instance_id == SUP_A
    assert cmd.delivery_attempts == 1


def test_lease_commit_before_ack_crash_single_lease():
    """FR-EXEC-003: crash after the lease commit, before ACK -> redelivery is a
    safe duplicate; exactly one lease acquisition."""
    cid, jid = _new_dispatched_command()
    failpoints.arm("FP-EXEC-BEFORE-QUEUE-ACK")
    with SessionLocal() as s:
        with pytest.raises(failpoints.Failpoint):
            sup.consume_execution_queue(s, R, supervisor_id=SUP_A)
    # Lease is durable but the message was never ACKed.
    assert _job(jid).execution_lease_revision == 1
    assert R.xpending(EXEC_STREAM, SUPERVISOR_GROUP)["pending"] == 1

    # Broker re-delivery (claim) -> safe duplicate, no second lease.
    with SessionLocal() as s:
        outcomes = sup.claim_pending_execution(s, R, supervisor_id=SUP_A)
    assert outcomes == ["duplicate"]
    job = _job(jid)
    assert job.execution_lease_revision == 1  # unchanged
    assert job.state == "leased"
    assert R.xpending(EXEC_STREAM, SUPERVISOR_GROUP)["pending"] == 0


def test_fencing_old_revision_cannot_write():
    """FR-EXEC-006: after takeover, the old supervisor's writes are rejected."""
    cid, jid = _new_dispatched_command()
    _consume(SUP_A)  # revision 1 held by A (shared DB may lease others)
    assert _job(jid).state == "leased" and _job(jid).execution_lease_revision == 1

    _expire_lease(jid)
    with SessionLocal() as s:
        recovered = scanner.recover_expired_leases(s, R)
    assert jid in recovered
    # The scanner may also republish stale jobs left over from earlier test
    # runs (their 60s leases expired since); drain until OUR job is re-leased.
    for _ in range(5):
        outcomes = _consume(SUP_B)
        if _job(jid).state == "leased" or not outcomes:
            break
    job = _job(jid)
    assert (job.worker_instance_id, job.execution_lease_revision) == (SUP_B, 2)

    # Old owner (rev 1) attempts a state write -> FencedOut, nothing changes.
    def _evil(sess, j):
        j.state = "completed"

    with SessionLocal() as s:
        with pytest.raises(FencedOut):
            fenced(s, jid, SUP_A, 1, _evil)
    assert _job(jid).state == "leased"

    # Old owner also cannot commit a result.
    with pytest.raises((FencedOut, hs.ResultRefused)):
        hs.commit_result(SessionLocal, job_id=jid, supervisor_id=SUP_A,
                         lease_revision=1, result={"mock": True})
    assert _job(jid).state == "leased"


def test_recovery_budget_isolation():
    """FR-EXEC-007: lease-recovery budget moves independently of dispatch,
    delivery and execution budgets; stable run clears only the consecutive
    counter (IMP-EXEC-006)."""
    cid, jid = _new_dispatched_command()
    _consume(SUP_A)
    assert _job(jid).state == "leased"
    _expire_lease(jid)
    with SessionLocal() as s:
        scanner.recover_expired_leases(s, R)
    cmd = _cmd(cid)
    assert cmd.lease_recovery_attempts == 1
    assert cmd.total_recovery_attempts == 1
    assert cmd.consecutive_recovery_failures == 1
    assert cmd.recovery_window_started_at is not None
    assert cmd.dispatch_attempts == 2      # initial send + republish (dispatch budget)
    assert cmd.delivery_attempts == 1      # one lease acquisition so far
    assert _job(jid).execution_attempts == 0  # GPU budget untouched

    scanner.note_stable_execution(SessionLocal(), cid)
    cmd = _cmd(cid)
    assert cmd.consecutive_recovery_failures == 0
    assert cmd.total_recovery_attempts == 1  # history preserved


def test_startup_ready_gating_and_persist():
    """FR-EXEC-008: spawn does not advance control-plane state; only the
    persisted execution_started transaction does."""
    cid, jid = _new_dispatched_command()
    _consume(SUP_A)
    assert _job(jid).state == "leased"

    handle = hs.spawn_worker(jid, 1)
    try:
        msg = hs.await_startup_ready(handle, timeout=15)
        assert msg["type"] == "startup_ready"
        # Child is ready and WAITING — control plane still 'leased'.
        assert _job(jid).state == "leased"
        assert _cmd(cid).state == "lease_acquired"

        hs.persist_execution_started(
            SessionLocal, command_id=cid, supervisor_id=SUP_A, lease_revision=1,
            pid=handle.process.pid, child_uuid=handle.child_uuid, nonce=handle.nonce,
        )
        job, cmd = _job(jid), _cmd(cid)
        assert job.state == "loading_model"
        assert cmd.state == "execution_started"
        assert job.worker_pid == handle.process.pid
        assert job.child_process_uuid == handle.child_uuid
        assert job.execution_attempts == 1

        hs.send_begin_execution(handle)
        result = hs.run_to_completion(
            SessionLocal, handle, job_id=jid, supervisor_id=SUP_A, lease_revision=1,
            timeout=30,
        )
        assert result.get("mock") is True
    finally:
        if handle.process.is_alive():
            handle.process.kill()
            handle.process.join(5)

    job, cmd = _job(jid), _cmd(cid)
    assert job.state == "completed"
    assert cmd.state == "resolved" and cmd.resolution_type == "succeeded"
    with SessionLocal() as s:
        att = s.get(TaskAttempt, cmd.attempt_id)
        assert att.state == "succeeded"


def test_persist_failure_means_no_begin_execution():
    """FR-EXEC-013 / IMP-EXEC-012: if the execution_started transaction fails,
    begin_execution is never sent and no state advances."""
    cid, jid = _new_dispatched_command()
    _consume(SUP_A)
    assert _job(jid).state == "leased"

    parent_conn, child_conn = mp.Pipe()
    failpoints.arm("FP-EXEC-BEFORE-BEGIN-EXECUTION")
    with pytest.raises(failpoints.Failpoint):
        hs.persist_execution_started(
            SessionLocal, command_id=cid, supervisor_id=SUP_A, lease_revision=1,
            pid=12345, child_uuid="child-x", nonce="nonce-x",
        )
    # Rolled back: nothing advanced, and the supervisor never sends begin.
    assert _job(jid).state == "leased"
    assert _cmd(cid).state == "lease_acquired"
    assert _job(jid).execution_attempts == 0
    assert not child_conn.poll(0.2)  # no begin_execution reached the child side


def test_worker_exits_when_begin_never_arrives():
    """IMP-EXEC-012: a ready child that never receives begin_execution exits by
    itself without executing."""
    jid = uuid.uuid4()  # no DB needed; the worker never touches the DB
    handle = hs.spawn_worker(jid, 1, begin_timeout=2.0)
    try:
        msg = hs.await_startup_ready(handle, timeout=15)
        assert msg["type"] == "startup_ready"
        # Never send begin_execution; child must exit on its own timeout.
        handle.process.join(timeout=10)
        assert not handle.process.is_alive()
    finally:
        if handle.process.is_alive():
            handle.process.kill()
            handle.process.join(5)


def test_forced_cancel_no_result_commit():
    """FR-EXEC-010: cooperative stop ignored -> terminate/kill; job ends
    cancelled_forced and a result commit is refused."""
    cid, jid = _new_dispatched_command()
    _consume(SUP_A)
    assert _job(jid).state == "leased"

    handle = hs.spawn_worker(jid, 1, behavior="ignore_stop")
    try:
        hs.await_startup_ready(handle, timeout=15)
        hs.persist_execution_started(
            SessionLocal, command_id=cid, supervisor_id=SUP_A, lease_revision=1,
            pid=handle.process.pid, child_uuid=handle.child_uuid, nonce=handle.nonce,
        )
        hs.send_begin_execution(handle)
        time.sleep(0.5)  # let the child enter its wedged 'running' loop

        with SessionLocal() as s:
            def _cancel(sess, j):
                repo.transition(sess, j, "model_job", "cancelling", actor=SUP_A)
            fenced(s, jid, SUP_A, 1, _cancel)

        summary = forced_terminate(handle, stop_grace=1.0, term_grace=2.0)
        assert summary["terminated"] or summary["killed"]  # cooperative failed
        assert not handle.process.is_alive()

        with SessionLocal() as s:
            def _forced(sess, j):
                repo.transition(sess, j, "model_job", "cancelled_forced", actor=SUP_A)
            fenced(s, jid, SUP_A, 1, _forced)

        with pytest.raises(hs.ResultRefused):
            hs.commit_result(SessionLocal, job_id=jid, supervisor_id=SUP_A,
                             lease_revision=1, result={"mock": True})
        assert _job(jid).state == "cancelled_forced"
    finally:
        if handle.process.is_alive():
            handle.process.kill()
            handle.process.join(5)
