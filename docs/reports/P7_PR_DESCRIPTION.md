# Phase P7 — CT-RATE Acquisition & Governance (HIGH RISK)

Acquire, verify, register, and split a governed CT-RATE subset as a reproducible
data release. No preprocessing/model code (P9+/P11+). **No restricted data,
report text, or weights are committed** — only hashes/counts (H-13/H-14).

## Resource decision (Master Plan §9.2)
CT-RATE is 21.3 TB / 250,931 volumes vs 231 GB free. Three options were
presented; user chose **Option B (~130 GB patient-level subset)**.

## Deliverables
- Provenance/license record (`redistribution_allowed=false`, de-identified).
- Full companion data (reports, multi-abnormality labels, metadata; ~110 MB, local).
- 801 `train_fixed` volumes (130.9 GB), resumable retry-hardened downloader.
- Canonical manifest + **root SHA-256 `b577dd13…528e3208`** (SPEC-06 §7.3).
- Patient-level split (seed 42): train 556 / val 127 / test 118 vols across
  242 / 52 / 53 patients — **zero leakage**, deterministic.

## Test summary (all critical, all passed)
canonical-hash stability (FR-DATA-001) · content/order sensitivity · patient-level
no-leakage · split determinism · volume↔report coverage · manifest-matches-disk ·
provenance-forbids-redistribution. **8 governance tests pass**;
ruff/mypy/bandit/pip-audit clean.

Full evidence: `docs/reports/P7_EXIT_REPORT.md` ·
manifest summary: `docs/reports/P7_DATASET_MANIFEST.md` ·
conformance: `docs/reports/P7_CONFORMANCE_REPORT.md`.

## Change log
- `ml/datasets/ct_rate/`: `select.py`, `acquire.py`, `manifest.py`, `provenance.py`.
- `tests/data/test_ct_rate_governance.py` (8 tests).
- CI: mypy scope extended to `ml/`.
- Committed reports (hashes/counts only). Dataset lives under git-ignored `data/`.

## Approval
Requires user approval to merge (pause-each-phase). Merging approves the CT-RATE
data release and unlocks P8 — NIfTI Ingestion & 3D CT Viewer.
