"""Recovery Scanner (P4, SPEC-03 §4.6; IMP-EXEC-005/006/007).

Detects jobs whose lease expired or heartbeat went stale, atomically moves them
to `recovery_required`, marks the bound command `failed_retryable`, updates the
lease-recovery budget and recovery window, and republishes the command **with
the same generation** (normal faults never create a new Model Job or a new
generation).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import CommandOutbox, ModelJob
from ..queue import dispatcher
from .lease import HEARTBEAT_STALE_SECONDS

RECOVERY_WINDOW_SECONDS = 1800
MAX_CONSECUTIVE_RECOVERIES = 3
MAX_TOTAL_RECOVERIES = 10
STABLE_EXECUTION_RESET_SECONDS = 300

# Job states holding a lease that can go stale.
_LEASED_STATES = (
    "leased", "loading_model", "preprocessing", "running",
    "postprocessing", "finalizing_artifacts",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _expired(job: ModelJob) -> bool:
    now = _now()
    lease_gone = job.execution_lease_expires_at is None or job.execution_lease_expires_at <= now
    hb_stale = (
        job.supervisor_heartbeat_at is None
        or job.supervisor_heartbeat_at <= now - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
    )
    return lease_gone or hb_stale


def recover_expired_leases(session: Session, r: redis.Redis, *, limit: int = 50) -> list[uuid.UUID]:
    """One scanner pass. Returns the job ids sent into recovery + republished."""
    with session.begin():
        candidate_ids = list(
            session.execute(
                select(ModelJob.id).where(ModelJob.state.in_(_LEASED_STATES)).limit(limit)
            ).scalars()
        )

    recovered: list[uuid.UUID] = []
    for job_id in candidate_ids:
        command_id: uuid.UUID | None = None
        with session.begin():
            job = session.get(ModelJob, job_id, with_for_update=True)
            if job is None or job.state not in _LEASED_STATES or not _expired(job):
                continue
            # lease_suspect -> recovery_required (legal path through the machine)
            repo.transition(session, job, "model_job", "lease_suspect", actor="scanner")
            repo.transition(session, job, "model_job", "recovery_required", actor="scanner")

            cmd = session.execute(
                select(CommandOutbox)
                .where(
                    CommandOutbox.model_job_id == job.id,
                    CommandOutbox.command_generation == job.current_command_generation,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if cmd is not None and cmd.state not in (
                "resolved", "failed_final", "cancelled", "superseded"
            ):
                if cmd.state != "failed_retryable":
                    repo.transition(session, cmd, "command", "failed_retryable", actor="scanner")
                # Budgets (IMP-EXEC-005/007): lease recovery only — never mixes
                # with dispatch/delivery/execution counters.
                cmd.lease_recovery_attempts += 1
                cmd.total_recovery_attempts += 1
                cmd.consecutive_recovery_failures += 1
                cmd.last_recovery_at = _now()
                if cmd.recovery_window_started_at is None:
                    cmd.recovery_window_started_at = _now()
                command_id = cmd.id

            # Job returns to the queue for a fresh lease acquisition.
            repo.transition(session, job, "model_job", "queued", actor="scanner")

        if command_id is not None:
            # Republish reusing the SAME generation (SPEC-03 §4.6).
            with session.begin():
                cmd2 = session.get(CommandOutbox, command_id, with_for_update=True)
                if cmd2 is not None and cmd2.state == "failed_retryable":
                    repo.transition(session, cmd2, "command", "dispatching", actor="scanner")
            dispatcher.dispatch_one(session, r, command_id)
        recovered.append(job_id)
    return recovered


def note_stable_execution(session: Session, command_id: uuid.UUID) -> None:
    """IMP-EXEC-006: stable execution clears ONLY the consecutive counter."""
    with session.begin():
        cmd = session.get(CommandOutbox, command_id, with_for_update=True)
        if cmd is not None:
            cmd.consecutive_recovery_failures = 0
            # total_recovery_attempts / audit history intentionally untouched.
