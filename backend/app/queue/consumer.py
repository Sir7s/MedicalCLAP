"""Mock supervisor consumer for the execution stream (P3).

In P3 the consumer validates and dedups messages; real lease/GPU execution is P4.
Correctness properties proved here:

- **Dedup** (FR-EXEC-005): a message is "processed" at most once per
  (command_id, generation), enforced by a unique `idempotency_records` key, so
  duplicate delivery yields exactly one business effect.
- **Dead-letter** (FR-EXEC-011, IMP-EXEC-003/004): unparseable payloads, missing
  commands, and generation-ahead anomalies are dead-lettered and ACKed (no
  infinite retry). A message whose generation is *behind* the current one is
  superseded — audited and ACKed, not executed.
- **Pending claim**: messages left un-ACKed by a crashed consumer are reclaimed
  with XAUTOCLAIM and reprocessed idempotently.
"""
from __future__ import annotations

import uuid
from typing import Any

import redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import CommandOutbox, IdempotencyRecord
from .deadletter import dead_letter
from .redis_client import EXEC_STREAM, SUPERVISOR_GROUP, ensure_group


def _try_uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except (ValueError, TypeError):
        return None


def _mark_processed(session: Session, key: str, ref: str) -> bool:
    """Insert an idempotency record; False if it already existed (duplicate)."""
    try:
        with session.begin():
            session.add(
                IdempotencyRecord(
                    idempotency_key=key, request_kind="command_processed", result_ref=ref
                )
            )
        return True
    except IntegrityError:
        session.rollback()
        return False


def process_message(
    session: Session, r: redis.Redis, msg_id: str, fields: dict[str, str]
) -> str:
    """Validate + dedup a single message, then ACK. Returns an outcome tag."""
    cid = _try_uuid(fields.get("command_id"))
    if cid is None:
        dead_letter(
            session, queue_name=EXEC_STREAM, error_code="PAYLOAD_UNPARSEABLE",
            detected_by="consumer", original_message_id=msg_id, raw_payload=fields,
        )
        r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
        return "dead_letter"

    cmd = session.get(CommandOutbox, cid)
    # Capture what we need BEFORE rollback (rollback expires ORM objects, and a
    # later attribute access would re-open a transaction and clash with begin()).
    found = cmd is not None
    current_gen = cmd.command_generation if cmd is not None else None
    session.rollback()  # close the autobegun read transaction

    if not found:
        dead_letter(
            session, queue_name=EXEC_STREAM, error_code="COMMAND_NOT_FOUND",
            detected_by="consumer", original_message_id=msg_id, command_id=cid,
            raw_payload=fields,
        )
        r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
        return "dead_letter"

    assert current_gen is not None  # narrowing: found implies a generation
    msg_gen = int(fields.get("command_generation", "-1"))
    if msg_gen > current_gen:
        # Message ahead of the control plane — an anomaly (IMP-EXEC-004).
        dead_letter(
            session, queue_name=EXEC_STREAM, error_code="GENERATION_AHEAD",
            detected_by="consumer", original_message_id=msg_id, command_id=cid,
            raw_payload=fields,
        )
        r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
        return "dead_letter"
    if msg_gen < current_gen:
        # Superseded — audit and ACK, do not execute (IMP-EXEC-004).
        with session.begin():
            repo.append_audit(
                session, actor="consumer", action="command_superseded",
                aggregate_type="command", aggregate_id=str(cid),
                detail={"msg_generation": msg_gen, "current": current_gen},
            )
        r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
        return "superseded"

    # Valid, current message — process at most once.
    key = f"cmd-processed:{cid}:{msg_gen}"
    fresh = _mark_processed(session, key, str(cid))
    r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
    return "processed" if fresh else "duplicate"


def consume_once(
    session: Session, r: redis.Redis, *, consumer: str = "c1", count: int = 20, block_ms: int = 200
) -> list[str]:
    """Read and process a batch of new messages. Returns the outcome tags."""
    ensure_group(r)
    resp: Any = r.xreadgroup(
        SUPERVISOR_GROUP, consumer, {EXEC_STREAM: ">"}, count=count, block=block_ms
    )
    outcomes: list[str] = []
    for _stream, entries in resp or []:
        for msg_id, fields in entries:
            outcomes.append(process_message(session, r, msg_id, fields))
    return outcomes


def claim_pending(
    session: Session, r: redis.Redis, *, consumer: str = "recovery",
    min_idle_ms: int = 0, count: int = 50,
) -> list[str]:
    """Reclaim and reprocess messages abandoned by a crashed consumer."""
    ensure_group(r)
    result: Any = r.xautoclaim(
        EXEC_STREAM, SUPERVISOR_GROUP, consumer,
        min_idle_time=min_idle_ms, start_id="0-0", count=count,
    )
    entries = result[1]
    outcomes: list[str] = []
    for msg_id, fields in entries:
        if fields:
            outcomes.append(process_message(session, r, msg_id, fields))
        else:  # tombstone (already deleted) — just ACK it away
            r.xack(EXEC_STREAM, SUPERVISOR_GROUP, msg_id)
    return outcomes
