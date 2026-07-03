"""Repository helpers for the control plane (P2).

Thin, typed helpers over the ORM: guarded state transitions (validated by the
state machine before any write), audit append, and monotonic sequence/number
allocation. Higher-level, multi-row transactions live in `service.py`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import states
from .models import (
    AuditEvent,
    OutboxEvent,
    TaskAttempt,
    WorkspaceSession,
)


def append_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        actor=actor,
        action=action,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        detail=detail,
    )
    session.add(ev)
    return ev


def transition(
    session: Session,
    obj: object,
    machine: str,
    new_state: str,
    *,
    actor: str = "system",
    write_audit: bool = True,
) -> None:
    """Validate and apply a state transition; raises IllegalTransition if illegal."""
    old = obj.state  # type: ignore[attr-defined]
    states.assert_transition(machine, old, new_state)
    obj.state = new_state  # type: ignore[attr-defined]
    if write_audit:
        append_audit(
            session,
            actor=actor,
            action=f"{machine}_transition",
            aggregate_type=machine,
            aggregate_id=str(getattr(obj, "id", "")),
            detail={"from": old, "to": new_state},
        )


def create_workspace(session: Session) -> WorkspaceSession:
    ws = WorkspaceSession(state="active", active_task_count=0)
    session.add(ws)
    session.flush()
    return ws


def lock_workspace(session: Session, workspace_id: uuid.UUID) -> WorkspaceSession:
    """SELECT ... FOR UPDATE to serialize task-count and event-sequence writes."""
    return session.execute(
        select(WorkspaceSession).where(WorkspaceSession.id == workspace_id).with_for_update()
    ).scalar_one()


def next_event_sequence(session: Session, workspace_id: uuid.UUID) -> int:
    """Next monotonic per-workspace event sequence (call under lock_workspace)."""
    current = session.execute(
        select(func.coalesce(func.max(OutboxEvent.event_sequence), 0)).where(
            OutboxEvent.workspace_id == workspace_id
        )
    ).scalar_one()
    return int(current) + 1


def next_attempt_number(session: Session, task_id: uuid.UUID) -> int:
    current = session.execute(
        select(func.coalesce(func.max(TaskAttempt.attempt_number), 0)).where(
            TaskAttempt.task_id == task_id
        )
    ).scalar_one()
    return int(current) + 1
