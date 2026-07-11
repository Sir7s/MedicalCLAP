# Phase Exit Report — P9 · CT Preprocessing & Point Sampling

> **Status: CANDIDATE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P9 · report v1.0 |
| Branch | `phase/P9-preprocessing` |
| Date | 2026-07-07 |
| Prerequisite | P7 + P8 merged ✅ |

## 1. Objective (met)
Deterministically convert a CT-RATE volume into the PointNet++ input:
32,768 `(x, y, z, density)` points via reorient → resample → HU normalize →
body mask → gradient sampling, with a full reproducibility manifest.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Orientation (RAS) + affine + isotropic resampling | ✅ |
| S2 | HU clip + normalization to [0,1] | ✅ |
| S3 | Body mask (largest CC) + gradient magnitude | ✅ |
| S4 | Sample 32,768 pts: 50% body / 25% high-gradient / 25% global | ✅ |
| S5 | Preprocessing manifest + point-cloud cache + CLI | ✅ |
| S6 | CI (ml lane) + reports + PR | ✅ |

## 3. Deliverables
- `ml/preprocessing/`: `config.py` (reproducibility contract), `ct_pointcloud.py`
  (pipeline + CLI + `.npz` cache), `manifest.py` (SPEC-07 §8.5 manifest).
- New CI **ml lane** (numpy/scipy/nibabel) + ml dependency audit.

## 4. Exit-gate evidence (Master Plan P9)
- **Same input → same point cloud** — bit-identical across runs, on synthetic
  *and* a real CT-RATE volume (`train_9965_a_1`, 512×512×213 → 175×175×160 @2mm →
  32,768 pts); manifest `points_sha256` reproduces. ✅
- **No NaN/Inf** — asserted in the pipeline and tests. ✅
- **Manifest complete & traceable** — input hash, config, seed, geometry, output
  hash, source counts, coordinate bounds, library versions, precision. ✅

## 5. Tests (all critical, all green)
determinism · exact 32,768 count + finite · coordinate range [-1,1] + density
[0,1] · sampling ratios 50/25/25 · seed changes sampling · resample-to-target
spacing · different-spacing geometry · manifest completeness + hash
reproducibility. **8 ml tests**; ruff/mypy clean; verified on real CT.

## 6. Architecture deviation
**none** — sampling scheme, point count, coordinate/density normalization, and
manifest fields follow SPEC-07 §8.2/§8.5.

## 7. Known issues
**None.**

## 8. Governance
`PROJECT_STATE.*` updated. Auto-merge on green CI; unlocks P10 — Text Pipeline &
Bilingual Input.
