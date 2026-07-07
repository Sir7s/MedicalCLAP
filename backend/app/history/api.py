"""History API v0 (P5) — minimal save/list/get; only `ready` records visible."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db.base import get_sessionmaker
from ..db.models import HistoryRecord
from . import service

router = APIRouter(prefix="/api/history", tags=["history"])


class SaveRequest(BaseModel):
    workspace_id: uuid.UUID
    title: str = Field(min_length=1, max_length=256)
    payload: dict = Field(default_factory=dict)


@router.post("/save")
def save_history(req: SaveRequest) -> dict:
    SessionLocal = get_sessionmaker()
    try:
        record_id = service.save_lightweight_history(
            SessionLocal, workspace_id=req.workspace_id, title=req.title,
            payload=req.payload,
        )
    except service.HistorySaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"history_record_id": str(record_id), "state": "ready"}


@router.get("")
def list_history(workspace_id: uuid.UUID | None = None) -> list[dict]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        return service.list_ready(s, workspace_id)


@router.get("/{record_id}")
def get_history(record_id: uuid.UUID) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        rec = s.get(HistoryRecord, record_id)
        if rec is None or rec.state != "ready":  # non-ready is invisible
            raise HTTPException(status_code=404, detail="history record not found")
        return {"id": str(rec.id), "title": rec.title, "profile": rec.profile,
                "state": rec.state, "meta": rec.meta,
                "created_at": rec.created_at.isoformat()}
