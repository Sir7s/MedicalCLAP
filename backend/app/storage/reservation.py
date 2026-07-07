"""Storage reservation with atomic quota checks (P5, IMP-STOR-001/002/003).

The quota row is locked FOR UPDATE, active reservations are summed, and the
new reservation is inserted in the same transaction — "check free space, then
insert without a lock" is exactly what IMP-STOR-002 forbids.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import StorageQuota, StorageReservation


class QuotaExceeded(RuntimeError):
    pass


def ensure_quota(
    session: Session, backend: str, fs_identity: str, quota_bytes: int
) -> None:
    """Idempotently create the quota row (dev/test bootstrap)."""
    with session.begin():
        row = session.execute(
            select(StorageQuota).where(
                StorageQuota.storage_backend == backend,
                StorageQuota.filesystem_identity == fs_identity,
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(StorageQuota(
                storage_backend=backend, filesystem_identity=fs_identity,
                quota_bytes=quota_bytes,
            ))


def reserve(
    session: Session,
    *,
    reservation_type: str,
    backend: str,
    fs_identity: str,
    bytes_needed: int,
    workspace_id: uuid.UUID | None = None,
    operation_id: str | None = None,
    owner: str | None = None,
) -> uuid.UUID:
    """Atomically reserve space. Raises QuotaExceeded without inserting."""
    with session.begin():
        quota = session.execute(
            select(StorageQuota)
            .where(
                StorageQuota.storage_backend == backend,
                StorageQuota.filesystem_identity == fs_identity,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if quota is None:
            raise QuotaExceeded(f"no quota configured for {backend}/{fs_identity}")

        active = session.execute(
            select(func.coalesce(func.sum(StorageReservation.reserved_bytes), 0)).where(
                StorageReservation.storage_backend == backend,
                StorageReservation.filesystem_identity == fs_identity,
                StorageReservation.reservation_status == "active",
            )
        ).scalar_one()
        if int(active) + bytes_needed > quota.quota_bytes:
            raise QuotaExceeded(
                f"{backend}/{fs_identity}: active={active} + request={bytes_needed} "
                f"> quota={quota.quota_bytes}"
            )
        res = StorageReservation(
            reservation_type=reservation_type,
            workspace_id=workspace_id,
            operation_id=operation_id,
            storage_backend=backend,
            filesystem_identity=fs_identity,
            reserved_bytes=bytes_needed,
            reservation_status="active",
            owner_instance_id=owner,
        )
        session.add(res)
        session.flush()
        return res.id


def release(session: Session, reservation_id: uuid.UUID) -> None:
    with session.begin():
        res = session.get(StorageReservation, reservation_id, with_for_update=True)
        if res is not None and res.reservation_status == "active":
            res.reservation_status = "released"
            res.released_at = datetime.now(UTC)
