"""Dead-letter protocol (P3, Appendix IMP-EXEC-001/002).

Invalid execution-queue messages are never silently dropped: they are persisted
to `dead_letter_commands`, an audit event is written, and the original message
is ACKed. Dead letters are NEVER auto-replayed — an administrator must act.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..db import repository as repo
from ..db.models import DeadLetterCommand


def dead_letter(
    session: Session,
    *,
    queue_name: str,
    error_code: str,
    detected_by: str,
    original_message_id: str | None = None,
    command_id: uuid.UUID | None = None,
    model_job_id: str | None = None,
    raw_payload: dict | None = None,
    error_message: str | None = None,
    delivery_attempt: int | None = None,
    command_schema_version: str | None = None,
) -> uuid.UUID:
    """Persist a dead-letter record + audit event in one transaction. Returns its id."""
    with session.begin():
        dl = DeadLetterCommand(
            original_message_id=original_message_id,
            queue_name=queue_name,
            command_id=command_id,
            model_job_id=model_job_id,
            raw_payload=raw_payload,
            command_schema_version=command_schema_version,
            delivery_attempt=delivery_attempt,
            error_code=error_code,
            error_message=error_message,
            detected_by=detected_by,
            resolution_status="unresolved",
        )
        session.add(dl)
        session.flush()
        repo.append_audit(
            session,
            actor=detected_by,
            action="dead_letter",
            aggregate_type="command",
            aggregate_id=str(command_id) if command_id else None,
            detail={"error_code": error_code, "queue": queue_name},
        )
        return dl.id
