"""WebSocket status stream (P6, SPEC-08 §9.3 subset).

Contract: `/ws/{workspace_id}?after=<seq>` replays persisted outbox events
(PostgreSQL is the durable truth) in sequence order, then streams new ones by
polling the outbox. Clients dedup by `event_sequence`; a reconnect with
`after=<last seen>` closes any gap. Full session auth arrives in P17
(loopback-only posture until then).
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..db.base import get_sessionmaker
from ..db.models import OutboxEvent, WorkspaceSession

router = APIRouter()

POLL_SECONDS = 0.5


def _fetch_after(workspace_id: uuid.UUID, after: int, limit: int = 200) -> list[dict]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        rows = s.execute(
            select(OutboxEvent)
            .where(OutboxEvent.workspace_id == workspace_id,
                   OutboxEvent.event_sequence > after)
            .order_by(OutboxEvent.event_sequence)
            .limit(limit)
        ).scalars().all()
        return [
            {"event_sequence": e.event_sequence, "event_type": e.event_type,
             "aggregate_type": e.aggregate_type, "aggregate_id": e.aggregate_id}
            for e in rows
        ]


@router.websocket("/ws/{workspace_id}")
async def workspace_events(ws: WebSocket, workspace_id: uuid.UUID, after: int = 0) -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        exists = s.get(WorkspaceSession, workspace_id) is not None
    if not exists:
        await ws.close(code=4404)
        return

    await ws.accept()
    last = after
    try:
        while True:
            batch = await asyncio.to_thread(_fetch_after, workspace_id, last)
            for ev in batch:
                await ws.send_json(ev)
                last = max(last, ev["event_sequence"])
            # Await the client between polls: receive_text() raises
            # WebSocketDisconnect promptly on close (a pure-push loop would
            # never notice the disconnect); the timeout doubles as poll sleep.
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
    except WebSocketDisconnect:
        return
