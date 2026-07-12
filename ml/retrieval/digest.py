"""Qdrant Content Digest (P13 Subphase 4, Architecture §7.5 / Appendix IMP-DATA-001).

Normative form (IMP-DATA-001 "确定性内容清单"):

    line     = UTF8(point_id) + NUL + lowercase_vector_sha256
             + NUL + lowercase_payload_sha256 + LF
    manifest = SHA-256( concat( lines sorted by point_id ) )
             = collection_content_manifest_sha256

Vector rules (IMP-DATA-001):
  - IEEE 754 float32, little-endian, fixed dimension
  - no NaN / Inf
Payload rule:
  - Canonical JSON (see payload.canonical_json_bytes)

This mirrors the existing spec/dataset manifest hashing style
(scripts/spec_manifest.py, ml/datasets/ct_rate/manifest.py) so the whole
project hashes content the same way.
"""
from __future__ import annotations

import hashlib

import numpy as np

from . import EMBED_DIM
from .embeddings import EmbeddingRecord
from .payload import canonical_json_bytes


def vector_sha256(vector: np.ndarray, dim: int = EMBED_DIM) -> str:
    """SHA-256 of a vector's normative float32 little-endian bytes.

    Rejects wrong dimension and any NaN/Inf so a point can never hash
    non-reproducibly (IMP-DATA-001).
    """
    if vector.shape != (dim,):
        raise ValueError(f"expected shape ({dim},), got {vector.shape}")
    if not np.isfinite(vector).all():
        raise ValueError("vector contains NaN or Inf (forbidden by IMP-DATA-001)")
    # Force IEEE-754 float32 little-endian regardless of host byte order.
    le = np.ascontiguousarray(vector, dtype="<f4")
    return hashlib.sha256(le.tobytes()).hexdigest()


def payload_sha256(payload_dict: dict) -> str:
    """SHA-256 of the payload's Canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload_dict)).hexdigest()


def content_line(point_id: str, v_sha: str, p_sha: str) -> bytes:
    """One normative digest line (IMP-DATA-001)."""
    return (
        point_id.encode("utf-8") + b"\x00"
        + v_sha.lower().encode("ascii") + b"\x00"
        + p_sha.lower().encode("ascii") + b"\n"
    )


def collection_content_manifest_sha256(records: list[EmbeddingRecord]) -> str:
    """Deterministic content manifest hash over all points (§7.5).

    Point ids must be unique; lines are sorted by UTF-8 bytes of point_id
    (matching the dataset manifest's sort discipline) before hashing.
    """
    seen: set[str] = set()
    lines: list[bytes] = []
    for r in records:
        if r.point_id in seen:
            raise ValueError(f"duplicate point_id: {r.point_id!r}")
        seen.add(r.point_id)
        v_sha = vector_sha256(r.vector)
        p_sha = payload_sha256(r.payload.to_dict())
        lines.append(content_line(r.point_id, v_sha, p_sha))

    lines.sort(key=lambda ln: ln.split(b"\x00", 1)[0])
    h = hashlib.sha256()
    for ln in lines:
        h.update(ln)
    return h.hexdigest()
