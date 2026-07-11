# Phase Exit Report — P7 · CT-RATE Acquisition & Governance

> **Status: CANDIDATE — awaiting user approval + merge** (per the user's
> pause-each-phase decision for data/model phases).

| Field | Value |
|---|---|
| Phase ID | P7 · report v1.0 (HIGH RISK) |
| Branch | `phase/P7-ctrate` |
| Date | 2026-07-07 |
| Prerequisite | P6 merged (`a3f91eb`) ✅ + HF gated access confirmed ✅ |

## 1. Objective (met)
Acquire, verify, register, and split a governed CT-RATE subset as a reproducible
data release — the primary retrieval dataset — without exceeding the local disk
budget or committing any restricted data.

## 2. The resource decision (Master Plan §9.2)
CT-RATE measured at **21.3 TB / 250,931 volumes** vs **231 GB free**. Three
options were presented; the **user chose Option B (~130 GB patient-level
subset)**. No AI auto-downgrade. Recorded in the conformance report.

## 3. Deliverables
- **Provenance/license record** (`data/ct_rate/PROVENANCE.json`): source, terms,
  `redistribution_allowed=false`, de-id status, scope, exclusions.
- **Companion data (full, ~110 MB):** radiology reports, multi-abnormality
  labels, acquisition metadata.
- **CT subset:** 801 `train_fixed` volumes, 130.9 GB, resumable/retry-hardened
  downloader (`ml/datasets/ct_rate/acquire.py`).
- **Canonical Dataset Manifest + Root Hash** (SPEC-06 §7.3):
  `root_sha256 = b577dd1354e1baf84f4a02c66e1c8a9da552bc39bad2e19bceb49367528e3208`
  (801 files). Committed summary: `docs/reports/P7_DATASET_MANIFEST.md`.
- **Patient-level split** (seed 42): train 556 / val 127 / test 118 volumes
  across 242 / 52 / 53 patients — **zero leakage**, deterministic.

## 4. Exit-gate evidence (Master Plan P7 gates)
- **Source & license clear** — provenance record; access accepted on HF. ✅
- **Split has no patient leakage** — verified (`test_split_has_no_patient_leakage`). ✅
- **Manageable within budget** — 130.9 GB of 231 GB free; ~90 GB headroom. ✅
- **Hash / readability** — canonical root hash computed over all 801 files;
  manifest matches disk (`test_manifest_matches_disk`); every selected volume has
  a report (`test_every_selected_volume_has_a_report`). ✅
- **No restricted data committed** — all volumes/report text under git-ignored
  `data/`; repo tracks only hashes/counts (`test_repo_structure`, gitleaks). ✅

## 5. Test results (all critical, all green)
| Test | Freeze/spec ref | Result |
|---|---|---|
| canonical root-hash stability (path-sep + Unicode) | FR-DATA-001 | ✅ |
| hash changes on content change / order-independent | SPEC-06 §7.3 | ✅ |
| patient-level split — zero leakage | Master Plan P7 | ✅ |
| split determinism (seed reproduces set) | reproducibility | ✅ |
| every selected volume has a report | data integrity | ✅ |
| manifest matches disk + root hash recompute | Master Plan P7 | ✅ |
| provenance forbids redistribution | SPEC-06 §7.2 / H-13 | ✅ |

8 governance tests pass; ruff/mypy/bandit/pip-audit clean.

## 6. Conformance
[`P7_CONFORMANCE_REPORT.md`](P7_CONFORMANCE_REPORT.md) — in-scope coverage 100%,
0 deviations.

## 7. Known issues / exceptions
**None.** (Download surfaced two downloader bugs — Xet instability and a bad
import in the retry path — both **fixed**; final download 801/801, 0 failures.)

## 8. Governance
`PROJECT_STATE.*` updated with the dataset root hash. **User approval + merge
required** to make CT-RATE the approved data release and unlock P8.
