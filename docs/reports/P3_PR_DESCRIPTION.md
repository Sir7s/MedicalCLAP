# Phase P3 — Command & Event Outbox

Reliable delivery from the DB to the execution queue and event stream over Redis
Streams, with crash recovery, dedup, and a dead-letter protocol. No future-phase
functionality (H-01).

## Subphases completed
- [x] S1 — Command Dispatcher (send-before-mark + recovery scan)
- [x] S2 — Event Outbox Publisher (ordered, idempotent)
- [x] S3 — Dead-letter protocol (IMP-EXEC-001/002)
- [x] S4 — Redis Stream consumer group (generation handling, dedup, XAUTOCLAIM)
- [x] S5 — Failpoint framework + crash/recovery tests
- [x] S6 — CI (compose lane runs outbox tests) + reports

## Test summary (critical unless noted)
| Test | Freeze ref | Result |
|---|---|---|
| commit crash → not lost | FR-EXEC-001 | passed |
| send-before-mark → one effect | FR-EXEC-002 | passed |
| duplicate message deduped | FR-EXEC-005 | passed |
| dead-letter missing command | FR-EXEC-011 | passed |
| dead-letter unparseable payload | — | passed |
| pending claim reprocess | — | passed |
| scanner recovers pending | — | passed |
| publisher publishes events | — | passed |
| ruff / mypy / bandit / pip-audit | — | passed / 0 issues |

**82 tests pass** (44 governance + 13 backend + 25 integration). Full evidence:
[`docs/reports/P3_EXIT_REPORT.md`](docs/reports/P3_EXIT_REPORT.md).

## Change log
- `backend/app/queue/`: `redis_client.py`, `dispatcher.py`, `publisher.py`, `deadletter.py`, `consumer.py`.
- `backend/app/failpoints.py`: env-gated one-shot crash injection.
- Tests: `tests/infra/test_outbox.py` (8 crash/recovery/dedup/dead-letter tests).

## Conformance & deviations
- [`docs/reports/P3_CONFORMANCE_REPORT.md`](docs/reports/P3_CONFORMANCE_REPORT.md) — in-scope coverage 100%.
- Documented note: consumer processing is a **mock** in P3; lease/fencing/GPU worker land in **P4**.
- Architecture deviation: **none**.

## Checklist
- [x] No restricted data/weights/secrets/PHI committed (git-tracked scan)
- [x] `PROJECT_STATE.{md,json}` updated & consistent
- [x] Phase Exit Report attached; no Known Issues needed
- [x] `bash scripts/ci_local.sh` green locally

## Reviewer action
Approve to make the P3 Exit Report authoritative and unblock **P4 — Supervisor,
Lease, Fencing & Mock Worker**. Do not merge before explicit approval.
