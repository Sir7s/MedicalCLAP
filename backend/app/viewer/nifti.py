"""NIfTI validation, metadata, and volume sampling (P8, SPEC-01 §2.2).

Formal MVP validation (Architecture SPEC-01 §2.2): structure, dimensionality,
affine, and size. Only a single 3-D chest CT is accepted; 4-D (or higher),
corrupt headers, and non-finite voxels are rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

MAX_DIM = 1024          # per-axis sanity bound
MIN_DIM = 8
MAX_VOXELS = 512 * 512 * 1024   # ~ guard against absurd volumes


class NiftiValidationError(ValueError):
    """Raised when an uploaded file is not an acceptable single 3-D CT."""


@dataclass
class VolumeMeta:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: list[list[float]]
    orientation: str            # e.g. "RAS", "LPS" axis codes
    dtype: str
    scalar_min: float
    scalar_max: float
    window_center: float
    window_width: float


def _load(path: Path):
    try:
        img = nib.load(str(path))
    except Exception as exc:  # noqa: BLE001 - corrupt/unreadable header
        raise NiftiValidationError(f"unreadable NIfTI: {exc}") from exc
    if not isinstance(img, (nib.Nifti1Image, nib.Nifti2Image)):
        raise NiftiValidationError("not a NIfTI-1/2 image")
    return img


def validate_and_meta(path: Path) -> VolumeMeta:
    img = _load(path)
    shape = tuple(int(x) for x in img.shape)

    # Dimensionality: exactly 3-D (a trailing singleton 4th dim is tolerated).
    core = [d for d in shape if d > 1]
    if len(shape) > 4 or (len(shape) == 4 and shape[3] > 1):
        raise NiftiValidationError(f"expected a single 3-D volume, got shape {shape}")
    if len(core) != 3:
        raise NiftiValidationError(f"volume is not 3-D (effective shape {tuple(core)})")

    dims3: tuple[int, int, int] = (int(shape[0]), int(shape[1]), int(shape[2]))
    for d in dims3:
        if d < MIN_DIM or d > MAX_DIM:
            raise NiftiValidationError(f"axis size {d} out of bounds [{MIN_DIM},{MAX_DIM}]")
    if int(np.prod(dims3)) > MAX_VOXELS:
        raise NiftiValidationError("volume exceeds the maximum voxel budget")

    affine = np.asarray(img.affine, dtype=float)
    if affine.shape != (4, 4) or not np.all(np.isfinite(affine)):
        raise NiftiValidationError("invalid or non-finite affine")
    try:
        orientation = "".join(nib.aff2axcodes(affine))
    except Exception as exc:  # noqa: BLE001
        raise NiftiValidationError(f"cannot derive orientation: {exc}") from exc

    zooms = img.header.get_zooms()[:3]
    spacing: tuple[float, float, float] = (float(zooms[0]), float(zooms[1]), float(zooms[2]))
    if not all(np.isfinite(spacing)) or any(s <= 0 for s in spacing):
        raise NiftiValidationError(f"invalid voxel spacing {spacing}")

    # Voxel finiteness (reject NaN/Inf). dataobj streams without loading twice.
    data = np.asanyarray(img.dataobj)
    data = np.squeeze(data)
    if not np.all(np.isfinite(data)):
        raise NiftiValidationError("volume contains NaN or Inf voxels")

    fdata = data.astype(np.float32, copy=False)
    smin, smax = float(fdata.min()), float(fdata.max())
    # Default window from robust HU percentiles (chest CT).
    lo, hi = np.percentile(fdata, [1.0, 99.0])
    center = float((lo + hi) / 2.0)
    width = float(max(hi - lo, 1.0))

    return VolumeMeta(
        shape=dims3,
        spacing=spacing,
        affine=affine.tolist(),
        orientation=orientation,
        dtype=str(data.dtype),
        scalar_min=smin,
        scalar_max=smax,
        window_center=center,
        window_width=width,
    )


def load_array(path: Path) -> np.ndarray:
    """Return the squeezed 3-D volume as float32 (validated caller)."""
    img = _load(path)
    return np.squeeze(np.asanyarray(img.dataobj)).astype(np.float32, copy=False)


def downsample_int16(path: Path, max_side: int = 128) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Downsample to <= max_side per axis, clipped to int16, for vtk.js volume
    rendering. Returns (array[z,y,x] int16, downsampled_shape)."""
    vol = load_array(path)
    factors = [max(1, int(np.ceil(s / max_side))) for s in vol.shape]
    ds = vol[:: factors[0], :: factors[1], :: factors[2]]
    ds = np.clip(ds, -32768, 32767).astype(np.int16)
    return ds, (int(ds.shape[0]), int(ds.shape[1]), int(ds.shape[2]))


def mip(path: Path, plane: str) -> np.ndarray:
    """Maximum-intensity projection along a plane's normal — basic volume
    rendering. Returns a 2-D float32 image."""
    vol = load_array(path)
    planes = {"sagittal": 0, "coronal": 1, "axial": 2}
    if plane not in planes:
        raise NiftiValidationError(f"unknown plane {plane!r}")
    return vol.max(axis=planes[plane]).astype(np.float32)


def extract_slice(path: Path, plane: str, index: int) -> np.ndarray:
    """Return a 2-D float32 slice for a plane in {axial,coronal,sagittal}."""
    vol = load_array(path)  # axes (i, j, k)
    planes = {"sagittal": 0, "coronal": 1, "axial": 2}
    if plane not in planes:
        raise NiftiValidationError(f"unknown plane {plane!r}")
    axis = planes[plane]
    n = vol.shape[axis]
    if index < 0 or index >= n:
        raise NiftiValidationError(f"slice {index} out of range [0,{n})")
    return np.take(vol, index, axis=axis)
