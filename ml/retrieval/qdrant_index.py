"""Versioned Qdrant collection: create + ingest (P13 Subphase 3).

Spec anchors:
  - §8.2/§8.3: 512-d, L2-normalized embeddings.
  - §8.6 Deployment Contract: distance metric is deployment-bound. L2-normalized
    ⇒ cosine (equivalent to dot). We use COSINE.
  - §7.4: queries use a Deployment's FIXED collection name (not a mutable alias),
    and the collection is bound to a data/model version. The versioned name below
    encodes that binding.
  - IMP-EXEC-013: QDRANT_TEMPORARILY_UNAVAILABLE is retryable (handled by the
    caller / worker, not here).

`qdrant_client` is imported lazily so the pure-Python modules (payload, digest,
eval) and their tests run without the dependency installed.
"""
from __future__ import annotations

from . import EMBED_DIM
from .embeddings import EmbeddingRecord

DISTANCE = "Cosine"  # §8.6, L2-normalized embeddings


def collection_name(model_version: str, dataset_revision: str) -> str:
    """Fixed, version-bound collection name (§7.4).

    Deterministic from the model + dataset version so a deployment always points
    at an immutable name rather than a mutable alias.
    """
    safe = lambda s: "".join(c if c.isalnum() else "_" for c in s)  # noqa: E731
    return f"medical_clip__{safe(model_version)}__{safe(dataset_revision)}"


def _client(url: str):
    try:
        from qdrant_client import QdrantClient
    except ImportError as e:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "qdrant-client is required to build/query the index. "
            "It is added in P13 (not yet pinned in requirements)."
        ) from e
    return QdrantClient(url=url)


def create_collection(client, name: str, dim: int = EMBED_DIM) -> None:
    """Create (or recreate) a 512-d cosine collection."""
    from qdrant_client.models import Distance, VectorParams

    client.recreate_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def ingest(client, name: str, records: list[EmbeddingRecord]) -> int:
    """Upsert all records; returns the number of points ingested.

    Qdrant point ids must be int/UUID, so the logical string point_id (used by
    the digest) is carried in the payload and a deterministic UUID5 is used as
    the Qdrant id.
    """
    import uuid

    from qdrant_client.models import PointStruct

    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, r.point_id)),
            vector=r.vector.astype("float32").tolist(),
            payload=r.payload.to_dict(),
        )
        for r in records
    ]
    client.upsert(collection_name=name, points=points)
    return len(points)


def build_index(url: str, records: list[EmbeddingRecord], model_version: str,
                dataset_revision: str) -> str:
    """End-to-end: create the versioned collection and ingest. Returns its name."""
    name = collection_name(model_version, dataset_revision)
    client = _client(url)
    create_collection(client, name)
    ingest(client, name, records)
    return name
