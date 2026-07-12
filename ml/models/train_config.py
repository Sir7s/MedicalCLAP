"""Frozen training configuration (P12, SPEC-07; H-08 reproducibility).

Records everything that determines a training run. For local RTX 4050 (6 GB)
training the volume subset and point count are reduced from the full-scale
Colab target; this is recorded so the run is reproducible and honestly scoped.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TrainConfig:
    # Data: the full downloaded local subset (P7 patient-level split, train_fixed).
    # Slicing caps (select_subset takes [:n]); these equal the whole local subset.
    n_train: int = 556
    n_val: int = 127
    n_test: int = 118
    n_points: int = 16384          # local GPU budget (full-scale target 32768)
    seq_len: int = 128
    n_labels: int = 18
    # Optimization
    batch_size: int = 4
    epochs: int = 40
    lr: float = 1e-4
    weight_decay: float = 1e-4
    aux_weight: float = 0.5
    grad_clip: float = 1.0
    embed_dim: int = 512
    # Low-data regularization: freeze the 110M BioClinicalBERT backbone and train
    # only its projection (+ PointNet++/classifier). Full fine-tuning on a small
    # local subset memorizes the training pairs and does not generalize.
    freeze_text_backbone: bool = True
    # Runtime
    device: str = "cuda"
    amp: bool = True
    seed: int = 42
    num_workers: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = TrainConfig()
