# Phase P5 — Artifact, Workspace & Lightweight History

Atomic artifact finalize, lease-revision workspace layout, source/snapshot
reference lifecycles, storage reservation with atomic quota checks, and the
lightweight-history state machine with chunked artifacts + verification seal.

## Exit-gate evidence
| Gate | Evidence |
|---|---|
| Incomplete artifacts invisible | failpoint-before-rename test: only `.partial` exists; retry finalizes |
| History visible only after `ready` | crash at snapshot/seal/ready stages ⇒ absent from list API; recoverable to `failed` |
| File hash matches DB | snapshot manifest sha256 persisted + re-verified; chunk & content hashes revalidated at seal |

## Test summary (all critical, all passed)
FR-STOR-001 anti-GC · FR-STOR-003 snapshot immutability · FR-STOR-005 late
chunk · FR-STOR-006 continuity · FR-STOR-007 corruption · FR-STOR-009 crash
recovery (3 stages) · FR-STOR-012 concurrent reservation · artifact crash
consistency · migration round-trip.

**115 tests pass** (44 governance + 26 backend + 45 integration);
ruff/mypy/bandit/pip-audit clean.
Full evidence: [`docs/reports/P5_EXIT_REPORT.md`](docs/reports/P5_EXIT_REPORT.md).

## Change log
- `backend/app/storage/`: `paths.py`, `artifacts.py`, `reservation.py`.
- `backend/app/history/`: `service.py` (save flow, seal verification, recovery,
  cleanup gate), `api.py` (History API v0, mounted in `main.py`).
- `backend/app/db/`: 8 new tables + history/artifact state machines; migration
  `6bf5810a8f42`; `repository.transition` handles non-`state` columns.
- Tests: `tests/infra/test_history.py` (12).

## Conformance & deviations
IMP-HIST-001..004, IMP-STOR-001..003 implemented with test evidence.
Scope notes: full-archive/re-executable profiles → P15; multi-fs guard → P18.
Architecture deviation: **none**.

## Approval
Merge pre-authorized by user (2026-07-07) conditional on green CI.
