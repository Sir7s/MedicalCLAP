# Phase P4 — Supervisor, Lease, Fencing & Mock Worker

The unique Lease Owner: atomic lease acquisition + fencing, a two-phase GPU
startup handshake against a real spawned mock worker, recovery scanner with
isolated retry budgets, stage watchdog, and forced cancel. No real model code
(H-01; models arrive P11+).

## Subphases completed
- [x] S1 — Supervisor consumer: atomic lease + command binding → commit → ACK
- [x] S2 — Lease/fencing/heartbeat + recovery scanner + budgets migration
- [x] S3 — Startup nonce + IPC protocol (replay-proof)
- [x] S4 — Mock GPU worker + two-phase handshake (persist-before-begin)
- [x] S5 — Stage watchdog + forced-cancel ladder
- [x] S6 — CI + reports

## Exit-gate evidence
| Gate (Master Plan P4) | Evidence |
|---|---|
| Old lease cannot commit | FR-EXEC-006 test: stale owner write + result commit rejected |
| Crash after ACK recoverable | scanner takeover: same-generation republish, revision+1 lease |
| Mock worker full flow completes | spawn → handshake → 4 stages → completed/succeeded/resolved |

## Test summary (all critical, all passed)
FR-EXEC-003 lease-before-ACK crash → single lease · FR-EXEC-006 fencing ·
FR-EXEC-007 budget isolation · FR-EXEC-008 startup gating + full flow ·
FR-EXEC-009 watchdog (unit) · FR-EXEC-010 forced cancel, result refused ·
FR-EXEC-012 nonce replay (unit) · FR-EXEC-013 persist-before-begin ·
migration verified against non-empty tables.

**103 tests pass** (44 governance + 26 backend + 33 integration).
ruff/mypy/bandit/pip-audit clean. Full evidence:
[`docs/reports/P4_EXIT_REPORT.md`](docs/reports/P4_EXIT_REPORT.md).

## Change log
- `backend/app/supervisor/`: `lease.py`, `scanner.py`, `ipc.py`, `worker.py`,
  `handshake.py`, `watchdog.py`, `consumer.py`.
- `backend/app/db/models.py` + migration `a690573bf986`: recovery-window fields,
  distinct retry budgets, worker binding (pid / child UUID / nonce hash).
- Tests: `backend/tests/test_ipc_watchdog.py` (11), `tests/infra/test_supervisor.py` (8).

## Conformance & deviations
- [`docs/reports/P4_CONFORMANCE_REPORT.md`](docs/reports/P4_CONFORMANCE_REPORT.md)
  — IMP-EXEC-003..013 in-scope coverage 100%; deviations 0.
- Architecture deviation: **none**.

## Checklist
- [x] No restricted data/weights/secrets/PHI committed
- [x] `PROJECT_STATE.{md,json}` updated & consistent
- [x] Phase Exit Report attached; no Known Issues needed
- [x] Local CI mirror green

## Approval
User granted advance approval (2026-07-07) for merge + P5 entry conditional on
green CI.
