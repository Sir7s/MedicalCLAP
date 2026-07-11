# Phase P9 — CT Preprocessing & Point Sampling

Deterministically convert a CT volume into 32,768 (x,y,z,density) points for
PointNet++: reorient (RAS) → isotropic resample → HU normalize → body mask →
gradient sampling (50% body / 25% high-gradient / 25% global), with a full
reproducibility manifest. Compute-only; no CT/PHI committed.

## Exit-gate evidence
- Same input → **bit-identical** point cloud (synthetic + real CT-RATE volume
  512×512×213 → 175×175×160 @2mm → 32,768 pts; manifest hash reproduces).
- No NaN/Inf; coords in [-1,1], density in [0,1]; exact 50/25/25 sampling.
- Complete manifest (input hash, config, seed, geometry, output hash, lib versions).

## Test summary (all critical, all passed)
8 ml tests: determinism, exact count + finite, coordinate/density ranges,
sampling ratios, seed sensitivity, resample-to-target-spacing, spacing geometry,
manifest completeness + hash reproducibility. ruff/mypy clean; real-CT verified.

## Change log
- `ml/preprocessing/` (config, ct_pointcloud + CLI + npz cache, manifest).
- `ml/requirements.txt` (numpy/scipy/nibabel).
- CI: new **ml lane** + ml dependency audit; governance ignores tests/ml.
- Tests: `tests/ml/test_preprocessing.py`.

## Approval
Auto-merge on green CI. Unlocks P10 — Text Pipeline & Bilingual Input.
