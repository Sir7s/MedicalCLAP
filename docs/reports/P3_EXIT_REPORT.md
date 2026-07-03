# Phase Exit Report — P3 · Command & Event Outbox

> **Status: CANDIDATE.** Authoritative once approved and merged (H-15).

| Field | Value |
|---|---|
| Phase ID | P3 · report v1.0 |
| Architecture bundle | v2.4.5 |
| Branch | `phase/P3-outbox` |
| Date | 2026-07-03 |
| Prerequisite | P2 merged (`84dcef9`) ✅ |

## 1. Objective (met)
Reliable delivery from the DB to the execution queue and event stream, with
crash recovery, dedup, and a dead-letter protocol — committed commands are never
lost and duplicate delivery never causes a second business effect.

## 2. Subphase completion
| # | Subphase | Status | Evidence |
|---|---|---|---|
| S1 | Command Dispatcher (send-before-mark + recovery) | ✅ | `backend/app/queue/dispatcher.py` |
| S2 | Event Outbox Publisher | ✅ | `backend/app/queue/publisher.py` |
| S3 | Dead-letter protocol (IMP-EXEC-001/002) | ✅ | `backend/app/queue/deadletter.py` |
| S4 | Redis Stream consumer group (dedup, claim) | ✅ | `backend/app/queue/consumer.py` |
| S5 | Failpoints + crash/recovery tests | ✅ | `backend/app/failpoints.py`, `tests/infra/test_outbox.py` |
| S6 | CI (compose lane already runs outbox tests) + reports | ✅ | `.github/workflows/ci.yml` |

## 3. Deliverables
- Redis Streams wiring (`exec:commands`, `events:stream`, `supervisors` group).
- Command Dispatcher with per-command two-phase send (durable dispatching → XADD
  → durable dispatched) and a recovery scan.
- Event Publisher (ordered by sequence, idempotent mark).
- Dead-letter protocol with audit; never auto-replayed.
- Mock supervisor consumer: validate + generation handling + dedup + ACK; pending
  claim via XAUTOCLAIM.
- Failpoint framework (env-gated, one-shot).

## 4. Test results (all green)
| Test | Freeze ref | Class | Result |
|---|---|---|---|
| commit crash → not lost | FR-EXEC-001 | **Critical** — recovery | ✅ |
| send-before-mark → one effect | FR-EXEC-002 | **Critical** — recovery | ✅ |
| duplicate message deduped | FR-EXEC-005 | **Critical** — data integrity | ✅ |
| dead-letter missing command | FR-EXEC-011 | **Critical** — recovery | ✅ |
| dead-letter unparseable payload | — | **Critical** — recovery | ✅ |
| pending claim reprocess | — | **Critical** — recovery | ✅ |
| scanner recovers pending | — | **Critical** — recovery | ✅ |
| publisher publishes events | — | Core | ✅ |

Counts: 44 governance + 13 backend + 25 integration = **82 pass, 0 fail** locally.
Bandit 0 issues; pip-audit 0 vulns. ruff/mypy clean.

## 5. Clause conformance
See [`P3_CONFORMANCE_REPORT.md`](P3_CONFORMANCE_REPORT.md). In-scope coverage 100%.
Documented note: consumer processing is a **mock** in P3; lease/fencing/GPU worker
land in P4.

## 6. Known issues / test exceptions
**None.**

## 7. Architecture deviation
**none.**

## 8. State & governance
- `PROJECT_STATE.*` updated (P3 in review).
- Approval: ⬜ pending. Merge: ⬜ open after push.
- Next gate (P4): P3 approved + merged → Supervisor, Lease, Fencing & Mock Worker.

## 9. Commit / PR
[`P3_COMMIT_MESSAGE.txt`](P3_COMMIT_MESSAGE.txt) · [`P3_PR_DESCRIPTION.md`](P3_PR_DESCRIPTION.md).
