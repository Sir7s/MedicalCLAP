"""Execution lease ownership and fencing (P4, SPEC-03 §4.3/§4.5).

The Model Job Supervisor is the **unique lease owner**: acquiring the lease,
renewing the heartbeat, and every critical write all go through this module,
and every write re-validates `(worker_instance_id, execution_lease_revision)`
inside the same transaction. A supervisor holding a stale revision receives
`FencedOut` and changes nothing — even if it is still running.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import ModelJob

DEFAULT_LEASE_TTL_SECONDS = 60
HEARTBEAT_STALE_SECONDS = 30


class FencedOut(RuntimeError):
    """A write was attempted under a lease that is no longer current."""


class LeaseUnavailable(RuntimeError):
    """The job is not in a leasable state."""


def _now() -> datetime:
    return datetime.now(UTC)


def acquire_lease(
    session: Session,
    job_id: uuid.UUID,
    supervisor_id: str,
    *,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> int:
    """Atomically acquire the execution lease. Returns the new lease revision.

    Job must be `queued` (fresh) — takeover paths re-queue via the recovery
    scanner first, so there is exactly one acquisition door (SPEC-03 §4.3).
    """
    with session.begin():
        job = session.get(ModelJob, job_id, with_for_update=True)
        if job is None:
            raise LeaseUnavailable(f"model job {job_id} not found")
        if job.state != "queued":
            raise LeaseUnavailable(f"model job {job_id} not leasable (state={job.state})")
        job.execution_lease_revision += 1
        job.worker_instance_id = supervisor_id
        job.supervisor_heartbeat_at = _now()
        job.execution_lease_expires_at = _now() + timedelta(seconds=ttl_seconds)
        repo.transition(session, job, "model_job", "leased", actor=supervisor_id)
        return job.execution_lease_revision


def fenced(
    session: Session,
    job_id: uuid.UUID,
    supervisor_id: str,
    lease_revision: int,
    mutate: Callable[[Session, ModelJob], None],
) -> None:
    """Run `mutate` on the locked job iff the caller still owns the lease.

    Fencing check (SPEC-03 §4.5): owner id AND revision must match the row —
    revision alone is not enough, a newer owner may reuse the id string.
    Raises FencedOut and leaves the transaction rolled back otherwise.
    """
    with session.begin():
        job = session.get(ModelJob, job_id, with_for_update=True)
        if job is None:
            raise FencedOut(f"model job {job_id} not found")
        if (
            job.worker_instance_id != supervisor_id
            or job.execution_lease_revision != lease_revision
        ):
            raise FencedOut(
                f"stale lease for job {job_id}: "
                f"held=({supervisor_id}, rev {lease_revision}) "
                f"current=({job.worker_instance_id}, rev {job.execution_lease_revision})"
            )
        mutate(session, job)


def renew_heartbeat(
    session: Session,
    job_id: uuid.UUID,
    supervisor_id: str,
    lease_revision: int,
    *,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> None:
    def _renew(_s: Session, job: ModelJob) -> None:
        job.supervisor_heartbeat_at = _now()
        job.execution_lease_expires_at = _now() + timedelta(seconds=ttl_seconds)

    fenced(session, job_id, supervisor_id, lease_revision, _renew)


def lease_is_live(job: ModelJob, *, stale_seconds: int = HEARTBEAT_STALE_SECONDS) -> bool:
    """Lease validity per IMP-EXEC-003: unexpired AND heartbeat fresh."""
    now = _now()
    if job.execution_lease_expires_at is None or job.supervisor_heartbeat_at is None:
        return False
    return (
        job.execution_lease_expires_at > now
        and job.supervisor_heartbeat_at > now - timedelta(seconds=stale_seconds)
    )
