# Phase Exit Report — P5 · Artifact, Workspace & Lightweight History

> **Status: CANDIDATE.** Merge pre-authorized by user (2026-07-07) conditional
> on green CI (H-15 satisfied by that standing approval + green CI).

| Field | Value |
|---|---|
| Phase ID | P5 · report v1.0 |
| Branch | `phase/P5-artifacts` |
| Date | 2026-07-07 |
| Prerequisite | P4 merged (`5d5b188`) ✅ |

## 1. Objective (met)
Atomic artifact finalize, lease-revision workspace layout, dual reference
lifecycles, storage reservation with atomic quota checks, and the
lightweight-history state machine with chunked artifacts + verification seal.

## 2. Subphases
| # | Subphase | Status | Evidence |
|---|---|---|---|
| S1 | Volume/file paths (lease-revision dirs) | ✅ | `backend/app/storage/paths.py` |
| S2 | Atomic finalize `.partial→fsync→sha256→rename` + manifests | ✅ | `storage/artifacts.py`; crash test |
| S3 | Tables migration `6bf5810a8f42` (8 tables) + source/snapshot references (IMP-HIST-001/002) | ✅ | `db/models.py`; anti-GC + immutability tests |
| S4 | Storage reservation, atomic quota (IMP-STOR-001/002/003) | ✅ | `storage/reservation.py`; concurrency test |
| S5 | Lightweight history + chunked artifacts + seal (IMP-HIST-003/004) + History API v0 | ✅ | `history/service.py`, `history/api.py` |
| S6 | CI + reports + PR + authorized merge | ✅ | this delivery |

## 3. Exit-gate evidence (Master Plan P5 gates)
- **Incomplete artifacts invisible** — crash before rename leaves only
  `.partial`; readers see nothing; retry finalizes + verifies. ✅
- **History visible only after ready** — crash at snapshot/seal/ready stages ⇒
  record non-ready, absent from list API; recovery marks `failed`. ✅
- **File hash matches DB** — snapshot manifest sha256 persisted and re-verified;
  chunk hashes + full-content hash re-validated at seal verification. ✅

## 4. Test results (all critical, all green)
| Test | Freeze ref |
|---|---|
| artifact crash consistency (failpoint before rename) | FR-STOR-… (artifact crash) |
| finalized artifact immutability | SPEC-04 §5.2 |
| snapshot unaffected by source mutation | FR-STOR-003 |
| cleanup blocked by active reference / allowed after release | FR-STOR-001 |
| full lightweight save → ready → visible; references released | FR-STOR-008 subset |
| crash at 3 stages → invisible + recoverable | FR-STOR-009 |
| late chunk rejected after seal | FR-STOR-005 / IMP-HIST-004 |
| chunk gap fails verification → corrupted | FR-STOR-006 |
| tampered chunk detected → corrupted | FR-STOR-007 |
| concurrent reservations don't oversell | FR-STOR-012 subset |
| migration up/down round-trip | data integrity |

**115 tests pass** (44 governance + 26 backend + 45 integration); ruff/mypy/
bandit/pip-audit clean.

## 5. Conformance
IMP-HIST-001..004 and IMP-STOR-001..003 implemented with test evidence (table
above; code paths in §2). Scope notes (not deviations): full-archive/
re-executable profiles → P15; snapshot chunk streaming for large CT files → P15
(lightweight profile stores documents, per SPEC-05); FR-STOR-013
multi-filesystem guard → P18 with backup storage.

## 6. Known issues / exceptions
**None.** (Two implementation defects found by tests — transition attr on
artifacts, unflushed reference id — fixed before commit.)

## 7. Architecture deviation
**none.**

## 8. Governance
`PROJECT_STATE.*` updated; merge + P6 entry pre-authorized conditional on green CI.
