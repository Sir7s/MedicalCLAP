"""Control-plane runner (P6): one tick drives the P3/P4 loops end-to-end.

tick() = dispatch pending commands -> supervisor consume + pending claim ->
publish outbox events. Tests call tick() deterministically; the backend can run
it continuously via a daemon thread (env MEDCLIP_RUN_CONTROLPLANE=1).
"""
from __future__ import annotations

import os
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..db.base import get_sessionmaker
from ..db.models import ModelJob
from ..logging_config import get_logger
from ..queue import dispatcher, publisher
from ..queue.redis_client import get_redis
from ..supervisor import consumer as sup
from ..supervisor import handshake as hs
from ..supervisor import scanner

log = get_logger("medclip.runner")

SUPERVISOR_ID = os.environ.get("MEDCLIP_SUPERVISOR_ID", "supervisor-main")


def execute_leased_jobs(SessionLocal: sessionmaker, *, limit: int = 4) -> int:
    """Run the P4 two-phase handshake + mock execution for jobs this supervisor
    leases. Returns the number of jobs completed."""
    with SessionLocal() as s:
        rows = s.execute(
            select(ModelJob.id, ModelJob.execution_lease_revision)
            .where(ModelJob.state == "leased",
                   ModelJob.worker_instance_id == SUPERVISOR_ID)
            .limit(limit)
        ).all()
        pairs = [(row[0], row[1]) for row in rows]
        s.rollback()

    done = 0
    for job_id, revision in pairs:
        with SessionLocal() as s:
            from ..db.models import CommandOutbox
            cmd_id = s.execute(
                select(CommandOutbox.id).where(
                    CommandOutbox.model_job_id == job_id,
                    CommandOutbox.state == "lease_acquired",
                ).limit(1)
            ).scalar_one_or_none()
            s.rollback()
        if cmd_id is None:
            continue
        handle = hs.spawn_worker(job_id, revision)
        try:
            hs.await_startup_ready(handle, timeout=30)
            hs.persist_execution_started(
                SessionLocal, command_id=cmd_id, supervisor_id=SUPERVISOR_ID,
                lease_revision=revision, pid=handle.process.pid or 0,
                child_uuid=handle.child_uuid, nonce=handle.nonce,
            )
            hs.send_begin_execution(handle)
            hs.run_to_completion(
                SessionLocal, handle, job_id=job_id, supervisor_id=SUPERVISOR_ID,
                lease_revision=revision, timeout=60,
            )
            done += 1
        except Exception:  # noqa: BLE001 - the scanner recovers stuck jobs
            log.exception("leased-job execution failed job=%s", job_id)
        finally:
            if handle.process.is_alive():
                handle.process.kill()
                handle.process.join(5)
    return done


def tick(SessionLocal: sessionmaker | None = None, r=None) -> dict:
    """Run one full control-plane cycle. Returns per-stage counts."""
    SessionLocal = SessionLocal or get_sessionmaker()
    r = r if r is not None else get_redis()
    out: dict[str, int] = {}
    with SessionLocal() as s:
        out["dispatched"] = dispatcher.dispatch_pending(s, r)
    with SessionLocal() as s:
        out["consumed"] = len(sup.consume_execution_queue(s, r, supervisor_id=SUPERVISOR_ID))
    with SessionLocal() as s:
        out["claimed"] = len(
            sup.claim_pending_execution(s, r, supervisor_id=SUPERVISOR_ID, min_idle_ms=30_000)
        )
    out["executed"] = execute_leased_jobs(SessionLocal)
    with SessionLocal() as s:
        out["recovered"] = len(scanner.recover_expired_leases(s, r))
    with SessionLocal() as s:
        out["published"] = publisher.publish_pending(s, r)
    return out


def start_background_runner(interval_seconds: float = 1.0) -> threading.Thread:
    """Daemon loop for the live demo; failures are logged, never fatal."""

    def _loop() -> None:
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001 - keep the demo loop alive
                log.exception("control-plane tick failed")
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, name="controlplane-runner", daemon=True)
    t.start()
    return t
