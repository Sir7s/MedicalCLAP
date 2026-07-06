"""Event Outbox Publisher (P3, SPEC-01 §2.4).

Publishes committed business events from `outbox_events` to the Redis event
stream in id order, then marks them published. At-least-once: a crash between
XADD and the `published` mark re-publishes on recovery; downstream consumers
dedup by (workspace_id, event_sequence).
"""
from __future__ import annotations

import json
import uuid

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import failpoints
from ..db.models import OutboxEvent
from .redis_client import EVENT_STREAM


def _fields(ev: OutboxEvent) -> dict[str, str]:
    return {
        "event_id": str(ev.id),
        "workspace_id": str(ev.workspace_id) if ev.workspace_id else "",
        "aggregate_type": ev.aggregate_type,
        "aggregate_id": ev.aggregate_id,
        "event_type": ev.event_type,
        "event_sequence": str(ev.event_sequence),
        "payload": json.dumps(ev.payload or {}),
    }


def _unpublished_ids(session: Session, limit: int) -> list[uuid.UUID]:
    with session.begin():
        return list(
            session.execute(
                select(OutboxEvent.id)
                .where(OutboxEvent.published.is_(False))
                .order_by(OutboxEvent.event_sequence, OutboxEvent.created_at)
                .limit(limit)
            ).scalars()
        )


def publish_one(session: Session, r: redis.Redis, event_id: uuid.UUID) -> bool:
    with session.begin():
        ev = session.get(OutboxEvent, event_id, with_for_update=True)
        if ev is None or ev.published:
            return False
        fields = _fields(ev)

    r.xadd(EVENT_STREAM, fields)  # type: ignore[arg-type]  # redis stub dict invariance
    failpoints.trip("FP-EXEC-AFTER-EVENT-SEND")

    with session.begin():
        ev = session.get(OutboxEvent, event_id, with_for_update=True)
        if ev is not None and not ev.published:
            ev.published = True
    return True


def publish_pending(session: Session, r: redis.Redis, *, limit: int = 200) -> int:
    sent = 0
    for eid in _unpublished_ids(session, limit):
        if publish_one(session, r, eid):
            sent += 1
    return sent
