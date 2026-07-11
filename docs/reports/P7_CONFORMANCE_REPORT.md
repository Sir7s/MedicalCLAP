# Implementation Conformance Report — P7 (CT-RATE Acquisition & Governance)

Per Implementation Appendix v1.1 **IMP-GOV-001/002**; Architecture SPEC-06.

## Scope
P7 acquires a governed CT-RATE subset (reports + labels + metadata in full, a
patient-level ~130 GB `train_fixed` CT subset) and establishes provenance,
a canonical manifest + root hash, and a leakage-free split. No preprocessing or
model code (P9+/P11+).

## Clause / spec mapping
| Spec / clause | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-06 §7.2 | Provenance + license; training/redistribution/commercial flags; de-id status | implemented | `ml/datasets/ct_rate/provenance.py` → `data/ct_rate/PROVENANCE.json`; `test_provenance_forbids_redistribution` |
| SPEC-06 §7.3 | Canonical dataset hash: `NFC(path)+NUL+size+NUL+lower_sha256+LF`, sorted by utf8(path) | implemented | `ml/datasets/ct_rate/manifest.py`; FR-DATA-001 stability tests |
| SPEC-06 §7.1 | Dataset lifecycle / release identity (root hash = release id) | implemented (release manifest) | `data/ct_rate/MANIFEST.json` (root_sha256) |
| Master Plan P7 | Patient-level train/val/test split, no leakage | implemented | `ml/datasets/ct_rate/select.py`; `test_split_has_no_patient_leakage` |
| Master Plan P7 | Random-file readability / manifest matches disk | implemented | `test_manifest_matches_disk` |
| SPEC-07 §8.1 | Chest-CT scope only | honored | reports/labels/metadata + `train_fixed` volumes only; `ts_seg` + model weights excluded |
| H-13 / H-14 | No restricted data / weights / PHI committed | enforced | dataset only under git-ignored `data/`; repo tracks manifests/hashes only; `test_repo_structure` blocks `*.nii.gz` etc. |
| CT-CLIP policy | Never load CT-CLIP image weights into PointNet++ | honored | `models/`, `models_deprecated/` (CT-CLIP/CT-CHAT) excluded from download |

## Governance decisions recorded
- **Resource shortfall handled per Master Plan §9.2**: CT-RATE is 21.3 TB vs
  231 GB free; three options were presented and the **user chose Option B**
  (~800 patient-level volumes / ~130 GB). Not an AI auto-downgrade.
- **Reproducible selection**: seeded (`seed=42`), deterministic; re-running
  `build_split` reproduces the exact volume set (`test_split_is_deterministic`).

## Not applicable to P7 (later phases)
- FR-DATA-002 published-dataset mutation guard, Qdrant content digest → P13.
- Preprocessing manifest / point sampling → P9.
- Full-scale training data (Colab/Kaggle) → P12.

## Summary
In-scope mandatory coverage 100%; deviations 0. Final `root_sha256`, file count,
and byte total are recorded in the Exit Report once the download + manifest
complete.
