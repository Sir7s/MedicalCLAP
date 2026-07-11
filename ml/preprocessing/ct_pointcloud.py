"""Deterministic CT volume -> 32,768 (x, y, z, density) points (P9).

Pipeline (Architecture SPEC-07 §8.2):
    reorient to RAS -> resample to isotropic spacing -> HU clip + normalize
    -> body mask -> gradient magnitude
    -> sample 50% body / 25% high-gradient / 25% global (seeded)
    -> coordinates normalized to [-1, 1], density in [0, 1]

Given the same input volume and config (incl. seed), the output point cloud is
bit-identical (proved by `test_determinism`). No NaN/Inf ever leaves the sampler.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

from .config import DEFAULT, PreprocConfig


@dataclass
class PointCloud:
    points: np.ndarray            # (N, 4) float32: x, y, z in [-1,1], density in [0,1]
    source: np.ndarray           # (N,) uint8: 0=body, 1=gradient, 2=global
    resampled_shape: tuple[int, int, int]
    resampled_spacing: tuple[float, float, float]


def _reorient_ras(path: Path) -> tuple[np.ndarray, np.ndarray]:
    img = nib.as_closest_canonical(nib.load(str(path)))
    data = np.asanyarray(img.dataobj).astype(np.float32)
    return np.squeeze(data), np.asarray(img.header.get_zooms()[:3], dtype=float)


def _resample(vol: np.ndarray, spacing: np.ndarray, cfg: PreprocConfig) -> tuple[np.ndarray, tuple]:
    target = np.asarray(cfg.target_spacing, dtype=float)
    factors = spacing / target
    out = ndimage.zoom(vol, factors, order=cfg.interpolation_order, mode="nearest")
    return out.astype(np.float32), tuple(cfg.target_spacing)


def _normalize_density(vol: np.ndarray, cfg: PreprocConfig) -> np.ndarray:
    clipped = np.clip(vol, cfg.hu_min, cfg.hu_max)
    density = (clipped - cfg.hu_min) / (cfg.hu_max - cfg.hu_min)
    return density.astype(np.float32)


def _body_mask(vol: np.ndarray, cfg: PreprocConfig) -> np.ndarray:
    mask = vol > cfg.body_hu_threshold
    if not mask.any():
        return np.ones_like(mask)
    labels, n = ndimage.label(mask)
    if n <= 1:
        return mask
    counts = np.bincount(labels.ravel())
    counts[0] = 0  # background
    return labels == counts.argmax()


def _gradient_magnitude(density: np.ndarray) -> np.ndarray:
    gx, gy, gz = np.gradient(density)
    return np.sqrt(gx * gx + gy * gy + gz * gz).astype(np.float32)


def _coords_unit(idx: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Flat indices -> (x,y,z) normalized to [-1, 1]."""
    ijk = np.stack(np.unravel_index(idx, shape), axis=1).astype(np.float32)  # (n,3)
    denom = np.maximum(np.asarray(shape, dtype=np.float32) - 1.0, 1.0)
    return (ijk / denom) * 2.0 - 1.0


def _sample(rng: np.random.Generator, pool: np.ndarray, n: int) -> np.ndarray:
    if n <= 0 or pool.size == 0:
        return np.empty(0, dtype=np.int64)
    replace = pool.size < n
    picked = rng.choice(pool.size, size=n, replace=replace)
    return pool[picked]


def preprocess(path: Path, cfg: PreprocConfig = DEFAULT) -> PointCloud:
    vol_hu, spacing = _reorient_ras(path)
    vol_hu, out_spacing = _resample(vol_hu, spacing, cfg)
    density = _normalize_density(vol_hu, cfg)
    shape = (int(density.shape[0]), int(density.shape[1]), int(density.shape[2]))

    mask = _body_mask(vol_hu, cfg)
    gradmag = _gradient_magnitude(density)

    body_pool = np.flatnonzero(mask)
    all_pool = np.arange(density.size, dtype=np.int64)
    thresh = np.percentile(gradmag, cfg.gradient_percentile)
    grad_pool = np.flatnonzero(gradmag >= thresh)

    rng = np.random.default_rng(cfg.seed)
    n_body, n_grad, n_global = cfg.counts()
    idx_body = _sample(rng, body_pool, n_body)
    idx_grad = _sample(rng, grad_pool, n_grad)
    idx_global = _sample(rng, all_pool, n_global)

    idx = np.concatenate([idx_body, idx_grad, idx_global])
    source = np.concatenate([
        np.zeros(idx_body.size, np.uint8),
        np.ones(idx_grad.size, np.uint8),
        np.full(idx_global.size, 2, np.uint8),
    ])

    coords = _coords_unit(idx, shape)
    dens = density.ravel()[idx].astype(np.float32)[:, None]
    points = np.concatenate([coords, dens], axis=1).astype(np.float32)

    if not np.all(np.isfinite(points)):
        raise ValueError("preprocessing produced non-finite points")
    return PointCloud(points=points, source=source,
                      resampled_shape=shape, resampled_spacing=out_spacing)


def save_cache(pc: PointCloud, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, points=pc.points, source=pc.source)
    return out


def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="CT -> point cloud (P9)")
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT.seed)
    args = ap.parse_args(argv)
    from dataclasses import replace

    pc = preprocess(Path(args.input), replace(DEFAULT, seed=args.seed))
    save_cache(pc, Path(args.out))
    print(f"points={pc.points.shape} shape={pc.resampled_shape} "
          f"spacing={pc.resampled_spacing} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
