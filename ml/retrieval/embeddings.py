"""Embedding source for the retrieval index (P13 Subphase 2).

PLACEHOLDER. The real CT encoder (PointNet++, §8.2) and text encoder
(BioClinicalBERT + projection head, §8.3) both emit 512-d L2-normalized
embeddings. Until P11-P12 land, `load_embeddings()` returns deterministic
random vectors with the SAME contract (512-d, float32, L2-normalized, no
NaN/Inf), so every downstream module — index, digest, search, eval — can be
built and tested now.

    # TODO(P12): swap the body of load_embeddings() for the real encoder output
    #            (an encode() call or a loaded .npy/.parquet). Nothing else in
    #            ml/retrieval changes.

The placeholder deliberately gives each case a shared latent so a CT and its
matching report land near each other — retrieval on placeholder data therefore
has real signal, which lets search/eval be exercised meaningfully.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import EMBED_DIM
from .payload import Payload, make_point_id

# How real embeddings arrive is the one cross-code interface not fixed by the
# spec (Master Plan P13 open item). Kept behind this function on purpose.
DEFAULT_DATASET_REVISION = "placeholder-dataset-rev0"
DEFAULT_MODEL_VERSION = "placeholder-model-v0"


@dataclass(frozen=True)
class EmbeddingRecord:
    point_id: str
    vector: np.ndarray      # shape (512,), float32, L2-normalized
    payload: Payload


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n == 0:
        raise ValueError("cannot L2-normalize a zero vector")
    return (v / n).astype(np.float32)


def load_embeddings(
    n_cases: int = 64,
    seed: int = 13,
    noise: float = 0.15,
    split: str = "test",
    dataset_revision: str = DEFAULT_DATASET_REVISION,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[EmbeddingRecord]:
    """Return paired CT/report embedding records (PLACEHOLDER, deterministic).

    Each case gets a shared latent; the CT and report vectors are that latent
    plus independent noise, then L2-normalized — so matching pairs are close.
    """
    rng = np.random.default_rng(seed)
    records: list[EmbeddingRecord] = []
    for i in range(n_cases):
        case_id = f"case_{i:04d}"
        latent = rng.standard_normal(EMBED_DIM).astype(np.float32)
        for modality in ("ct", "report"):
            v = latent + noise * rng.standard_normal(EMBED_DIM).astype(np.float32)
            vector = _l2_normalize(v)
            point_id = make_point_id(case_id, modality)
            payload = Payload(
                point_id=point_id,
                modality=modality,
                case_id=case_id,
                dataset_revision=dataset_revision,
                model_version=model_version,
                split=split,
            )
            records.append(EmbeddingRecord(point_id, vector, payload))
    return records
