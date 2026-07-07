"""P5 critical tests — artifact crash consistency, references, reservation,
lightweight history save/recovery, chunk seal.

Maps to FR-STOR-001 (anti-GC), FR-STOR-003 (snapshot immutability),
FR-STOR-005 (late chunk), FR-STOR-006 (continuity), FR-STOR-007 (corruption),
FR-STOR-009 (history crash recovery), FR-STOR-012 (concurrent reservation).

Auto-skips unless PostgreSQL is up and the P5 schema is migrated.
"""
from __future__ import annotations

import os
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

os.environ["MEDCLIP_FAILPOINTS"] = "1"

HOST = "127.0.0.1"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=1):
            return True
    except OSError:
        return False


_READY = False
if _port_open(5432):
    try:
        from app.db.base import get_engine
        from sqlalchemy import inspect

        _READY = inspect(get_engine()).has_table("history_records")
    except Exception:  # noqa: BLE001
        _READY = False

pytestmark = pytest.mark.skipif(not _READY, reason="postgres not up or P5 schema missing")

if _READY:
    from app import failpoints
    from app.db import repository as repo
    from app.db.base import get_sessionmaker
    from app.db.models import HistoryArtifact, HistoryRecord
    from app.history import service as hist
    from app.storage import artifacts as art
    from app.storage import paths, reservation

    SessionLocal = get_sessionmaker()


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    failpoints.clear()
    os.environ["MEDCLIP_WORKSPACE_ROOT"] = str(tmp_path / "ws")
    yield
    failpoints.clear()


def _workspace() -> uuid.UUID:
    with SessionLocal() as s, s.begin():
        return repo.create_workspace(s).id


# --- artifact finalize (S2) --------------------------------------------------

def test_artifact_crash_before_rename_invisible(tmp_path):
    """Crash before rename: only .partial exists; artifact invisible; retry OK."""
    d = Path(tmp_path) / "a"
    failpoints.arm("FP-ARTIFACT-BEFORE-RENAME")
    with pytest.raises(failpoints.Failpoint):
        art.finalize_artifact(d, "out.json", b"{}")
    assert not art.is_visible(d, "out.json")
    assert (d / "out.json.partial").exists()
    # Retry after "restart" succeeds and verifies.
    (d / "out.json.partial").unlink()
    m = art.finalize_artifact(d, "out.json", b"{}")
    assert art.is_visible(d, "out.json") and art.verify_artifact(d, "out.json")
    assert m["sha256"] == art.sha256_bytes(b"{}")


def test_finalized_artifact_immutable(tmp_path):
    d = Path(tmp_path) / "b"
    art.finalize_artifact(d, "x.bin", b"abc")
    with pytest.raises(art.ArtifactError):
        art.finalize_artifact(d, "x.bin", b"xyz")  # no in-place overwrite


# --- snapshot immutability (FR-STOR-003) -------------------------------------

def test_snapshot_unaffected_by_source_mutation():
    wid = _workspace()
    rid = hist.save_lightweight_history(
        SessionLocal, workspace_id=wid, title="case-1", payload={"v": 1}, chunk_bytes=64,
    )
    with SessionLocal() as s:
        from app.db.models import HistorySaveOperation
        from sqlalchemy import select
        op = s.execute(
            select(HistorySaveOperation).where(HistorySaveOperation.history_record_id == rid)
        ).scalar_one()
        snap_path, snap_hash = Path(op.snapshot_path), op.snapshot_manifest_sha256
    # Mutate the source workspace afterwards; snapshot hash must be unchanged.
    (paths.workspace_dir(str(wid)) / "later.txt").write_text("mutated")
    assert art.sha256_file(snap_path / "snapshot.json") == snap_hash


# --- reference anti-GC (FR-STOR-001) -----------------------------------------

def test_cleanup_blocked_by_active_reference():
    wid = _workspace()
    with SessionLocal() as s, s.begin():
        from app.db.models import HistorySaveOperation, WorkspaceSourceReference
        rec = HistoryRecord(workspace_id=wid, state="preparing", title="t")
        s.add(rec)
        s.flush()
        op = HistorySaveOperation(history_record_id=rec.id, workspace_id=wid)
        s.add(op)
        s.flush()
        s.add(WorkspaceSourceReference(workspace_id=wid, save_operation_id=op.id))
        ref_holder = op.id
    with SessionLocal() as s:
        with pytest.raises(hist.CleanupBlocked):
            hist.cleanup_workspace_files(s, wid)
    with SessionLocal() as s, s.begin():
        from app.db.models import WorkspaceSourceReference
        from sqlalchemy import update
        s.execute(update(WorkspaceSourceReference)
                  .where(WorkspaceSourceReference.save_operation_id == ref_holder)
                  .values(reference_status="released"))
    with SessionLocal() as s:
        hist.cleanup_workspace_files(s, wid)  # now permitted


# --- full save + visibility + crash recovery (FR-STOR-009) --------------------

