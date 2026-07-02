"""Transactional control-plane services (P2).

`create_task` implements the atomic creation transaction of Architecture v2.4.5
SPEC-03 §4.1 for the entities that exist in P2: it either persists the Task,
its first Attempt, its Model Job, the workspace task-count increment, the
Event-Outbox row, and the Command-Outbox row **all together**, or nothing at
all. (Deployment-execution-reference binding — step 3 of §4.1 — is added in P13
when deployments exist.)

Idempotency: an optional idempotency key is enforced by a UNIQUE constraint, so
concurrent duplicate requests resolve to exactly one task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import repository as repo
from .models import (
    ApplicationTask,
    CommandOutbox,
    IdempotencyRecord,
    ModelJob,
    TaskAttempt,
)


class TaskCreationError(RuntimeError):
    pass


@dataclass
class CreatedTask:
    task_id: str
    attempt_id: str
    model_job_id: str
    command_id: str
    idempotent_reuse: bool = False


def _find_idempotent(session: Session, key: str) -> str | None:
    rec = session.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
    ).scalar_one_or_none()
    return rec.result_ref if rec else None


def create_task(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    task_type: str,
    idempotency_key: str | None = None,
    payload: dict | None = None,
    fail_before_commit: bool = False,
) -> CreatedTask:
    """Atomically create a task and its execution scaffolding (SPEC-03 §4.1).

    `fail_before_commit` is a test-only failpoint that raises just before commit
    to prove the transaction is all-or-nothing.
    """
    try:
        with session.begin():
            # Idempotency short-circuit inside the tx (avoids autobegin conflicts).
            if idempotency_key:
                existing = _find_idempotent(session, idempotency_key)
                if existing:
                    return CreatedTask(existing, "", "", "", idempotent_reuse=True)

            ws = repo.lock_workspace(session, workspace_id)
            if ws.state != "active":
                raise TaskCreationError(f"workspace not active: {ws.state}")

            task = ApplicationTask(workspace_id=ws.id, task_type=task_type, state="queued")
            session.add(task)
            session.flush()

            attempt = TaskAttempt(
                task_id=task.id,
                attempt_number=repo.next_attempt_number(session, task.id),
                state="command_pending",
            )
            session.add(attempt)
            session.flush()

            job = ModelJob(attempt_id=attempt.id, state="queued", current_command_generation=0)
            session.add(job)
            session.flush()

            ws.active_task_count += 1

            seq = repo.next_event_sequence(session, ws.id)
            from .models import OutboxEvent

            session.add(
                OutboxEvent(
                    workspace_id=ws.id,
                    aggregate_type="task",
                    aggregate_id=str(task.id),
                    event_type="task_created",
                    event_sequence=seq,
                    payload=payload,
                )
            )

            command = CommandOutbox(
                model_job_id=job.id,
                attempt_id=attempt.id,
                command_generation=0,
                state="pending",
                payload=payload,
            )
            session.add(command)
            session.flush()

            repo.append_audit(
                session,
                actor="system",
                action="task_created",
                aggregate_type="task",
                aggregate_id=str(task.id),
                detail={"task_type": task_type},
            )

            if idempotency_key:
                session.add(
                    IdempotencyRecord(
                        idempotency_key=idempotency_key,
                        request_kind="create_task",
                        result_ref=str(task.id),
                    )
                )

            if fail_before_commit:
                raise TaskCreationError("injected failure before commit")

            result = CreatedTask(
                task_id=str(task.id),
                attempt_id=str(attempt.id),
                model_job_id=str(job.id),
                command_id=str(command.id),
            )
        return result
    except IntegrityError:
        # Likely a concurrent duplicate idempotency key; resolve to the winner.
        session.rollback()
        if idempotency_key:
            existing = _find_idempotent(session, idempotency_key)
            if existing:
                return CreatedTask(existing, "", "", "", idempotent_reuse=True)
        raise
