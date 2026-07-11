# Phase Execution Plan — P7 · CT-RATE Acquisition & Governance

**Source:** Master Plan §P7 (p.16, HIGH RISK); Architecture SPEC-06 (dataset
governance, canonical hash, provenance/license, patient-level split), SPEC-07
§8.1 (Chest-CT scope). **Prerequisite:** P6 merged (`a3f91eb`) ✅ + HF access
**confirmed** (user `Sir7s`, CT-RATE gated access granted). **Branch:** `phase/P7-ctrate`.

## The resource reality (drives the mandatory three-option decision)
- **CT-RATE total = 21.3 TB** (250,931 CT volumes) — measured live via HF metadata.
- **Free disk (D:) = 231 GB.** Full download is impossible and not required
  (Architecture: "local small subset first; full training on Google Colab Free").
- Per Master Plan §9.2, on a disk/bandwidth shortfall I must present **three
  options and may not auto-downgrade** — see §Decision below.

## What P7 downloads regardless of scale (tiny, essential — ~110 MB)
| File | Size | Use |
|---|---|---|
| `radiology_text_reports/{train,validation}_reports.csv` | 85 MB | report text (the text side of retrieval) |
| `metadata/{train,validation}_metadata.csv` | 16 MB | spacing/orientation (preprocessing) |
| `multi_abnormality_labels/{train,valid}_predicted_labels.csv` | 3 MB | abnormality multi-labels (auxiliary classification loss) |
| `metadata/no_chest_*.txt`, `Metadata_Attributes.xlsx` | <1 MB | exclusions / schema |

**Excluded by design:** `ts_seg/` (244 GB segmentation masks — different task);
all `models/` + `models_deprecated/` (CT-CHAT LLMs, CT-CLIP weights) — H-rule
forbids loading CT-CLIP image weights into PointNet++, and they're 100s of GB.
CT volumes use the **`_fixed`** variants (the dataset's own metadata-corrected set).

## Subphases
| # | Subphase | Output |
|---|---|---|
| S1 | Confirm license/provenance; write Provenance + License record | `data/ct_rate/PROVENANCE.json` (git-ignored data; manifest tracked) |
| S2 | Disk + bandwidth precheck; storage reservation (reuses P5) | precheck report |
| S3 | Download metadata/reports/labels (full) + the chosen CT subset | `data/ct_rate/…` (git-ignored) |
| S4 | Canonical Dataset Manifest + Root Hash (SPEC-06 §7.3 form) | `data/ct_rate/MANIFEST.json` + committed `docs/reports/P7_DATASET_MANIFEST.md` (hashes only) |
| S5 | Patient-level train/val/test split (no leakage) + smoke subset | `split_revision.json` |
| S6 | Governance tests + Dataset Release row (reuses control plane) + reports + PR | tests, exit report |

## Critical tests (SPEC-06 / Master Plan P7 gate)
- **Canonical hash stability** across path/Unicode/sort (FR-DATA-001 subset).
- **Patient-level split has zero leakage** (no patient in >1 split).
- Random-file readability (valid NIfTI headers).
- **PHI / no-restricted-data guard**: dataset lives only under git-ignored
  `data/`; the repo tracks *manifests/hashes only*, never volumes or report text
  (H-13/H-14; `test_repo_structure` already enforces `*.nii.gz` etc.).

## Governance
- `data/` is git-ignored (already). Reports contain de-identified clinical text;
  still never committed. Only hashes/counts/manifests (no content) are tracked.
- A `dataset_releases`-style provenance record captures source org, URL, license,
  `redistribution_allowed=false`, de-identification status, and the root hash.

## ⚠️ Decision required before any bulk download (Master Plan §9.2)
Downloading hundreds of GB commits your disk + bandwidth, so pick the CT-volume
scale. Metadata/reports/labels (~110 MB) are downloaded in **all** options.

| Option | Local CT volumes | Disk | Local baseline quality | Notes |
|---|---|---|---|---|
| **A — Smoke + Colab (recommended)** | ~60 vols smoke (~10 GB) | ~10–15 GB | pipeline dev only; real training on Colab/Kaggle | Matches the architecture's stated strategy; leaves ~215 GB free; fastest |
| **B — Local subset** | ~800 vols (~130 GB) | ~130 GB | a genuine (modest) local retrieval baseline | ~100 GB headroom; hours of download |
| **C — Max local** | ~1,200 vols (~200 GB) | ~200 GB | strongest local dataset within budget | only ~30 GB headroom (tight w/ Docker) — not recommended |

All options: patient-level stratified selection, full reports/labels, canonical
manifest + hash, no-leakage split. I will **not** start bulk download until you
choose. Timeline depends on your bandwidth (unmeasured — I'll report throughput
after the ~110 MB metadata pull).
