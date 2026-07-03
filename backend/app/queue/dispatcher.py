"""Command Dispatcher (P3, SPEC-03 §4.2/§4.6).

Delivers committed commands from `command_outbox` to the execution stream with
at-least-once semantics and crash recovery:

    pending --(commit)--> dispatching --XADD--> (commit) dispatched

A crash after the DB commit but before XADD (FR-EXEC-001), or after XADD but
before the `dispatched` mark (FR-EXEC-002), is recovered by re-selecting stuck
`pending`/`dispatching` commands and re-sending. The consumer dedups by
(command_id, generation), so re-delivery never causes a second business effect.
"""
from __future__ import annotations

import json
import uuid

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import failpoints
from ..db import repository as repo
from ..db.models import CommandOutbox
from .redis_client import EXEC_STREAM

_DISPATCHABLE = ("pending", "dispatching")


def _fields(cmd: CommandOutbox) -> dict[str, str]:
    return {
        "command_id": str(cmd.id),
        "model_job_id": str(cmd.model_job_id),
        "attempt_id": str(cmd.attempt_id),
        "command_generation": str(cmd.command_generation),
        "payload": json.dumps(cmd.payload or {}),
    }


def _dispatchable_ids(session: Session, limit: int) -> list[uuid.UUID]:
    with session.begin():
        return list(
            session.execute(
                select(CommandOutbox.id)
                .where(CommandOutbox.state.in_(_DISPATCHABLE))
                .order_by(CommandOutbox.created_at)
                .limit(limit)
            ).scalars()
        )


def dispatch_one(session: Session, r: redis.Redis, command_id: uuid.UUID) -> bool:
    """Dispatch a single command. Returns True if a message was sent."""
    # Phase A — move pending -> dispatching (durable) and capture the payload.
    with session.begin():
        cmd = session.get(CommandOutbox, command_id, with_for_update=True)
        if cmd is None or cmd.state not in _DISPATCHABLE:
            return False
        if cmd.state == "pending":
            repo.transition(session, cmd, "command", "dispatching", write_audit=False)
        cmd.dispatch_attempts += 1
        fields = _fields(cmd)

    failpoints.trip("FP-EXEC-BEFORE-QUEUE-SEND")
    r.xadd(EXEC_STREAM, fields)  # type: ignore[arg-type]  # redis stub dict invariance
    failpoints.trip("FP-EXEC-AFTER-QUEUE-SEND")

    # Phase B — mark dispatched (durable).
    with session.begin():
        cmd = session.get(CommandOutbox, command_id, with_for_update=True)
        if cmd is not None and cmd.state == "dispatching":
            repo.transition(session, cmd, "command", "dispatched", write_audit=False)
    return True


def dispatch_pending(session: Session, r: redis.Redis, *, limit: int = 100) -> int:
    """Dispatch (and recover) all dispatchable commands. Returns count sent."""
    sent = 0
    for cid in _dispatchable_ids(session, limit):
        if dispatch_one(session, r, cid):
            sent += 1
    return sent
