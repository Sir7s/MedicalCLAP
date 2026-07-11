# Phase Execution Plan — P8 · NIfTI Ingestion & 3D CT Viewer

**Source:** Master Plan §P8 (p.17, HIGH RISK); Architecture SPEC-01 §2.1–2.2
(single chest CT, 3 orthogonal views, WW/WL, polygon annotation, basic volume
rendering). **Prerequisite:** P7 merged (`45b6881`) ✅. **Branch:** `phase/P8-viewer`.
**Merge:** auto-merge on green CI (resumed from P8).

## Objective
Upload one chest CT (NIfTI), validate it, view three orthogonal planes with
slice scrolling + WW/WL, draw + persist polygon annotations, and basic 3D volume
rendering — a professional viewer page.

## Scope boundary (H-01)
✅ NIfTI validation/ingestion API, orientation/affine handling, slice + volume
data endpoints, annotation table + API, vtk.js viewer (3 planes, WW/WL, polygon,
volume render), test fixtures. ❌ No retrieval/model wiring (P13), no preprocessing
point-sampling (P9), no history full-archive of CT (P15 extends P5).

## Subphases
| # | Subphase | Critical tests |
|---|---|---|
| S1 | NIfTI validation + ingestion API (structure/dims/affine/size) | valid 3D accepted; invalid (4D / corrupt header / NaN·Inf) rejected |
| S2 | Orientation/affine metadata + slice + downsampled-volume endpoints | affine/orientation correctness; slice bounds |
| S3 | Annotation model + migration + save/load API | annotation persistence round-trip |
| S4 | vtk.js viewer page: 3 orthogonal views + slice scroll + WW/WL | frontend builds; contract types |
| S5 | Polygon annotation UI + save; basic volume rendering | build; annotation wired to API |
| S6 | CI + reports + PR (auto-merge on green) | full suite green |

## Key designs
- **Ingestion** (`backend/app/viewer/`): parse with nibabel; validate 3D (reject
  4D+), finite voxels (reject NaN/Inf header-declared or sampled), reasonable
  dims/size; store the uploaded `.nii.gz` under the workspace volume tree
  (P5 paths, git-ignored), record a `ct_volumes` row (dims, spacing, affine,
  default WW/WL from HU percentiles). Upload capped (single CT, size limit).
- **Data endpoints**: `/api/ct/{id}/meta`, `/api/ct/{id}/slice/{plane}/{index}`
  (PNG, windowed) as a robust 2D path; `/api/ct/{id}/volume` (downsampled raw
  for vtk.js volume rendering). Server-side slicing keeps the viewer correct even
  before WebGL, and gives deterministic tests.
- **Annotations**: `ct_annotations` (workspace_id, ct_id, plane, slice_index,
  polygon points JSON, label); save/list/delete API; persisted with the case.
- **Frontend**: `Viewer.tsx` using vtk.js — 3 image views + volume view, slice
  sliders, WW/WL sliders, polygon draw tool posting to the annotation API.
- **Fixtures**: synthetic NIfTIs (valid 3D chest-like, 4D, corrupt header,
  NaN/Inf) generated in tests via nibabel (never committed — `.nii.gz` ignored).

## Verification note
Backend ingestion/validation/annotation are fully unit/integration tested. The
vtk.js **rendering quality** (WebGL) can't be asserted headlessly; CI proves the
frontend compiles + builds, and I will launch the app + screenshot the viewer
for a visual check. Any rendering polish the user wants is feedback on the PR.
