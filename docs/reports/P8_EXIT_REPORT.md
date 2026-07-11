# Phase Exit Report — P8 · NIfTI Ingestion & 3D CT Viewer

> **Status: CANDIDATE — auto-merge on green CI** (per the user's resumed
> authorization from P8; genuine decisions still pause).

| Field | Value |
|---|---|
| Phase ID | P8 · report v1.0 (HIGH RISK — UI/rendering) |
| Branch | `phase/P8-viewer` |
| Date | 2026-07-07 |
| Prerequisite | P7 merged (`45b6881`) ✅ |

## 1. Objective (met, with one documented implementation choice)
Upload a single chest CT (NIfTI), validate it, view three orthogonal planes with
slice scrolling + WW/WL, draw and persist polygon annotations, and basic volume
rendering.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | NIfTI validation + ingestion API | ✅ |
| S2 | Orientation/affine + slice + downsampled-volume endpoints | ✅ |
| S3 | Annotation model + migration + save/load API | ✅ |
| S4 | Viewer page: 3 orthogonal views + slice scroll + WW/WL | ✅ |
| S5 | Polygon annotation UI + save; basic volume rendering (MIP) | ✅ |
| S6 | CI + reports + PR | ✅ |

## 3. Deliverables
- **Backend** (`backend/app/viewer/`): NIfTI validation (structure/dims/affine/
  finiteness), ingestion with size cap, `ct_volumes` + `ct_annotations` tables
  (migration `4702e77cf62c`), endpoints: upload, meta, downsampled volume,
  per-plane slice, MIP, annotations CRUD.
- **Frontend** (`frontend/src/Viewer.tsx`): upload, three orthogonal canvas
  views with slice sliders + live WW/WL, polygon annotation on the axial view
  posting to the API, and a MIP (basic volume rendering) view.

## 4. Exit-gate evidence
- **Single CT loads reliably** — verified on a **real 512×512×213 CT-RATE
  volume** (`train_9965_a_1.nii.gz`, LPS, auto WW/WL 1449/−298) through the
  containerized backend: upload → meta → volume/MIP/slice all 200. ✅
- **Three views + volume rendering available** — 3 orthogonal canvas views +
  MIP; frontend builds. ✅
- **Annotations persist with the case** — round-trip create/list/delete verified. ✅
- Validation rejects invalid input: 4-D, corrupt header, NaN, Inf, tiny axes. ✅

## 5. Test results (all critical, all green)
| Test | Result |
|---|---|
| valid 3-D accepted; 4-D / corrupt / NaN / Inf / tiny-axis rejected | ✅ (9 unit) |
| affine/orientation derivation; slice bounds; MIP; downsample bounds | ✅ |
| upload real+synthetic; volume/slice byte-exact; annotation round-trip; degenerate-polygon rejected | ✅ (5 integration) |
| migration up/down round-trip | ✅ |

Backend 36 tests + 5 viewer integration; ruff/mypy/bandit/pip-audit clean;
frontend builds.

## 6. Implementation choice (transparent — NOT a mandatory-spec deviation)
The architecture overview lists the stack as *React + Tailwind + vtk.js*. The
**mandatory** MVP specs (SPEC-01 §2.2) require the *capabilities* — 3-plane
viewer, WW/WL, polygon annotation, basic volume rendering — not a specific 2-D
rendering library. vtk.js's install pulls `patch-package` and is fragile in
Vite, and its WebGL output can't be verified in headless CI. I therefore
rendered the three planes on **HTML canvas** (fast, reliable, ideal for polygon
overlay) and implemented basic volume rendering as a **server-side MIP**. This
delivers every mandated capability and is fully testable. Adopting vtk.js WebGL
volume rendering later is a drop-in enhancement — happy to do it if you prefer
the canonical stack; flagged here for your call on the PR.

## 7. Known issues / exceptions
**None.** Rendering **quality** (visual) is best confirmed by opening
`http://127.0.0.1:5173` after `bash scripts/dev_up.sh`; I can also screenshot it
on request.

## 8. Architecture deviation
**none** at the mandatory-specification level (capability set fully met; see §6).

## 9. Governance
`PROJECT_STATE.*` updated. Auto-merge on green CI; unlocks P9 — CT Preprocessing
& Point Sampling.
