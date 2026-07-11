"""CT viewer API (P8): upload/validate NIfTI, serve volume/slice, annotations."""
from __future__ import annotations

import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db.base import get_sessionmaker
from ..db.models import CtAnnotation, CtVolume, WorkspaceSession
from ..storage import paths
from . import nifti

router = APIRouter(prefix="/api/ct", tags=["viewer"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB — a single chest CT


def _meta_dict(v: CtVolume) -> dict:
    return {
        "id": str(v.id), "workspace_id": str(v.workspace_id), "filename": v.filename,
        "shape": v.shape, "spacing": v.spacing, "affine": v.affine,
        "orientation": v.orientation, "dtype": v.dtype,
        "scalar_min": v.scalar_min, "scalar_max": v.scalar_max,
        "window_center": v.window_center, "window_width": v.window_width,
        "size_bytes": v.size_bytes,
    }


@router.post("/upload")
async def upload_ct(workspace_id: uuid.UUID = Form(...), file: UploadFile = File(...)) -> dict:
    name = file.filename or ""
    if not name.endswith((".nii", ".nii.gz")):
        raise HTTPException(400, "expected a .nii or .nii.gz file")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        if s.get(WorkspaceSession, workspace_id) is None:
            raise HTTPException(404, "workspace not found")

    # Stream to a temp file with a size cap.
    suffix = ".nii.gz" if name.endswith(".gz") else ".nii"
    total = 0
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, "file exceeds the size limit")
            tmp.write(chunk)

    try:
        meta = nifti.validate_and_meta(tmp_path)
    except nifti.NiftiValidationError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(422, f"invalid CT: {exc}") from exc

    ct_id = uuid.uuid4()
    dest_dir = paths.workspace_dir(str(workspace_id)) / "ct"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ct_id}{suffix}"
    tmp_path.replace(dest)

    with SessionLocal() as s, s.begin():
        v = CtVolume(
            id=ct_id, workspace_id=workspace_id, filename=file.filename,
            stored_path=str(dest), size_bytes=total,
            shape=list(meta.shape), spacing=list(meta.spacing), affine=meta.affine,
            orientation=meta.orientation, dtype=meta.dtype,
            scalar_min=meta.scalar_min, scalar_max=meta.scalar_max,
            window_center=meta.window_center, window_width=meta.window_width,
        )
        s.add(v)
        s.flush()
        return _meta_dict(v)


def _get_volume(ct_id: uuid.UUID) -> CtVolume:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        v = s.get(CtVolume, ct_id)
        if v is None:
            raise HTTPException(404, "CT not found")
        s.expunge(v)
        return v


@router.get("/{ct_id}/meta")
def ct_meta(ct_id: uuid.UUID) -> dict:
    return _meta_dict(_get_volume(ct_id))


@router.get("/{ct_id}/volume")
def ct_volume(ct_id: uuid.UUID, max_side: int = 128) -> Response:
    """Downsampled int16 volume (little-endian) for vtk.js, dims in headers."""
    v = _get_volume(ct_id)
    arr, ds_shape = nifti.downsample_int16(Path(v.stored_path), max_side=max_side)
    body = np.ascontiguousarray(arr, dtype="<i2").tobytes()
    return Response(
        content=body, media_type="application/octet-stream",
        headers={
            "X-Dims": ",".join(str(x) for x in ds_shape),         # (i, j, k)
            "X-Spacing": ",".join(str(x) for x in v.spacing),
            "X-Window-Center": str(v.window_center),
            "X-Window-Width": str(v.window_width),
            "X-Scalar-Range": f"{v.scalar_min},{v.scalar_max}",
        },
    )


@router.get("/{ct_id}/slice/{plane}/{index}")
def ct_slice(ct_id: uuid.UUID, plane: str, index: int) -> Response:
    v = _get_volume(ct_id)
    try:
        sl = nifti.extract_slice(Path(v.stored_path), plane, index)
    except nifti.NiftiValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    body = np.ascontiguousarray(sl, dtype="<f4").tobytes()
    return Response(
        content=body, media_type="application/octet-stream",
        headers={"X-Shape": ",".join(str(x) for x in sl.shape)},
    )


@router.get("/{ct_id}/mip/{plane}")
def ct_mip(ct_id: uuid.UUID, plane: str) -> Response:
    """Maximum-intensity projection (basic volume rendering) as float32 raw."""
    v = _get_volume(ct_id)
    try:
        img = nifti.mip(Path(v.stored_path), plane)
    except nifti.NiftiValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    body = np.ascontiguousarray(img, dtype="<f4").tobytes()
    return Response(
        content=body, media_type="application/octet-stream",
        headers={"X-Shape": ",".join(str(x) for x in img.shape),
                 "X-Scalar-Range": f"{v.scalar_min},{v.scalar_max}"},
    )


class AnnotationIn(BaseModel):
    plane: str = Field(pattern="^(axial|coronal|sagittal)$")
    slice_index: int = Field(ge=0)
    points: list[list[float]] = Field(min_length=3)
    label: str | None = Field(default=None, max_length=128)


@router.post("/{ct_id}/annotations")
def add_annotation(ct_id: uuid.UUID, ann: AnnotationIn) -> dict:
    v = _get_volume(ct_id)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s, s.begin():
        row = CtAnnotation(
            ct_volume_id=ct_id, workspace_id=v.workspace_id, plane=ann.plane,
            slice_index=ann.slice_index, points=ann.points, label=ann.label,
        )
        s.add(row)
        s.flush()
        return {"id": str(row.id), "plane": row.plane, "slice_index": row.slice_index,
                "points": row.points, "label": row.label}


@router.get("/{ct_id}/annotations")
def list_annotations(ct_id: uuid.UUID) -> list[dict]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s:
        rows = s.execute(
            select(CtAnnotation).where(CtAnnotation.ct_volume_id == ct_id)
            .order_by(CtAnnotation.created_at)
        ).scalars().all()
        return [{"id": str(r.id), "plane": r.plane, "slice_index": r.slice_index,
                 "points": r.points, "label": r.label} for r in rows]


@router.delete("/annotations/{annotation_id}")
def delete_annotation(annotation_id: uuid.UUID) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as s, s.begin():
        row = s.get(CtAnnotation, annotation_id)
        if row is None:
            raise HTTPException(404, "annotation not found")
        s.delete(row)
    return {"deleted": str(annotation_id)}
