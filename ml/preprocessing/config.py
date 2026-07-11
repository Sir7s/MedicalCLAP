"""Preprocessing configuration (P9, Architecture SPEC-07 §8.2/§8.5).

Every field is part of the reproducibility contract and is recorded verbatim in
the preprocessing manifest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

N_POINTS = 32_768  # SPEC-07 §8.2


@dataclass(frozen=True)
class PreprocConfig:
    # Orientation / resampling
    orientation: str = "RAS"                    # canonical reorientation target
    target_spacing: tuple[float, float, float] = (2.0, 2.0, 2.0)  # mm, isotropic
    interpolation_order: int = 1                # trilinear
    # HU windowing / normalization
    hu_min: float = -1000.0
    hu_max: float = 1000.0                       # density = (clip(HU)-min)/(max-min) -> [0,1]
    body_hu_threshold: float = -500.0            # voxels above -> body
    # Point sampling (SPEC-07 §8.2: 50% body / 25% high-gradient / 25% global)
    n_points: int = N_POINTS
    ratio_body: float = 0.50
    ratio_gradient: float = 0.25
    ratio_global: float = 0.25
    gradient_percentile: float = 90.0            # "high gradient" cutoff
    coord_norm: str = "unit_symmetric"           # coords -> [-1, 1]
    seed: int = 42
    precision: str = "float32"

    def counts(self) -> tuple[int, int, int]:
        n_body = int(round(self.n_points * self.ratio_body))
        n_grad = int(round(self.n_points * self.ratio_gradient))
        n_global = self.n_points - n_body - n_grad
        return n_body, n_grad, n_global

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = PreprocConfig()
