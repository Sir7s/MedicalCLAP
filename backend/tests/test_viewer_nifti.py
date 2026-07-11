"""P8 unit tests — NIfTI validation (synthetic fixtures, no DB)."""
from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.viewer import nifti


def _write(tmp: Path, data: np.ndarray, affine: np.ndarray | None = None) -> Path:
    aff = affine if affine is not None else np.diag([1.0, 1.0, 2.0, 1.0])
    p = tmp / "vol.nii.gz"
    nib.save(nib.Nifti1Image(data, aff), str(p))
    return p


def test_valid_3d_accepted(tmp_path):
    data = (np.random.default_rng(0).random((32, 32, 16)) * 1000 - 500).astype(np.int16)
    meta = nifti.validate_and_meta(_write(tmp_path, data))
    assert meta.shape == (32, 32, 16)
    assert meta.spacing == (1.0, 1.0, 2.0)
    assert len(meta.orientation) == 3
    assert meta.window_width > 0


def test_4d_rejected(tmp_path):
    data = np.zeros((16, 16, 16, 3), dtype=np.int16)
    with pytest.raises(nifti.NiftiValidationError):
        nifti.validate_and_meta(_write(tmp_path, data))


def test_trailing_singleton_4th_dim_ok(tmp_path):
    data = np.zeros((16, 16, 16, 1), dtype=np.int16)
    meta = nifti.validate_and_meta(_write(tmp_path, data))
    assert meta.shape == (16, 16, 16)


def test_nan_rejected(tmp_path):
    data = np.zeros((16, 16, 16), dtype=np.float32)
    data[0, 0, 0] = np.nan
    with pytest.raises(nifti.NiftiValidationError):
        nifti.validate_and_meta(_write(tmp_path, data))


def test_inf_rejected(tmp_path):
    data = np.zeros((16, 16, 16), dtype=np.float32)
    data[1, 2, 3] = np.inf
    with pytest.raises(nifti.NiftiValidationError):
        nifti.validate_and_meta(_write(tmp_path, data))


def test_corrupt_header_rejected(tmp_path):
    p = tmp_path / "bad.nii.gz"
    p.write_bytes(b"not a nifti file at all")
    with pytest.raises(nifti.NiftiValidationError):
        nifti.validate_and_meta(p)


def test_tiny_axis_rejected(tmp_path):
    data = np.zeros((4, 16, 16), dtype=np.int16)  # 4 < MIN_DIM
    with pytest.raises(nifti.NiftiValidationError):
        nifti.validate_and_meta(_write(tmp_path, data))


def test_slice_extraction_and_bounds(tmp_path):
    data = np.arange(32 * 32 * 16, dtype=np.float32).reshape(32, 32, 16)
    p = _write(tmp_path, data)
    ax = nifti.extract_slice(p, "axial", 0)
    assert ax.shape == (32, 32)
    sag = nifti.extract_slice(p, "sagittal", 5)
    assert sag.shape == (32, 16)
    with pytest.raises(nifti.NiftiValidationError):
        nifti.extract_slice(p, "axial", 999)
    with pytest.raises(nifti.NiftiValidationError):
        nifti.extract_slice(p, "oblique", 0)


def test_mip_projection(tmp_path):
    data = np.zeros((20, 24, 16), dtype=np.float32)
    data[5, 6, 7] = 900.0  # a bright voxel
    p = _write(tmp_path, data)
    ax = nifti.mip(p, "axial")   # project along k -> (i, j)
    assert ax.shape == (20, 24)
    assert ax[5, 6] == 900.0
    with pytest.raises(nifti.NiftiValidationError):
        nifti.mip(p, "bogus")


def test_downsample_bounds(tmp_path):
    data = np.zeros((200, 200, 200), dtype=np.int16)
    p = _write(tmp_path, data)
    arr, shape = nifti.downsample_int16(p, max_side=64)
    assert max(shape) <= 64
    assert arr.dtype == np.int16
