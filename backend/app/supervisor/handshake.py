"""Two-phase GPU startup handshake — supervisor side (P4, IMP-EXEC-010..013).

    spawn child -> child startup_ready
    -> persist execution_started (single fenced transaction, IMP-EXEC-011)
    -> ONLY on commit success: send begin_execution (IMP-EXEC-012/013)
    -> consume stage/result messages (validated per IMP-EXEC-009)
    -> fenced result commit (refused after cancel / from a stale lease)
"""
from __future__ import annotations

import multiprocessing as mp
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import failpoints
from ..db import repository as repo
from ..db.models import ApplicationTask, CommandOutbox, ModelJob, OutboxEvent, TaskAttempt
from .ipc import IpcValidator, new_child_identity, nonce_hash
from .lease import fenced
from .worker import mock_worker_main

STARTUP_READY_TIMEOUT_SECONDS = 30.0


class HandshakeError(RuntimeError):
    pass


class ResultRefused(RuntimeError):
    """A result commit was refused (cancelled job or stale lease)."""


@dataclass
class WorkerHandle:
    process: mp.process.BaseProcess  # SpawnProcess from the spawn context
    conn: Any  # parent end of the duplex pipe
    validator: IpcValidator
    nonce: str
    child_uuid: str


def spawn_worker(
    model_job_id: uuid.UUID,
    lease_revision: int,
    *,
    behavior: str = "normal",
    begin_timeout: float = 20.0,
) -> WorkerHandle:
    """Spawn the mock GPU worker with a fresh nonce + child UUID (IMP-EXEC-008)."""
    nonce, child_uuid = new_child_identity()
    ctx = mp.get_context("spawn")  # SPEC-03 §4.8: multiprocessing spawn
    parent_conn, child_conn = ctx.Pipe(duplex=True)
    proc = ctx.Process(
        target=mock_worker_main,
        args=(child_conn, str(model_job_id), lease_revision, nonce, child_uuid,
              behavior, begin_timeout),
        daemon=True,
    )
    proc.start()
    validator = IpcValidator(
        model_job_id=str(model_job_id),
        lease_revision=lease_revision,
        nonce=nonce,
        child_uuid=child_uuid,
    )
    return WorkerHandle(proc, parent_conn, validator, nonce, child_uuid)


