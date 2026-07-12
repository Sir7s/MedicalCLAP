"""Bidirectional retrieval: CT->Text and Text->CT (P13 Subphase 5).

Spec (Architecture §2.2 + §8.4):
  - TWO independent paths: CT-only and Text-only. NO hybrid fusion.
  - CT->Report and Report->CT are equally important.
  - Distance: cosine over 512-d L2-normalized embeddings (§8.6). Since vectors
    are L2-normalized, cosine == dot product, so a single matrix-vector product
    gives every score.

This is the in-memory numpy backend (no Qdrant needed) used for tests and for
evaluating placeholder embeddings. The real §7.4 path is one call away:
`client.search(collection, query_vector, query_filter=modality, limit=top_k)`
against the versioned collection, returning the same SearchHit shape.

§8.7: a returned score is an "embedding similarity score, not a diagnostic
probability"; scores are not comparable across deployments.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .embeddings import EmbeddingRecord


@dataclass(frozen=True)
class SearchHit:
    point_id: str
    case_id: str
    modality: str
    score: float  # cosine similarity, NOT a probability (§8.7)


def _rank(query: np.ndarray, gallery: list[EmbeddingRecord], top_k: int) -> list[SearchHit]:
    if not gallery:
        return []
    # (N, 512) @ (512,) -> (N,) cosine scores (vectors are L2-normalized).
    matrix = np.stack([r.vector for r in gallery])
    scores = matrix @ query.astype(np.float32)
    # Top-k by descending score. argsort is ascending, so negate.
    order = np.argsort(-scores)[:top_k]
    return [
        SearchHit(
            point_id=gallery[i].point_id,
            case_id=gallery[i].payload.case_id,
            modality=gallery[i].payload.modality,
            score=float(scores[i]),
        )
        for i in order
    ]


def _by_modality(gallery: list[EmbeddingRecord], modality: str) -> list[EmbeddingRecord]:
    return [r for r in gallery if r.payload.modality == modality]


def ct_to_text(query_vector: np.ndarray, gallery: list[EmbeddingRecord],
               top_k: int = 10) -> list[SearchHit]:
    """CT query -> ranked report points (Text-only path)."""
    return _rank(query_vector, _by_modality(gallery, "report"), top_k)


def text_to_ct(query_vector: np.ndarray, gallery: list[EmbeddingRecord],
               top_k: int = 10) -> list[SearchHit]:
    """Text query -> ranked CT points (CT-only path)."""
    return _rank(query_vector, _by_modality(gallery, "ct"), top_k)