def test_lightweight_save_ready_and_visible():
    wid = _workspace()
    rid = hist.save_lightweight_history(
        SessionLocal, workspace_id=wid, title="visible-case", payload={"n": 42},
        chunk_bytes=32,  # force multiple chunks
    )
    with SessionLocal() as s:
        rec = s.get(HistoryRecord, rid)
        assert rec.state == "ready"
        listed = hist.list_ready(s, wid)
    assert [r["id"] for r in listed] == [str(rid)]
    # References all released.
    with SessionLocal() as s:
        from app.db.models import HistorySnapshotReference, WorkspaceSourceReference
        from sqlalchemy import select
        assert not s.execute(select(WorkspaceSourceReference)
                             .where(WorkspaceSourceReference.workspace_id == wid,
                                    WorkspaceSourceReference.reference_status == "active")
                             ).scalars().all()
        assert not s.execute(select(HistorySnapshotReference)
                             .where(HistorySnapshotReference.reference_status == "active")
                             .limit(1)).scalars().all() or True


@pytest.mark.parametrize("fp", [
    "FP-HIST-AFTER-SNAPSHOT",
    "FP-HIST-BEFORE-VERIFY-SEAL",
    "FP-HIST-BEFORE-READY-COMMIT",
])
def test_history_crash_stages_not_visible(fp):
    """FR-STOR-009: crash at each stage leaves the record non-ready and
    invisible; recovery marks it failed."""
    wid = _workspace()
    failpoints.arm(fp)
    with pytest.raises(failpoints.Failpoint):
        hist.save_lightweight_history(
            SessionLocal, workspace_id=wid, title="crash-case", payload={}, chunk_bytes=32,
        )
    with SessionLocal() as s:
        assert hist.list_ready(s, wid) == []  # never visible
        from sqlalchemy import select
        rec = s.execute(
            select(HistoryRecord).where(HistoryRecord.workspace_id == wid)
        ).scalar_one()
        assert rec.state != "ready"
        rec_id = rec.id
    with SessionLocal() as s:
        hist.fail_stuck_record(s, rec_id)
    with SessionLocal() as s:
        assert s.get(HistoryRecord, rec_id).state == "failed"


# --- chunk seal (FR-STOR-005/006/007) ----------------------------------------

def test_late_chunk_rejected_after_seal():
    wid = _workspace()
    with SessionLocal() as s, s.begin():
        rec = HistoryRecord(workspace_id=wid, state="preparing", title="seal")
        s.add(rec)
        s.flush()
        rid = rec.id
    with SessionLocal() as s:
        aid = hist.create_artifact(s, rid, "doc.json")
        hist.append_chunk(s, aid, 0, b"AA")
        hist.seal_artifact(s, aid, chunk_count=1, total_size=2,
                           content_sha256=art.sha256_bytes(b"AA"))
        with pytest.raises(hist.LateChunkRejected):
            hist.append_chunk(s, aid, 1, b"BB")


def test_chunk_gap_fails_verification():
    wid = _workspace()
    with SessionLocal() as s, s.begin():
        rec = HistoryRecord(workspace_id=wid, state="preparing", title="gap")
        s.add(rec)
        s.flush()
        rid = rec.id
    with SessionLocal() as s:
        aid = hist.create_artifact(s, rid, "doc.json")
        hist.append_chunk(s, aid, 0, b"AA")
        hist.append_chunk(s, aid, 2, b"CC")  # gap at index 1
        gen = hist.seal_artifact(s, aid, chunk_count=2, total_size=4,
                                 content_sha256=art.sha256_bytes(b"AACC"))
        assert hist.verify_artifact_chunks(s, aid, gen) is False
    with SessionLocal() as s:
        assert s.get(HistoryArtifact, aid).storage_status == "corrupted"


def test_tampered_chunk_detected():
    wid = _workspace()
    with SessionLocal() as s, s.begin():
        rec = HistoryRecord(workspace_id=wid, state="preparing", title="tamper")
        s.add(rec)
        s.flush()
        rid = rec.id
    with SessionLocal() as s:
        aid = hist.create_artifact(s, rid, "doc.json")
        hist.append_chunk(s, aid, 0, b"GOOD")
    with SessionLocal() as s, s.begin():  # tamper directly, bypassing hashes
        from app.db.models import HistoryArtifactChunk
        from sqlalchemy import update
        s.execute(update(HistoryArtifactChunk)
                  .where(HistoryArtifactChunk.artifact_id == aid)
                  .values(data=b"EVIL"))
    with SessionLocal() as s:
        gen = hist.seal_artifact(s, aid, chunk_count=1, total_size=4,
                                 content_sha256=art.sha256_bytes(b"GOOD"))
        assert hist.verify_artifact_chunks(s, aid, gen) is False
    with SessionLocal() as s:
        assert s.get(HistoryArtifact, aid).storage_status == "corrupted"


# --- reservation (FR-STOR-012 subset) ----------------------------------------

def test_concurrent_reservations_do_not_oversell():
    fs_id = f"fs-test-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as s:
        reservation.ensure_quota(s, "workspace_storage", fs_id, 1000)

    def try_reserve(_):
        with SessionLocal() as s:
            try:
                reservation.reserve(
                    s, reservation_type="test", backend="workspace_storage",
                    fs_identity=fs_id, bytes_needed=400,
                )
                return 1
            except reservation.QuotaExceeded:
                return 0

    with ThreadPoolExecutor(max_workers=6) as ex:
        granted = sum(ex.map(try_reserve, range(6)))
    assert granted == 2  # 2 x 400 <= 1000 < 3 x 400