def await_startup_ready(
    handle: WorkerHandle, *, timeout: float = STARTUP_READY_TIMEOUT_SECONDS
) -> dict:
    """Wait for a VALID startup_ready; invalid messages are dropped, not applied."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        if not handle.conn.poll(remaining):
            break
        msg = handle.conn.recv()
        ok, _reason = handle.validator.validate(msg)
        if not ok:
            if handle.validator.should_terminate_child:
                handle.process.terminate()
                raise HandshakeError("too many invalid IPC messages during startup")
            continue
        if msg.get("type") == "startup_ready":
            return msg
    raise HandshakeError("startup_ready not received before timeout")


def persist_execution_started(
    SessionLocal: sessionmaker,
    *,
    command_id: uuid.UUID,
    supervisor_id: str,
    lease_revision: int,
    pid: int,
    child_uuid: str,
    nonce: str,
) -> None:
    """The durable transaction of IMP-EXEC-011 — all eight steps, one commit.

    Raises on any failure; the caller MUST NOT send begin_execution then
    (IMP-EXEC-012/013).
    """
    with SessionLocal() as session, session.begin():
        cmd = session.get(CommandOutbox, command_id, with_for_update=True)
        if cmd is None:
            raise HandshakeError(f"command {command_id} not found")
        job = session.get(ModelJob, cmd.model_job_id, with_for_update=True)
        if job is None:
            raise HandshakeError(f"model job {cmd.model_job_id} not found")
        # Step 2 — validate the current lease under lock (fencing inline).
        if (
            job.worker_instance_id != supervisor_id
            or job.execution_lease_revision != lease_revision
        ):
            raise HandshakeError("lease no longer current; refusing execution start")

        attempt = session.get(TaskAttempt, cmd.attempt_id, with_for_update=True)
        if attempt is None:
            raise HandshakeError(f"attempt {cmd.attempt_id} not found")

        # Steps 3-5 — command/attempt/job state advances (and the parent task
        # enters running: SPEC-02 task machine is driven by the control plane).
        repo.transition(session, cmd, "command", "execution_started", actor=supervisor_id)
        repo.transition(session, attempt, "attempt", "running", actor=supervisor_id)
        repo.transition(session, job, "model_job", "loading_model", actor=supervisor_id)
        parent_task = session.get(ApplicationTask, attempt.task_id, with_for_update=True)
        if parent_task is not None and parent_task.state == "queued":
            repo.transition(session, parent_task, "task", "running", actor=supervisor_id)

        # Step 6 — bind the concrete child (nonce stored only as a hash).
        job.worker_pid = pid
        job.child_process_uuid = child_uuid
        job.startup_nonce_hash = nonce_hash(nonce)
        job.execution_attempts += 1  # IMP-EXEC-007: the GPU-execution budget

        # Step 7 — event outbox row (same transaction).
        task = session.get(ApplicationTask, attempt.task_id)
        if task is None:
            raise HandshakeError(f"task {attempt.task_id} not found")
        repo.lock_workspace(session, task.workspace_id)
        seq = repo.next_event_sequence(session, task.workspace_id)
        session.add(
            OutboxEvent(
                workspace_id=task.workspace_id,
                aggregate_type="model_job",
                aggregate_id=str(job.id),
                event_type="execution_started",
                event_sequence=seq,
                payload={"pid": pid, "lease_revision": lease_revision},
            )
        )

        # Test-only crash point: persist failure ⇒ rollback ⇒ no begin_execution.
        failpoints.trip("FP-EXEC-BEFORE-BEGIN-EXECUTION")
        # Step 8 — commit happens on context exit.


def send_begin_execution(handle: WorkerHandle) -> None:
    handle.conn.send({"type": "begin_execution"})


_STAGE_TO_JOB_STATE = {
    "preprocessing": "preprocessing",
    "running": "running",
    "postprocessing": "postprocessing",
    "finalizing_artifacts": "finalizing_artifacts",
}


def run_to_completion(
    SessionLocal: sessionmaker,
    handle: WorkerHandle,
    *,
    job_id: uuid.UUID,
    supervisor_id: str,
    lease_revision: int,
    timeout: float = 60.0,
) -> dict:
    """Consume validated stage/result messages, advancing the job state through
    fenced writes, and commit the final result. Returns the result payload."""
    import time

    result_payload: dict | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        if not handle.conn.poll(remaining):
            break
        msg = handle.conn.recv()
        ok, _reason = handle.validator.validate(msg)
        if not ok:
            continue
        mtype = msg.get("type")
        if mtype == "stage":
            stage = msg["payload"]["stage"]
            new_state = _STAGE_TO_JOB_STATE.get(stage)
            if new_state:
                with SessionLocal() as session:
                    def _advance(s: Session, job: ModelJob, ns=new_state) -> None:
                        repo.transition(s, job, "model_job", ns, actor=supervisor_id)

                    fenced(session, job_id, supervisor_id, lease_revision, _advance)
        elif mtype == "result":
            result_payload = msg["payload"].get("result", {})
        elif mtype == "exiting":
            break

    if result_payload is None:
        raise HandshakeError("worker exited without a result")
    commit_result(
        SessionLocal,
        job_id=job_id,
        supervisor_id=supervisor_id,
        lease_revision=lease_revision,
        result=result_payload,
    )
    handle.process.join(timeout=10)
    return result_payload


def commit_result(
    SessionLocal: sessionmaker,
    *,
    job_id: uuid.UUID,
    supervisor_id: str,
    lease_revision: int,
    result: dict,
) -> None:
    """Fenced final commit: job -> completed, attempt -> succeeded, command ->
    resolved(succeeded). Refused for cancelled/foreign jobs (FR-EXEC-010/006)."""
    with SessionLocal() as session:

        def _commit(s: Session, job: ModelJob) -> None:
            if job.state not in _STAGE_TO_JOB_STATE.values() and job.state != "loading_model":
                raise ResultRefused(f"job {job.id} not executing (state={job.state})")
            repo.transition(s, job, "model_job", "completed", actor=supervisor_id)

            attempt = s.execute(
                select(TaskAttempt).where(TaskAttempt.id == job.attempt_id).with_for_update()
            ).scalar_one()
            repo.transition(s, attempt, "attempt", "committing", actor=supervisor_id)
            repo.transition(s, attempt, "attempt", "succeeded", actor=supervisor_id)

            cmd = s.execute(
                select(CommandOutbox)
                .where(
                    CommandOutbox.model_job_id == job.id,
                    CommandOutbox.command_generation == job.current_command_generation,
                )
                .with_for_update()
            ).scalar_one()
            repo.transition(s, cmd, "command", "resolved", actor=supervisor_id)
            cmd.resolution_type = "succeeded"
            cmd.payload = {**(cmd.payload or {}), "result": result}

            # Close the SPEC-02 task machine + emit the completion event.
            task = s.get(ApplicationTask, attempt.task_id, with_for_update=True)
            if task is not None and task.state == "running":
                repo.transition(s, task, "task", "completed", actor=supervisor_id)
                ws = repo.lock_workspace(s, task.workspace_id)
                if ws.active_task_count > 0:
                    ws.active_task_count -= 1
                seq = repo.next_event_sequence(s, task.workspace_id)
                s.add(OutboxEvent(
                    workspace_id=task.workspace_id, aggregate_type="task",
                    aggregate_id=str(task.id), event_type="task_completed",
                    event_sequence=seq, payload={"job_id": str(job.id)},
                ))

        fenced(session, job_id, supervisor_id, lease_revision, _commit)
