"""Retrieval API (P13, AUP-005): two-stage search with explanations."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .embedder import CtClipEmbedder, EmbedderUnavailable
from .index import REPORT_COLLECTION, VOLUME_COLLECTION, count, get_client
from .rerank import DEFAULT_ALPHA, FINDING_NAMES
from .service import DEFAULT_TOP, RECALL_K, search_by_text, search_by_volume

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


class TextQuery(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    top: int = Field(default=DEFAULT_TOP, ge=1, le=50)
    alpha: float = Field(default=DEFAULT_ALPHA, ge=0.0, le=1.0)
    recall_k: int = Field(default=RECALL_K, ge=1, le=200)


class VolumeQuery(BaseModel):
    path: str = Field(min_length=1)
    top: int = Field(default=DEFAULT_TOP, ge=1, le=50)
    alpha: float = Field(default=DEFAULT_ALPHA, ge=0.0, le=1.0)
    recall_k: int = Field(default=RECALL_K, ge=1, le=200)


@router.get("/status")
def status() -> dict:
    """Index sizes + whether the CT-CLIP inference service is reachable."""
    client = get_client()
    return {
        "volumes_indexed": count(client, VOLUME_COLLECTION),
        "reports_indexed": count(client, REPORT_COLLECTION),
        "embedder_available": CtClipEmbedder().health(),
        "findings": FINDING_NAMES,
        "default_alpha": DEFAULT_ALPHA,
    }


@router.post("/search/text")
def search_text(q: TextQuery) -> dict:
    """Natural-language query -> matching CT volumes, with findings explanations."""
    try:
        return search_by_text(q.text, top=q.top, alpha=q.alpha, recall_k=q.recall_k)
    except EmbedderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/search/volume")
def search_volume(q: VolumeQuery) -> dict:
    """CT volume -> matching reports, re-ranked by the CT's own zero-shot findings."""
    try:
        return search_by_volume(q.path, top=q.top, alpha=q.alpha, recall_k=q.recall_k)
    except EmbedderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
