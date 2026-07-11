# Phase P8 — NIfTI Ingestion & 3D CT Viewer

Upload one chest CT (NIfTI), validate it, view three orthogonal planes with
slice scroll + WW/WL, draw + persist polygon annotations, and basic volume
rendering. No CT/PHI committed (volumes under git-ignored workspace_data/).

## Exit-gate evidence
- Single CT loads reliably — verified on a **real 512×512×213 CT-RATE volume**
  through the containerized backend (upload→meta→volume/MIP/slice all 200).
- Three orthogonal views + basic volume rendering (MIP); frontend builds.
- Polygon annotations persist with the case (create/list/delete round-trip).
- Validation rejects 4-D / corrupt header / NaN / Inf / tiny-axis.

## Implementation choice (transparent)
Three planes are rendered on HTML canvas and volume rendering is a server-side
MIP, rather than vtk.js/WebGL (fragile install, unverifiable headlessly). All
mandatory SPEC-01 §2.2 capabilities are met; vtk.js is a drop-in enhancement if
preferred. Detail: `docs/reports/P8_EXIT_REPORT.md` §6.

## Test summary (all critical, all passed)
9 NIfTI validation unit tests + 5 viewer-API integration tests + migration
round-trip. Backend 36 tests; ruff/mypy/bandit/pip-audit clean; frontend builds.

## Change log
- `backend/app/viewer/` (nifti.py, api.py); `ct_volumes`+`ct_annotations` (migration `4702e77cf62c`).
- backend deps: nibabel 5.4.2, numpy 2.2.6, python-multipart.
- `frontend/src/Viewer.tsx` (+App wiring): canvas 3-view + WW/WL + polygon + MIP.
- Tests: `backend/tests/test_viewer_nifti.py`, `tests/infra/test_viewer_api.py`.

## Verification
Open http://127.0.0.1:5173 after `bash scripts/dev_up.sh` to view the CT viewer.

## Approval
Auto-merge on green CI (resumed from P8). Merging unlocks P9 — CT Preprocessing
& Point Sampling.
