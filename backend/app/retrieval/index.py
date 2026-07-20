"""Qdrant vector index for CT-CLIP embeddings (P13, AUP-005).

Stores one point per CT volume: the CT-CLIP image embedding (512-d, cosine) plus a
payload carrying the volume name, its report text and its 18-dim findings vector.
Text->CT and CT->CT queries both run as ANN search over the same collection; the
report side is searched via the stored report embedding in a parallel collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..config import get_settings

VOLUME_COLLECTION = "ct_volumes"
REPORT_COLLECTION = "ct_reports"
EMBED_DIM = 512


@dataclass
class Hit:
    volume: str
    score: float
    findings: list[float]
    report: str


def get_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(host=s.qdrant_host, port=s.qdrant_port, timeout=30)


def ensure_collections(client: QdrantClient, dim: int = EMBED_DIM) -> None:
    """Idempotently create both collections with cosine distance."""
    existing = {c.name for c in client.get_collections().collections}
    for name in (VOLUME_COLLECTION, REPORT_COLLECTION):
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )


def upsert_volumes(client: QdrantClient, records: list[dict[str, Any]]) -> int:
    """records: {id, vector, volume, report, findings}. Returns count upserted."""
    points = [
        qm.PointStruct(
            id=r["id"],
            vector=list(r["vector"]),
            payload={"volume": r["volume"], "report": r.get("report", ""),
                     "findings": list(r.get("findings", []))},
        )
        for r in records
    ]
    if points:
        client.upsert(collection_name=VOLUME_COLLECTION, points=points, wait=True)
    return len(points)


def upsert_reports(client: QdrantClient, records: list[dict[str, Any]]) -> int:
    points = [
        qm.PointStruct(
            id=r["id"],
            vector=list(r["vector"]),
            payload={"volume": r["volume"], "report": r.get("report", ""),
                     "findings": list(r.get("findings", []))},
        )
        for r in records
    ]
    if points:
        client.upsert(collection_name=REPORT_COLLECTION, points=points, wait=True)
    return len(points)


def search(client: QdrantClient, collection: str, vector: list[float],
           limit: int = 50) -> list[Hit]:
    res = client.query_points(collection_name=collection, query=list(vector),
                              limit=limit, with_payload=True).points
    out: list[Hit] = []
    for p in res:
        pl = p.payload or {}
        out.append(Hit(volume=str(pl.get("volume", p.id)), score=float(p.score),
                       findings=[float(x) for x in pl.get("findings", [])],
                       report=str(pl.get("report", ""))))
    return out


def count(client: QdrantClient, collection: str) -> int:
    try:
        return int(client.count(collection_name=collection, exact=True).count)
    except Exception:  # noqa: BLE001 - collection may not exist yet
        return 0
