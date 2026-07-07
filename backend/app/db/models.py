"""Persistent control-plane tables (P2).

Scope: the core execution control plane (SPEC-02 §3.2 subset) — workspaces,
tasks, attempts, model jobs, command/event outbox, idempotency, audit, and the
dead-letter table (Appendix IMP-EXEC-001). Dataset/model/history/backup/freeze
tables belong to their own phases.

Conventions:
- UUID primary keys; timezone-aware timestamps.
- State columns are VARCHAR guarded by CHECK constraints generated from the
  state machines in `states.py`, so the DB rejects unknown states too.
- All child→parent FKs use ON DELETE RESTRICT (SPEC-02 §3.3).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .states import (
    ATTEMPT_STATES as _ATTEMPT_STATES,
)
from .states import (
    COMMAND_RESOLUTION_TYPES,
    COMMAND_STATES,
    DEAD_LETTER_RESOLUTIONS,
    MODEL_JOB_STATES,
    TASK_STATES,
    WORKSPACE_STATES,
)


def _in_check(column: str, allowed: tuple[str, ...], name: str) -> CheckConstraint:
    values = ", ".join(f"'{v}'" for v in allowed)
    return CheckConstraint(f"{column} IN ({values})", name=name)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class WorkspaceSession(Base):
    __tablename__ = "workspace_sessions"
    __table_args__ = (
        _in_check("state", WORKSPACE_STATES, "ck_workspace_state"),
        CheckConstraint("active_task_count >= 0", name="ck_workspace_task_count_nonneg"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    active_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workspace_content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationTask(Base):
    __tablename__ = "application_tasks"
    __table_args__ = (
        _in_check("state", TASK_STATES, "ck_task_state"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        _in_check("state", _ATTEMPT_STATES, "ck_attempt_state"),
        UniqueConstraint("task_id", "attempt_number", name="uq_attempt_task_number"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ModelJob(Base):
    __tablename__ = "model_jobs"
    __table_args__ = (
        _in_check("state", MODEL_JOB_STATES, "ck_model_job_state"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_attempts.id", ondelete="RESTRICT"),
        nullable=False, unique=True, index=True,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    current_command_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_lease_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_instance_id: Mapped[str | None] = mapped_column(String(128))
    supervisor_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # P4 — worker binding (IMP-EXEC-011 step 6) + execution retry budget (IMP-EXEC-007).
    execution_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_pid: Mapped[int | None] = mapped_column(Integer)
    child_process_uuid: Mapped[str | None] = mapped_column(String(64))
    startup_nonce_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CommandOutbox(Base):
    __tablename__ = "command_outbox"
    __table_args__ = (
        _in_check("state", COMMAND_STATES, "ck_command_state"),
        CheckConstraint(
            "resolution_type IS NULL OR resolution_type IN ("
            + ", ".join(f"'{v}'" for v in COMMAND_RESOLUTION_TYPES)
            + ")",
            name="ck_command_resolution_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    model_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    command_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    resolution_type: Mapped[str | None] = mapped_column(String(32))
    acquired_lease_revision: Mapped[int | None] = mapped_column(Integer)
    lease_owner_instance_id: Mapped[str | None] = mapped_column(String(128))
    dispatch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # P4 — distinct retry budgets (IMP-EXEC-007) + recovery window (IMP-EXEC-005/006).
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_recovery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_recovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_recovery_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_recovery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "event_sequence", name="uq_event_workspace_sequence"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), index=True
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    result_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str | None] = mapped_column(String(64))
    aggregate_id: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeadLetterCommand(Base):
    """Appendix IMP-EXEC-001 — invalid messages are persisted, never silently dropped."""

    __tablename__ = "dead_letter_commands"
    __table_args__ = (
        _in_check("resolution_status", DEAD_LETTER_RESOLUTIONS, "ck_dead_letter_resolution"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    original_message_id: Mapped[str | None] = mapped_column(String(256))
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False)
    command_id: Mapped[uuid.UUID | None] = mapped_column()
    model_job_id: Mapped[str | None] = mapped_column(String(128))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    command_schema_version: Mapped[str | None] = mapped_column(String(64))
    delivery_attempt: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    detected_by: Mapped[str] = mapped_column(String(128), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unresolved"
    )
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
