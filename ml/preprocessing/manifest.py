"""Preprocessing manifest (P9, SPEC-07 §8.5).

Records everything needed to reproduce a point cloud: config, seed, input hash,
output hash, resampled geometry, and library versions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nibabel
import numpy
import scipy

from .config import PreprocConfig
from .ct_pointcloud import PointCloud


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_manifest(input_path: Path, pc: PointCloud, cfg: PreprocConfig) -> dict:
    return {
        "schema": "ct_preprocessing_manifest/v1",
        "input_sha256": _sha256_bytes(input_path.read_bytes()),
        "config": cfg.to_dict(),
        "seed": cfg.seed,
        "resampled_shape": list(pc.resampled_shape),
        "resampled_spacing": list(pc.resampled_spacing),
        "n_points": int(pc.points.shape[0]),
        "points_sha256": _sha256_bytes(pc.points.tobytes()),
        "source_counts": {
            "body": int((pc.source == 0).sum()),
            "gradient": int((pc.source == 1).sum()),
            "global": int((pc.source == 2).sum()),
        },
        "coordinate_bounds": {
            "xyz_min": [float(pc.points[:, i].min()) for i in range(3)],
            "xyz_max": [float(pc.points[:, i].max()) for i in range(3)],
            "density_min": float(pc.points[:, 3].min()),
            "density_max": float(pc.points[:, 3].max()),
        },
        "library_versions": {
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
            "nibabel": nibabel.__version__,
        },
        "precision_policy": cfg.precision,
    }


def write_manifest(manifest: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out
