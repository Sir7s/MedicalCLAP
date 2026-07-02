"""P2 critical tests — persistent control plane against live PostgreSQL.

Covers atomic task creation (no partial commit), idempotency (sequential +
concurrent), DB-level state CHECK constraints, and FK ON DELETE RESTRICT.

Auto-skips unless PostgreSQL is up AND the schema has been migrated
(`alembic upgrade head`). The compose CI lane migrates then runs these.
"""
from __future__ import annotations

import socket
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

HOST, PORT = "127.0.0.1", 5432


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


_SCHEMA_OK = False
if _port_open():
    try:
        from app.db.base import get_engine
        from sqlalchemy import inspect

        _SCHEMA_OK = inspect(get_engine()).has_table("workspace_sessions")
    except Exception:  # noqa: BLE001
        _SCHEMA_OK = False

pytestmark = pytest.mark.skipif(
    not (_port_open() and _SCHEMA_OK),
    reason="postgres not up or schema not migrated (alembic upgrade head)",
)

if _port_open() and _SCHEMA_OK:
    from app.db import repository as repo
    from app.db import service
    from app.db.base import get_sessionmaker
    from app.db.models import (
        ApplicationTask,
        CommandOutbox,
        ModelJob,
        OutboxEvent,
        TaskAttempt,
        WorkspaceSession,
    )
    from sqlalchemy import func, select, text

    SessionLocal = get_sessionmaker()


def _new_workspace() -> uuid.UUID:
    with SessionLocal() as s, s.begin():
        ws = repo.create_workspace(s)
        wid = ws.id
    return wid


def _count(session, model, **filters):
    stmt = select(func.count()).select_from(model)
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    return session.execute(stmt).scalar_one()


def test_atomic_create_success():
    wid = _new_workspace()
    with SessionLocal() as s:
        result = service.create_task(s, workspace_id=wid, task_type="retrieval")
    with SessionLocal() as s:
        assert _count(s, ApplicationTask, workspace_id=wid) == 1
        task_id = uuid.UUID(result.task_id)
        assert _count(s, TaskAttempt, task_id=task_id) == 1
        assert _count(s, ModelJob, attempt_id=uuid.UUID(result.attempt_id)) == 1
        assert _count(s, CommandOutbox, model_job_id=uuid.UUID(result.model_job_id)) == 1
        assert _count(s, OutboxEvent, workspace_id=wid) == 1
        ws = s.get(WorkspaceSession, wid)
        assert ws.active_task_count == 1


def test_atomic_create_rollback_on_failure():
    """Injected failure before commit must leave NOTHING persisted (all-or-nothing)."""
    wid = _new_workspace()
    with SessionLocal() as s:
        with pytest.raises(service.TaskCreationError):
            service.create_task(
                s, workspace_id=wid, task_type="retrieval", fail_before_commit=True
            )
    with SessionLocal() as s:
        assert _count(s, ApplicationTask, workspace_id=wid) == 0
        assert _count(s, OutboxEvent, workspace_id=wid) == 0
        ws = s.get(WorkspaceSession, wid)
        assert ws.active_task_count == 0


def test_idempotent_reuse_sequential():
    wid = _new_workspace()
    key = f"idem-{uuid.uuid4()}"
    with SessionLocal() as s:
        first = service.create_task(
            s, workspace_id=wid, task_type="retrieval", idempotency_key=key
        )
    with SessionLocal() as s:
        second = service.create_task(
            s, workspace_id=wid, task_type="retrieval", idempotency_key=key
        )
    assert second.idempotent_reuse
    assert second.task_id == first.task_id
    with SessionLocal() as s:
        assert _count(s, ApplicationTask, workspace_id=wid) == 1


def test_idempotent_concurrent_yields_single_task():
    wid = _new_workspace()
    key = f"idem-{uuid.uuid4()}"

    def worker(_):
        with SessionLocal() as s:
            return service.create_task(
                s, workspace_id=wid, task_type="retrieval", idempotency_key=key
            ).task_id

    with ThreadPoolExecutor(max_workers=8) as ex:
        ids = list(ex.map(worker, range(8)))

    assert len(set(ids)) == 1, f"expected one task id, got {set(ids)}"
    with SessionLocal() as s:
        assert _count(s, ApplicationTask, workspace_id=wid) == 1


def test_db_rejects_illegal_state():
    from sqlalchemy.exc import IntegrityError

    wid = _new_workspace()
    with SessionLocal() as s:
        s.add(ApplicationTask(workspace_id=wid, task_type="x", state="not_a_state"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_fk_ondelete_restrict():
    from sqlalchemy.exc import IntegrityError

    wid = _new_workspace()
    with SessionLocal() as s:
        service.create_task(s, workspace_id=wid, task_type="retrieval")
    with SessionLocal() as s:
        with pytest.raises(IntegrityError):
            s.execute(text("DELETE FROM workspace_sessions WHERE id = :i"), {"i": str(wid)})
            s.commit()
