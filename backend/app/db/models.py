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
    LargeBinary,
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
    HISTORY_ARTIFACT_STATES,
    HISTORY_STATES,
    MODEL_JOB_STATES,
    REFERENCE_STATUSES,
    RESERVATION_STATUSES,
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


# --- P5: history, references, storage reservation (SPEC-04/05) ---------------


class HistoryRecord(Base):
    __tablename__ = "history_records"
    __table_args__ = (_in_check("state", HISTORY_STATES, "ck_history_state"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    profile: Mapped[str] = mapped_column(String(32), nullable=False, default="lightweight")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="preparing")
    title: Mapped[str | None] = mapped_column(String(256))
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class HistorySaveOperation(Base):
    __tablename__ = "history_save_operations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    history_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("history_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    snapshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HistoryArtifact(Base):
    __tablename__ = "history_artifacts"
    __table_args__ = (
        _in_check("storage_status", HISTORY_ARTIFACT_STATES, "ck_history_artifact_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    history_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("history_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    storage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="writing")
    expected_chunk_count: Mapped[int | None] = mapped_column(Integer)
    expected_total_size: Mapped[int | None] = mapped_column(BigInteger)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    verification_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    verification_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HistoryArtifactChunk(Base):
    __tablename__ = "history_artifact_chunks"
    __table_args__ = (
        UniqueConstraint("artifact_id", "chunk_index", name="uq_chunk_artifact_index"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("history_artifacts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class WorkspaceSourceReference(Base):
    """IMP-HIST-001 — protects original workspace files until snapshot finalize."""

    __tablename__ = "workspace_source_references"
    __table_args__ = (
        _in_check("reference_status", REFERENCE_STATUSES, "ck_source_ref_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    save_operation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("history_save_operations.id", ondelete="RESTRICT"), nullable=False
    )
    reference_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HistorySnapshotReference(Base):
    """IMP-HIST-001 — protects the snapshot until history ready / safe cleanup."""

    __tablename__ = "history_snapshot_references"
    __table_args__ = (
        _in_check("reference_status", REFERENCE_STATUSES, "ck_snapshot_ref_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    save_operation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("history_save_operations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_path: Mapped[str] = mapped_column(Text, nullable=False)
    reference_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StorageQuota(Base):
    """Quota row per (backend, filesystem) — locked for atomic reservation checks."""

    __tablename__ = "storage_quotas"
    __table_args__ = (
        UniqueConstraint("storage_backend", "filesystem_identity", name="uq_quota_backend_fs"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    storage_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    filesystem_identity: Mapped[str] = mapped_column(String(256), nullable=False)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class StorageReservation(Base):
    """IMP-STOR-001 — durable space reservation preceding large file operations."""

    __tablename__ = "storage_reservations"
    __table_args__ = (
        _in_check("reservation_status", RESERVATION_STATUSES, "ck_reservation_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    reservation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[str | None] = mapped_column(String(128))
    storage_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    filesystem_identity: Mapped[str] = mapped_column(String(256), nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    consumed_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reservation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    owner_instance_id: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- P8: CT viewer (NIfTI volumes + polygon annotations) ---------------------


class CtVolume(Base):
    __tablename__ = "ct_volumes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shape: Mapped[dict] = mapped_column(JSONB, nullable=False)      # [x, y, z]
    spacing: Mapped[dict] = mapped_column(JSONB, nullable=False)    # [sx, sy, sz]
    affine: Mapped[dict] = mapped_column(JSONB, nullable=False)     # 4x4
    orientation: Mapped[str] = mapped_column(String(8), nullable=False)
    dtype: Mapped[str] = mapped_column(String(32), nullable=False)
    scalar_min: Mapped[float] = mapped_column(nullable=False)
    scalar_max: Mapped[float] = mapped_column(nullable=False)
    window_center: Mapped[float] = mapped_column(nullable=False)
    window_width: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CtAnnotation(Base):
    __tablename__ = "ct_annotations"
    __table_args__ = (
        _in_check("plane", ("axial", "coronal", "sagittal"), "ck_annotation_plane"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ct_volume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ct_volumes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_sessions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plane: Mapped[str] = mapped_column(String(16), nullable=False)
    slice_index: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[list] = mapped_column(JSONB, nullable=False)     # [[x,y], ...]
    label: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
