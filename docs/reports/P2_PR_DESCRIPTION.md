# Phase P2 — Persistent Database Control Plane

Core control-plane persistence on PostgreSQL with an all-or-nothing task
creation transaction. No future-phase functionality (H-01).

## Subphases completed
- [x] S1 — SQLAlchemy + Alembic wired to settings DSN (migration up/down verified)
- [x] S2 — 9 core tables, CHECK-constrained states, `ON DELETE RESTRICT` FKs
- [x] S3 — state machines + `assert_transition`
- [x] S4 — repository layer (guarded transitions, sequence allocation)
- [x] S5 — atomic `create_task` + idempotency (sequential + concurrent)
- [x] S6 — CI migrates DB and runs control-plane integration tests

## Test summary (critical unless noted)
| Test | Result |
|---|---|
| migration up→down→up | passed |
| atomic create success | passed |
| atomic create rollback (no partial commit) | passed |
| idempotency: sequential + 8-way concurrent → 1 task | passed |
| DB rejects illegal state (CHECK) | passed |
| FK ON DELETE RESTRICT | passed |
| state-machine legality (unit) | passed |
| ruff / mypy / bandit / pip-audit | passed / 0 issues |

**74 tests pass** (44 governance + 13 backend + 17 integration). Full evidence:
[`docs/reports/P2_EXIT_REPORT.md`](docs/reports/P2_EXIT_REPORT.md).

## Change log
- `backend/app/db/`: `base.py`, `models.py` (9 tables), `states.py`, `repository.py`, `service.py`.
- `backend/alembic/` + `alembic.ini`: migration framework + initial migration `2d80d962a004`.
- `backend/requirements.txt`: + sqlalchemy 2.0.49, alembic 1.18.5.
- Tests: `backend/tests/test_states.py`, `tests/infra/test_control_plane.py` (+ conftest path shim).
- CI: compose lane installs backend deps, runs `alembic upgrade head`, then integration tests.

## Conformance & deviations
- [`docs/reports/P2_CONFORMANCE_REPORT.md`](docs/reports/P2_CONFORMANCE_REPORT.md) — in-scope coverage 100%.
- Documented seam: deployment-reference binding in the creation transaction deferred to **P13**.
- Architecture deviation: **none**.

## Checklist
- [x] No restricted data/weights/secrets/PHI committed (git-tracked scan)
- [x] `PROJECT_STATE.{md,json}` updated & consistent
- [x] Phase Exit Report attached; no Known Issues needed
- [x] `bash scripts/ci_local.sh` green locally

## Reviewer action
Approve to make the P2 Exit Report authoritative and unblock **P3 — Command &
Event Outbox**. Do not merge before explicit approval.
