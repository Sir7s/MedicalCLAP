"""Minimum control-plane API (P6): workspaces, tasks, status, event replay."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import repository as repo
from ..db import service
from ..db.base import get_sessionmaker
from ..db.models import (
    ApplicationTask,
    ModelJob,
    OutboxEvent,
    TaskAttempt,
    WorkspaceSession,
)

router = APIRouter(prefix="/api", tags=["control-plane"])


class CreateTaskRequest(BaseModel):
    workspace_id: uuid.UUID
    task_type: str = Field(default="mock_retrieval", max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=256)
    payload: dict = Field(default_factory=dict)


@router.post("/workspaces")
def create_workspace() -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s, s.begin():
        ws = repo.create_workspace(s)
        return {"workspace_id": str(ws.id), "state": ws.state}


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: uuid.UUID) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        ws = s.get(WorkspaceSession, workspace_id)
        if ws is None:
            raise HTTPException(404, "workspace not found")
        return {"workspace_id": str(ws.id), "state": ws.state,
                "active_task_count": ws.active_task_count}


@router.post("/tasks")
def create_task(req: CreateTaskRequest) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        try:
            created = service.create_task(
                s, workspace_id=req.workspace_id, task_type=req.task_type,
                idempotency_key=req.idempotency_key, payload=req.payload,
            )
        except service.TaskCreationError as exc:
            raise HTTPException(409, str(exc)) from exc
    return {"task_id": created.task_id, "attempt_id": created.attempt_id,
            "model_job_id": created.model_job_id, "command_id": created.command_id,
            "idempotent_reuse": created.idempotent_reuse}


@router.get("/tasks/{task_id}")
def get_task(task_id: uuid.UUID) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        task = s.get(ApplicationTask, task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        attempt = s.execute(
            select(TaskAttempt).where(TaskAttempt.task_id == task_id)
            .order_by(TaskAttempt.attempt_number.desc()).limit(1)
        ).scalar_one_or_none()
        job = None
        if attempt is not None:
            job = s.execute(
                select(ModelJob).where(ModelJob.attempt_id == attempt.id)
            ).scalar_one_or_none()
        return {
            "task_id": str(task.id), "task_state": task.state,
            "attempt_state": attempt.state if attempt else None,
            "job_state": job.state if job else None,
            "lease_revision": job.execution_lease_revision if job else None,
        }


@router.get("/workspaces/{workspace_id}/events")
def replay_events(workspace_id: uuid.UUID, after: int = 0, limit: int = 200) -> list[dict]:
    """Gap recovery: gapless, sequence-ordered events after `after`."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        rows = s.execute(
            select(OutboxEvent)
            .where(OutboxEvent.workspace_id == workspace_id,
                   OutboxEvent.event_sequence > after)
            .order_by(OutboxEvent.event_sequence)
            .limit(min(limit, 1000))
        ).scalars().all()
        return [
            {"event_sequence": e.event_sequence, "event_type": e.event_type,
             "aggregate_type": e.aggregate_type, "aggregate_id": e.aggregate_id,
             "published": e.published, "created_at": e.created_at.isoformat()}
            for e in rows
        ]
