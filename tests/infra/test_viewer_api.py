"""P8 integration tests — CT upload, serving, annotation persistence (live DB)."""
from __future__ import annotations

import os
import socket

import pytest

HOST = "127.0.0.1"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=1):
            return True
    except OSError:
        return False


_READY = False
if _port_open(5432):
    try:
        from app.db.base import get_engine
        from sqlalchemy import inspect

        _READY = inspect(get_engine()).has_table("ct_volumes")
    except Exception:  # noqa: BLE001
        _READY = False

pytestmark = pytest.mark.skipif(not _READY, reason="postgres/P8 schema not present")

if _READY:
    import numpy as np
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)


@pytest.fixture(autouse=True)
def _ws_root(tmp_path):
    os.environ["MEDCLIP_WORKSPACE_ROOT"] = str(tmp_path / "ws")
    yield


def _nifti_bytes(data, affine=None):
    import tempfile
    from pathlib import Path

    import nibabel as nib
    import numpy as np
    aff = affine if affine is not None else np.diag([1.0, 1.0, 2.0, 1.0])
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v.nii.gz"
        nib.save(nib.Nifti1Image(data, aff), str(p))
        return p.read_bytes()


def _workspace() -> str:
    return client.post("/api/workspaces").json()["workspace_id"]


def _upload(wid: str, data, name="scan.nii.gz"):
    payload = _nifti_bytes(data)
    return client.post(
        "/api/ct/upload",
        data={"workspace_id": wid},
        files={"file": (name, payload, "application/gzip")},
    )


def test_upload_valid_ct_and_meta():
    wid = _workspace()
    data = (np.random.default_rng(1).random((40, 40, 20)) * 800 - 400).astype(np.int16)
    r = _upload(wid, data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shape"] == [40, 40, 20]
    assert body["window_width"] > 0
    ct_id = body["id"]
    assert client.get(f"/api/ct/{ct_id}/meta").json()["orientation"] == body["orientation"]


def test_upload_4d_rejected():
    wid = _workspace()
    data = np.zeros((16, 16, 16, 4), dtype=np.int16)
    r = _upload(wid, data)
    assert r.status_code == 422


def test_volume_and_slice_endpoints():
    wid = _workspace()
    data = np.arange(48 * 48 * 24, dtype=np.int16).reshape(48, 48, 24)
    ct_id = _upload(wid, data).json()["id"]

    vr = client.get(f"/api/ct/{ct_id}/volume", params={"max_side": 32})
    assert vr.status_code == 200
    dims = [int(x) for x in vr.headers["X-Dims"].split(",")]
    assert max(dims) <= 32
    assert len(vr.content) == np.prod(dims) * 2  # int16

    sr = client.get(f"/api/ct/{ct_id}/slice/axial/0")
    assert sr.status_code == 200
    shape = [int(x) for x in sr.headers["X-Shape"].split(",")]
    assert len(sr.content) == np.prod(shape) * 4  # float32


def test_annotation_persistence_roundtrip():
    wid = _workspace()
    data = np.zeros((32, 32, 16), dtype=np.int16)
    ct_id = _upload(wid, data).json()["id"]

    ann = {"plane": "axial", "slice_index": 3,
           "points": [[1, 1], [10, 1], [10, 10], [1, 10]], "label": "nodule"}
    created = client.post(f"/api/ct/{ct_id}/annotations", json=ann)
    assert created.status_code == 200
    aid = created.json()["id"]

    listed = client.get(f"/api/ct/{ct_id}/annotations").json()
    assert [a["id"] for a in listed] == [aid]
    assert listed[0]["points"] == ann["points"]
    assert listed[0]["label"] == "nodule"

    assert client.delete(f"/api/ct/annotations/{aid}").status_code == 200
    assert client.get(f"/api/ct/{ct_id}/annotations").json() == []


def test_annotation_rejects_degenerate_polygon():
    wid = _workspace()
    ct_id = _upload(wid, np.zeros((16, 16, 16), dtype=np.int16)).json()["id"]
    r = client.post(f"/api/ct/{ct_id}/annotations",
                    json={"plane": "axial", "slice_index": 0, "points": [[0, 0], [1, 1]]})
    assert r.status_code == 422  # < 3 points
