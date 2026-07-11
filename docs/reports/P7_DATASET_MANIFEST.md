# CT-RATE Dataset Release Manifest (P7)

> Committed summary — **hashes, counts, and parameters only**. No CT volumes and
> no report text are ever committed (H-13/H-14); those live solely under the
> git-ignored `data/ct_rate/` tree. The full per-file manifest is
> `data/ct_rate/MANIFEST.json` (local only).

## Release identity
| Field | Value |
|---|---|
| Dataset | CT-RATE (chest CT ↔ radiology reports) |
| Source variant | `train_fixed` (metadata-corrected volumes) |
| **Canonical root SHA-256** | `b577dd1354e1baf84f4a02c66e1c8a9da552bc39bad2e19bceb49367528e3208` |
| Hash form (SPEC-06 §7.3) | `NFC(path) + NUL + decimal_size + NUL + lower_sha256 + LF`, sorted by utf8(path) |
| Volume files | 801 |
| Total size | 130.9 GB |

## Patient-level split (seed = 42, deterministic, zero leakage)
| Split | Volumes | Patients |
|---|---|---|
| train | 556 | 242 |
| val | 127 | 52 |
| test | 118 | 53 |
| **total** | **801** | **347** |

Selection is reproducible: `python -m ml.datasets.ct_rate.select` with the same
seed reproduces this exact volume set (verified by `test_split_is_deterministic`).

## Companion data (full, ~110 MB, local only)
Radiology text reports (train + validation), multi-abnormality labels, and
acquisition metadata for the whole CT-RATE corpus — used for report pairing,
the auxiliary multi-label classification loss, and preprocessing.

## Provenance / license (see `data/ct_rate/PROVENANCE.json`)
Source: CT-RATE authors (HuggingFace, gated — access accepted by the user).
`training_allowed=true`, `redistribution_allowed=false`,
`commercial_use_allowed=false`, de-identified by the dataset authors.

## Excluded by design
`ts_seg/` (244 GB segmentation masks — different task); all `models/` and
`models_deprecated/` (CT-CHAT LLMs, CT-CLIP weights — the architecture forbids
loading CT-CLIP image weights into PointNet++).
