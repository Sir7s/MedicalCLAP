"""Qdrant point payload schema + canonical JSON (P13 Subphase 1).

The spec (Architecture §7.5, Appendix IMP-DATA-001) fixes only that the payload
is serialized as **Canonical JSON** and that the collection is bound to the
data/model version. It does NOT enumerate the payload fields, so the schema
below is P13's proposed design (Master Plan P13 Subphase 1 "定义 Payload
Schema"). Keep the field set and the point-id scheme in one place so a later
change is one edit.

OPEN ITEM (confirm with project owner): the spec says "Canonical JSON" without
citing a precise profile (e.g. RFC 8785 / JCS). We use the widely-used
deterministic form: UTF-8, keys sorted, compact separators, no NaN/Inf. For the
current string/int-only payloads this matches JCS output; revisit here if the
owner mandates a stricter profile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

# Payload schema version — bump on any field/serialization change so old
# indexes remain interpretable.
PAYLOAD_SCHEMA_VERSION = "medical_clip_payload/v1"

# Point-id scheme (logical id used by the content digest and stored in the
# payload). Qdrant's own point id is a UUID derived from this — see qdrant_index.
# OPEN ITEM: confirm the case_id/point_id pairing with the owner so a CT and its
# report link up for eval ground-truth.
MODALITIES = ("ct", "report")


def make_point_id(case_id: str, modality: str) -> str:
    """Logical, human-readable point id, unique per (case, modality)."""
    if modality not in MODALITIES:
        raise ValueError(f"unknown modality {modality!r}; expected {MODALITIES}")
    return f"{case_id}:{modality}"


@dataclass(frozen=True)
class Payload:
    point_id: str
    modality: str          # "ct" | "report"
    case_id: str           # links a CT to its matching report
    dataset_revision: str  # binds the index to a data version (§7.4)
    model_version: str     # binds the index to a model version (§7.4)
    split: str             # train | val | test

    def to_dict(self) -> dict:
        return {
            "schema": PAYLOAD_SCHEMA_VERSION,
            "point_id": self.point_id,
            "modality": self.modality,
            "case_id": self.case_id,
            "dataset_revision": self.dataset_revision,
            "model_version": self.model_version,
            "split": self.split,
        }


def canonical_json_bytes(obj: dict) -> bytes:
    """Deterministic Canonical JSON encoding (Appendix IMP-DATA-001).

    Sorted keys, compact separators, UTF-8, ``ensure_ascii=False``. Rejects
    NaN/Inf (``allow_nan=False``) so a payload can never hash non-reproducibly.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
