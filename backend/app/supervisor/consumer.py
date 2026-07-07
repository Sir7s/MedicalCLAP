"""Supervisor execution-queue consumer (P4, SPEC-03 §4.4; IMP-EXEC-003/004).

Consumption order:
    receive -> load command + job (locked) -> validate generation
    -> ATOMICALLY acquire lease + bind command  (one commit)
    -> ACK queue message
    (spawning the worker happens after ACK — see handshake.py)

Duplicate delivery (IMP-EXEC-003): a re-delivered message may be ACKed as a safe
duplicate ONLY when the command↔job binding, generation, lease owner, and lease
revision ALL match, the lease is unexpired, and the heartbeat is fresh. On any
other mismatch the job is marked `recovery_required` for the reconciler —
correctness is never guessed from the final state.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from sqlalchemy.orm import Session

from .. import failpoints
from ..db import repository as repo
from ..db.models import CommandOutbox, ModelJob, TaskAttempt
from ..queue.deadletter import dead_letter
from ..queue.redis_client import EXEC_STREAM, SUPERVISOR_GROUP, ensure_group
from .lease import lease_is_live


def _try_uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except (ValueError, TypeError):
        return None


def _ack(r: redis.Redis, msg_id: str) -> None:
    r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)


def process_execution_message(
    session: Session,
    r: redis.Redis,
    msg_id: str,
    fields: dict[str, str],
    *,
    supervisor_id: str,
    lease_ttl_seconds: int = 60,
) -> str:
    """Handle one queue message. Returns an outcome tag.

    Outcomes: 'leased' (fresh acquisition), 'duplicate' (safe re-delivery),
    'recovery_required', 'superseded', 'dead_letter'.
    """
    cid = _try_uuid(fields.get("command_id"))
    if cid is None:
        dead_letter(
            session, queue_name=EXEC_STREAM, error_code="PAYLOAD_UNPARSEABLE",
            detected_by=supervisor_id, original_message_id=msg_id, raw_payload=fields,
        )
        _ack(r, msg_id)
        return "dead_letter"

    # One locked transaction decides AND applies all state changes; the
    # dead-letter branches mutate nothing here and are persisted afterwards.
    outcome = "dead_letter"
    dl_code: str | None = None
    dl_job: str | None = None
    with session.begin():
        cmd = session.get(CommandOutbox, cid, with_for_update=True)
        job = (
            session.get(ModelJob, cmd.model_job_id, with_for_update=True)
            if cmd is not None
            else None
        )
        if cmd is None:
            dl_code = "COMMAND_NOT_FOUND"
        elif job is None:
            dl_code = "MODEL_JOB_NOT_FOUND"
            dl_job = str(cmd.model_job_id)
        else:
            msg_gen = int(fields.get("command_generation", "-1"))
            if msg_gen > job.current_command_generation:
                # IMP-EXEC-004: message ahead of the control plane — anomaly.
                dl_code = "GENERATION_AHEAD"
                dl_job = str(job.id)
            elif msg_gen < job.current_command_generation:
                repo.append_audit(
                    session, actor=supervisor_id, action="command_superseded",
                    aggregate_type="command", aggregate_id=str(cid),
                    detail={"msg_generation": msg_gen,
                            "current": job.current_command_generation},
                )
                outcome = "superseded"
            elif cmd.state in ("lease_acquired", "execution_started", "resolved"):
                # Re-delivery of an already-leased command (IMP-EXEC-003).
                safe = (
                    cmd.model_job_id == job.id
                    and cmd.command_generation == job.current_command_generation
                    and cmd.acquired_lease_revision == job.execution_lease_revision
                    and cmd.lease_owner_instance_id == job.worker_instance_id
                    and lease_is_live(job)
                )
                if safe:
                    repo.append_audit(
                        session, actor=supervisor_id, action="duplicate_message_acked",
                        aggregate_type="command", aggregate_id=str(cid),
                        detail={"lease_revision": job.execution_lease_revision},
                    )
                    outcome = "duplicate"
                else:
                    # Never guess: hand the job to the reconciler.
                    if job.state not in ("recovery_required", "queued"):
                        if job.state != "lease_suspect":
                            repo.transition(session, job, "model_job", "lease_suspect",
                                            actor=supervisor_id)
                        repo.transition(session, job, "model_job", "recovery_required",
                                        actor=supervisor_id)
                    outcome = "recovery_required"
            elif job.state == "queued" and cmd.state in ("dispatched", "dispatching", "pending"):
                # ATOMIC: lease acquisition + command binding (SPEC-03 §4.4).
                now = datetime.now(UTC)
                job.execution_lease_revision += 1
                job.worker_instance_id = supervisor_id
                job.supervisor_heartbeat_at = now
                job.execution_lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
                repo.transition(session, job, "model_job", "leased", actor=supervisor_id)

                if cmd.state == "pending":
                    repo.transition(session, cmd, "command", "dispatching",
                                    actor=supervisor_id, write_audit=False)
                if cmd.state == "dispatching":
                    repo.transition(session, cmd, "command", "dispatched",
                                    actor=supervisor_id, write_audit=False)
                repo.transition(session, cmd, "command", "worker_received",
                                actor=supervisor_id, write_audit=False)
                repo.transition(session, cmd, "command", "lease_acquired",
                                actor=supervisor_id)
                cmd.acquired_lease_revision = job.execution_lease_revision
                cmd.lease_owner_instance_id = supervisor_id
                cmd.delivery_attempts += 1

                attempt = session.get(TaskAttempt, cmd.attempt_id, with_for_update=True)
                if attempt is not None and attempt.state == "command_pending":
                    repo.transition(session, attempt, "attempt", "dispatched",
                                    actor=supervisor_id, write_audit=False)
                    repo.transition(session, attempt, "attempt", "lease_acquired",
                                    actor=supervisor_id)
                outcome = "leased"
            else:
                dl_code = "BINDING_INCONSISTENT"
                dl_job = str(job.id)

    if dl_code is not None:
        dead_letter(
            session, queue_name=EXEC_STREAM, error_code=dl_code,
            detected_by=supervisor_id, original_message_id=msg_id, command_id=cid,
            model_job_id=dl_job, raw_payload=fields,
        )
        _ack(r, msg_id)
        return "dead_letter"

    if outcome == "leased":
        # Lease is durable. A crash HERE (before ACK) is FR-EXEC-003 — the
        # broker re-delivers and the safe-duplicate path ACKs without a
        # second lease acquisition.
        failpoints.trip("FP-EXEC-BEFORE-QUEUE-ACK")

    _ack(r, msg_id)
    return outcome


def consume_execution_queue(
    session: Session,
    r: redis.Redis,
    *,
    supervisor_id: str,
    consumer_name: str = "supervisor-1",
    count: int = 10,
    block_ms: int = 200,
) -> list[str]:
    """Read a batch from the execution stream and process each message."""
    ensure_group(r)
    resp: Any = r.xreadgroup(
        SUPERVISOR_GROUP, consumer_name, {EXEC_STREAM: ">"}, count=count, block=block_ms
    )
    outcomes: list[str] = []
    for _stream, entries in resp or []:
        for msg_id, fields in entries:
            outcomes.append(
                process_execution_message(session, r, msg_id, fields, supervisor_id=supervisor_id)
            )
    return outcomes


def claim_pending_execution(
    session: Session,
    r: redis.Redis,
    *,
    supervisor_id: str,
    consumer_name: str = "supervisor-recovery",
    min_idle_ms: int = 0,
    count: int = 50,
) -> list[str]:
    """Reclaim messages abandoned by a crashed supervisor and reprocess them."""
    ensure_group(r)
    result: Any = r.xautoclaim(
        EXEC_STREAM, SUPERVISOR_GROUP, consumer_name,
        min_idle_time=min_idle_ms, start_id="0-0", count=count,
    )
    outcomes: list[str] = []
    for msg_id, fields in result[1]:
        if fields:
            outcomes.append(
                process_execution_message(session, r, msg_id, fields, supervisor_id=supervisor_id)
            )
        else:
            _ack(r, msg_id)
    return outcomes
