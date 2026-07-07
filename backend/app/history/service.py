"""Lightweight-history save flow (P5, SPEC-05; IMP-HIST-001..004).

Reference order (IMP-HIST-002):
    create workspace source reference
    -> create snapshot -> finalize snapshot manifest
    -> create history snapshot reference -> release source reference
    -> write/verify history artifacts -> ready
    -> release snapshot reference

Chunk verification uses a Seal (IMP-HIST-003/004): sealing flips the artifact
`writing -> verifying` and bumps `verification_generation`; late chunks are
rejected; the final short transaction re-validates status, generation, count,
size, and index continuity before `verified`.

Only `ready` records are visible through the read API.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .. import failpoints
from ..db import repository as repo
from ..db.models import (
    HistoryArtifact,
    HistoryArtifactChunk,
    HistoryRecord,
    HistorySaveOperation,
    HistorySnapshotReference,
    WorkspaceSourceReference,
)
from ..storage import artifacts as art
from ..storage import paths, reservation

DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024  # SPEC-05 §6.3
HISTORY_QUOTA_BYTES = 10 * 1024 * 1024 * 1024  # dev default (10 GB)


class HistorySaveError(RuntimeError):
    pass


class LateChunkRejected(RuntimeError):
    """IMP-HIST-004 — chunks may only be inserted while status is `writing`."""


class CleanupBlocked(RuntimeError):
    """FR-STOR-001 — cleanup is refused while active references exist."""


# --- chunked artifact primitives ---------------------------------------------

def create_artifact(session: Session, record_id: uuid.UUID, name: str) -> uuid.UUID:
    with session.begin():
        a = HistoryArtifact(history_record_id=record_id, name=name, storage_status="writing")
        session.add(a)
        session.flush()
        return a.id


def append_chunk(session: Session, artifact_id: uuid.UUID, index: int, data: bytes) -> None:
    with session.begin():
        a = session.get(HistoryArtifact, artifact_id, with_for_update=True)
        if a is None or a.storage_status != "writing":
            raise LateChunkRejected(
                f"artifact {artifact_id} not accepting chunks "
                f"(status={getattr(a, 'storage_status', 'missing')})"
            )
        session.add(HistoryArtifactChunk(
            artifact_id=artifact_id, chunk_index=index,
            size_bytes=len(data), sha256=art.sha256_bytes(data), data=data,
        ))
        failpoints.trip("FP-HIST-AFTER-CHUNK-INSERT")


def seal_artifact(
    session: Session, artifact_id: uuid.UUID, *, chunk_count: int, total_size: int,
    content_sha256: str,
) -> int:
    """Atomically flip writing->verifying; returns the verification generation."""
    with session.begin():
        a = session.get(HistoryArtifact, artifact_id, with_for_update=True)
        if a is None or a.storage_status != "writing":
            raise HistorySaveError("seal requires status=writing")
        repo.transition(session, a, "history_artifact", "verifying", write_audit=False)
        a.verification_generation += 1
        a.verification_started_at = datetime.now(UTC)
        a.expected_chunk_count = chunk_count
        a.expected_total_size = total_size
        a.content_sha256 = content_sha256
        return a.verification_generation


def verify_artifact_chunks(session: Session, artifact_id: uuid.UUID, generation: int) -> bool:
    """Streamed verification in short transactions, then a final revalidation."""
    hasher = hashlib.sha256()
    seen = 0
    total = 0
    last_index = -1
    while True:
        with session.begin():
            rows = session.execute(
                select(HistoryArtifactChunk)
                .where(
                    HistoryArtifactChunk.artifact_id == artifact_id,
                    HistoryArtifactChunk.chunk_index > last_index,
                )
                .order_by(HistoryArtifactChunk.chunk_index)
                .limit(16)
            ).scalars().all()
            batch = [(c.chunk_index, c.sha256, bytes(c.data)) for c in rows]
        if not batch:
            break
        for idx, chash, data in batch:
            if idx != last_index + 1:  # continuity (FR-STOR-006)
                return _mark_corrupted(session, artifact_id)
            if art.sha256_bytes(data) != chash:  # per-chunk integrity (FR-STOR-007)
                return _mark_corrupted(session, artifact_id)
            hasher.update(data)
            seen += 1
            total += len(data)
            last_index = idx
        failpoints.trip("FP-HIST-DURING-VERIFICATION")

    # Final short transaction: revalidate everything (IMP-HIST-004).
    with session.begin():
        a = session.get(HistoryArtifact, artifact_id, with_for_update=True)
        if (
            a is None
            or a.storage_status != "verifying"
            or a.verification_generation != generation
            or a.expected_chunk_count != seen
            or a.expected_total_size != total
            or a.content_sha256 != hasher.hexdigest()
        ):
            if a is not None:
                repo.transition(session, a, "history_artifact", "corrupted", write_audit=False)
            return False
        repo.transition(session, a, "history_artifact", "verified", write_audit=False)
        return True


def _mark_corrupted(session: Session, artifact_id: uuid.UUID) -> bool:
    with session.begin():
        a = session.get(HistoryArtifact, artifact_id, with_for_update=True)
        if a is not None and a.storage_status in ("writing", "verifying"):
            repo.transition(session, a, "history_artifact", "corrupted", write_audit=False)
    return False


# --- save flow ----------------------------------------------------------------

def _transition_record(session: Session, record_id: uuid.UUID, new_state: str) -> None:
    with session.begin():
        rec = session.get(HistoryRecord, record_id, with_for_update=True)
        repo.transition(session, rec, "history", new_state, actor="history")


def save_lightweight_history(
    SessionLocal: sessionmaker,
    *,
    workspace_id: uuid.UUID,
    title: str,
    payload: dict,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> uuid.UUID:
    """Run the full lightweight save. Returns the history record id.

    Crash-safe: any failure leaves the record in a non-`ready` state, invisible
    to readers, recoverable by `fail_stuck_record`.
    """
    root = paths.workspace_root()
    fs_id = paths.filesystem_identity(root)
    body = json.dumps(
        {"title": title, "payload": payload, "disclaimer":
         "Research and demonstration use only. Not intended for clinical "
         "diagnosis or treatment decisions."},
        ensure_ascii=False,
    ).encode("utf-8")

    with SessionLocal() as s:
        reservation.ensure_quota(s, "workspace_storage", fs_id, HISTORY_QUOTA_BYTES)
    with SessionLocal() as s:
        res_id = reservation.reserve(
            s, reservation_type="history_snapshot", backend="workspace_storage",
            fs_identity=fs_id, bytes_needed=max(len(body) * 2, 1024),
            workspace_id=workspace_id,
        )

    with SessionLocal() as s, s.begin():
        rec = HistoryRecord(workspace_id=workspace_id, profile="lightweight",
                            state="preparing", title=title, meta={"kind": "lightweight"})
        s.add(rec)
        s.flush()
        op = HistorySaveOperation(history_record_id=rec.id, workspace_id=workspace_id)
        s.add(op)
        s.flush()
        src_ref = WorkspaceSourceReference(workspace_id=workspace_id, save_operation_id=op.id)
        s.add(src_ref)
        s.flush()
        record_id, op_id, src_ref_id = rec.id, op.id, src_ref.id

    try:
        with SessionLocal() as s:
            _transition_record(s, record_id, "snapshotting")

        # Snapshot: copy current workspace files (the payload doc stands in for
        # the lightweight document set) into an immutable snapshot dir.
        snap_dir = paths.snapshot_dir(str(op_id))
        manifest = art.finalize_artifact(snap_dir, "snapshot.json", body)
        failpoints.trip("FP-HIST-AFTER-SNAPSHOT")

        with SessionLocal() as s, s.begin():
            op_row = s.get(HistorySaveOperation, op_id, with_for_update=True)
            op_row.snapshot_manifest_sha256 = manifest["sha256"]
            op_row.snapshot_path = str(snap_dir)
            s.add(HistorySnapshotReference(
                save_operation_id=op_id, snapshot_manifest_sha256=manifest["sha256"],
                snapshot_path=str(snap_dir),
            ))
            src = s.get(WorkspaceSourceReference, src_ref_id, with_for_update=True)
            src.reference_status = "released"
            src.released_at = datetime.now(UTC)

        with SessionLocal() as s:
            _transition_record(s, record_id, "writing_artifacts")
            artifact_id = create_artifact(s, record_id, "history.json")
            chunks = [body[i:i + chunk_bytes] for i in range(0, len(body), chunk_bytes)] or [b""]
            for idx, chunk in enumerate(chunks):
                append_chunk(s, artifact_id, idx, chunk)

        with SessionLocal() as s:
            failpoints.trip("FP-HIST-BEFORE-VERIFY-SEAL")
            gen = seal_artifact(
                s, artifact_id, chunk_count=len(chunks), total_size=len(body),
                content_sha256=art.sha256_bytes(body),
            )
            _transition_record(s, record_id, "verifying")
            if not verify_artifact_chunks(s, artifact_id, gen):
                raise HistorySaveError("artifact verification failed")

        with SessionLocal() as s:
            failpoints.trip("FP-HIST-BEFORE-READY-COMMIT")
            _transition_record(s, record_id, "ready")
            with s.begin():
                ref = s.execute(
                    select(HistorySnapshotReference)
                    .where(HistorySnapshotReference.save_operation_id == op_id)
                    .with_for_update()
                ).scalar_one()
                ref.reference_status = "released"
                ref.released_at = datetime.now(UTC)
        return record_id
    finally:
        with SessionLocal() as s:
            reservation.release(s, res_id)


# --- read/recovery/cleanup -----------------------------------------------------

def list_ready(session: Session, workspace_id: uuid.UUID | None = None) -> list[dict]:
    """Only `ready` records are visible (SPEC-05 exit gate)."""
    stmt = select(HistoryRecord).where(HistoryRecord.state == "ready")
    if workspace_id is not None:
        stmt = stmt.where(HistoryRecord.workspace_id == workspace_id)
    rows = session.execute(stmt.order_by(HistoryRecord.created_at.desc())).scalars().all()
    out = [
        {"id": str(r.id), "title": r.title, "profile": r.profile,
         "state": r.state, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
    session.rollback()
    return out


def fail_stuck_record(session: Session, record_id: uuid.UUID) -> None:
    """Recovery: a record stuck in a non-terminal, non-ready state -> failed."""
    with session.begin():
        rec = session.get(HistoryRecord, record_id, with_for_update=True)
        if rec is not None and rec.state in (
            "preparing", "snapshotting", "writing_artifacts", "verifying"
        ):
            repo.transition(session, rec, "history", "failed", actor="recovery")


def cleanup_workspace_files(session: Session, workspace_id: uuid.UUID) -> None:
    """Refuse cleanup while any active reference exists (FR-STOR-001)."""
    with session.begin():
        active_src = session.execute(
            select(func.count()).select_from(WorkspaceSourceReference).where(
                WorkspaceSourceReference.workspace_id == workspace_id,
                WorkspaceSourceReference.reference_status == "active",
            )
        ).scalar_one()
        active_snap = session.execute(
            select(func.count())
            .select_from(HistorySnapshotReference)
            .join(HistorySaveOperation,
                  HistorySnapshotReference.save_operation_id == HistorySaveOperation.id)
            .where(
                HistorySaveOperation.workspace_id == workspace_id,
                HistorySnapshotReference.reference_status == "active",
            )
        ).scalar_one()
    if active_src or active_snap:
        raise CleanupBlocked(
            f"workspace {workspace_id}: {active_src} source + {active_snap} snapshot "
            "references active"
        )
    shutil.rmtree(paths.workspace_dir(str(workspace_id)), ignore_errors=True)
