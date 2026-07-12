"""P13 tests — payload schema + Canonical JSON (§7.5 / IMP-DATA-001).

Gates: deterministic canonical encoding, sorted keys, compact, NaN rejected.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.retrieval.payload import (  # noqa: E402
    Payload,
    canonical_json_bytes,
    make_point_id,
)


def _payload() -> Payload:
    return Payload(
        point_id="case_0001:ct",
        modality="ct",
        case_id="case_0001",
        dataset_revision="rev0",
        model_version="v0",
        split="test",
    )


def test_point_id_scheme():
    assert make_point_id("case_0001", "report") == "case_0001:report"
    with pytest.raises(ValueError):
        make_point_id("case_0001", "mri")


def test_canonical_json_is_sorted_and_compact():
    b = canonical_json_bytes({"b": 1, "a": 2})
    assert b == b'{"a":2,"b":1}'


def test_canonical_json_deterministic():
    p = _payload().to_dict()
    assert canonical_json_bytes(p) == canonical_json_bytes(dict(reversed(list(p.items()))))


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json_bytes({"x": float("nan")})


def test_payload_has_schema_and_fields():
    d = _payload().to_dict()
    assert d["schema"].startswith("medical_clip_payload/")
    for key in ("point_id", "modality", "case_id", "dataset_revision",
                "model_version", "split"):
        assert key in d
