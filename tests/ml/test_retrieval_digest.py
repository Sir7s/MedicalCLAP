"""P13 tests — Qdrant Content Digest (§7.5 / IMP-DATA-001).

Gates: deterministic, order-invariant (sorted by point_id), sensitive to any
vector/payload change, rejects NaN/Inf and wrong dimension, rejects duplicate
point ids.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.retrieval import EMBED_DIM  # noqa: E402
from ml.retrieval.digest import (  # noqa: E402
    collection_content_manifest_sha256,
    content_line,
    vector_sha256,
)
from ml.retrieval.embeddings import load_embeddings  # noqa: E402


def test_vector_sha256_is_float32_le_bytes():
    v = np.arange(EMBED_DIM, dtype=np.float32)
    expected = hashlib.sha256(np.ascontiguousarray(v, dtype="<f4").tobytes()).hexdigest()
    assert vector_sha256(v) == expected


def test_vector_sha256_rejects_nonfinite_and_bad_dim():
    bad = np.zeros(EMBED_DIM, dtype=np.float32)
    bad[0] = np.inf
    with pytest.raises(ValueError):
        vector_sha256(bad)
    with pytest.raises(ValueError):
        vector_sha256(np.zeros(EMBED_DIM - 1, dtype=np.float32))


def test_content_line_format():
    line = content_line("case_0001:ct", "AB", "cd")
    # UTF8(point_id) + NUL + lower(vsha) + NUL + lower(psha) + LF
    assert line == b"case_0001:ct\x00ab\x00cd\n"


def test_manifest_deterministic_and_order_invariant():
    recs = load_embeddings(n_cases=8, seed=1)
    h1 = collection_content_manifest_sha256(recs)
    h2 = collection_content_manifest_sha256(list(reversed(recs)))
    assert h1 == h2  # sorted by point_id => input order irrelevant


def test_manifest_sensitive_to_vector_change():
    recs = load_embeddings(n_cases=8, seed=1)
    base = collection_content_manifest_sha256(recs)
    recs[0].vector[0] = np.float32(recs[0].vector[0] + 0.001)
    assert collection_content_manifest_sha256(recs) != base


def test_manifest_rejects_duplicate_point_id():
    recs = load_embeddings(n_cases=2, seed=1)
    dup = [recs[0], recs[0]]
    with pytest.raises(ValueError):
        collection_content_manifest_sha256(dup)
