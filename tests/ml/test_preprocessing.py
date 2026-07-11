"""P9 critical tests — deterministic CT preprocessing & point sampling.

Master Plan P9 gates: same input -> same point cloud; no NaN/Inf; coordinate
ranges; sampling ratios; spacing/affine handling; complete manifest.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import nibabel as nib
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.preprocessing import manifest as mf  # noqa: E402
from ml.preprocessing.config import DEFAULT, N_POINTS  # noqa: E402
from ml.preprocessing.ct_pointcloud import preprocess  # noqa: E402


def _phantom(tmp: Path, shape=(64, 64, 48), spacing=(1.0, 1.0, 1.0)) -> Path:
    """A chest-like phantom: air (-1000) with a soft-tissue cylinder (+50) and a
    denser insert (+300) to create gradients."""
    vol = np.full(shape, -1000.0, dtype=np.float32)
    zz, yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2]), indexing="ij"
    )
    cx = [s / 2 for s in shape]
    r = ((zz - cx[0]) ** 2 / (shape[0] / 2) ** 2
         + (yy - cx[1]) ** 2 / (shape[1] / 2) ** 2)
    vol[r < 0.8] = 50.0
    vol[(zz - cx[0]) ** 2 + (yy - cx[1]) ** 2 + (xx - cx[2]) ** 2 < 40] = 300.0
    p = tmp / "phantom.nii.gz"
    nib.save(nib.Nifti1Image(vol, np.diag([*spacing, 1.0])), str(p))
    return p


def test_determinism(tmp_path):
    p = _phantom(tmp_path)
    a = preprocess(p)
    b = preprocess(p)
    assert np.array_equal(a.points, b.points)
    assert np.array_equal(a.source, b.source)


def test_exact_point_count_and_finite(tmp_path):
    pc = preprocess(_phantom(tmp_path))
    assert pc.points.shape == (N_POINTS, 4)
    assert pc.points.dtype == np.float32
    assert np.all(np.isfinite(pc.points))


def test_coordinate_and_density_ranges(tmp_path):
    pc = preprocess(_phantom(tmp_path))
    xyz = pc.points[:, :3]
    dens = pc.points[:, 3]
    assert xyz.min() >= -1.0 - 1e-6 and xyz.max() <= 1.0 + 1e-6
    assert dens.min() >= 0.0 - 1e-6 and dens.max() <= 1.0 + 1e-6


def test_sampling_ratios(tmp_path):
    pc = preprocess(_phantom(tmp_path))
    n_body, n_grad, n_global = DEFAULT.counts()
    assert n_body + n_grad + n_global == N_POINTS
    assert int((pc.source == 0).sum()) == n_body      # 50%
    assert int((pc.source == 1).sum()) == n_grad      # 25%
    assert int((pc.source == 2).sum()) == n_global    # 25%


def test_seed_changes_sampling(tmp_path):
    p = _phantom(tmp_path)
    a = preprocess(p, replace(DEFAULT, seed=1))
    b = preprocess(p, replace(DEFAULT, seed=2))
    assert not np.array_equal(a.points, b.points)


def test_resamples_to_target_spacing(tmp_path):
    # Anisotropic 1mm input -> isotropic 2mm target halves each axis.
    p = _phantom(tmp_path, shape=(64, 64, 48), spacing=(1.0, 1.0, 1.0))
    pc = preprocess(p)
    assert pc.resampled_spacing == DEFAULT.target_spacing
    assert pc.resampled_shape == (32, 32, 24)


def test_different_spacing_same_geometry(tmp_path):
    # Same physical content at 2mm native needs no resample and yields the same
    # resampled grid as the 1mm phantom above (both land on the 2mm target).
    p2 = _phantom(tmp_path, shape=(32, 32, 24), spacing=(2.0, 2.0, 2.0))
    pc = preprocess(p2)
    assert pc.resampled_spacing == (2.0, 2.0, 2.0)
    assert pc.resampled_shape == (32, 32, 24)


def test_manifest_complete(tmp_path):
    p = _phantom(tmp_path)
    pc = preprocess(p)
    m = mf.build_manifest(p, pc, DEFAULT)
    for key in ("input_sha256", "points_sha256", "config", "seed",
                "resampled_shape", "source_counts", "coordinate_bounds",
                "library_versions", "precision_policy"):
        assert key in m
    assert m["n_points"] == N_POINTS
    assert set(m["library_versions"]) == {"numpy", "scipy", "nibabel"}
    # Manifest points hash must match a re-run (reproducibility).
    assert mf.build_manifest(p, preprocess(p), DEFAULT)["points_sha256"] == m["points_sha256"]
