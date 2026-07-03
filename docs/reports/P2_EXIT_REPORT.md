# Phase Exit Report — P2 · Persistent Database Control Plane

> **Status: CANDIDATE.** Authoritative once approved and merged (H-15).

| Field | Value |
|---|---|
| Phase ID | P2 · report v1.0 |
| Architecture bundle | v2.4.5 |
| Branch | `phase/P2-control-plane` |
| Date | 2026-07-01 |
| Prerequisite | P1 merged (`14bcafe`) ✅ |

## 1. Objective (met)
Persistent control plane on PostgreSQL: core tables, state machines + validators,
repository layer, and an all-or-nothing transactional task creation.

## 2. Subphase completion
| # | Subphase | Status | Evidence |
|---|---|---|---|
| S1 | Alembic framework wired to settings DSN | ✅ | `backend/alembic/`, `alembic.ini`, migration up/down/up round-trip |
| S2 | 9 core tables + constraints, `ON DELETE RESTRICT` | ✅ | `backend/app/db/models.py`, migration `2d80d962a004` |
| S3 | State-machine constants + validator | ✅ | `backend/app/db/states.py`, `backend/tests/test_states.py` |
| S4 | Repository layer (guarded transitions, sequences) | ✅ | `backend/app/db/repository.py` |
| S5 | Transactional task creation + idempotency | ✅ | `backend/app/db/service.py`, `tests/infra/test_control_plane.py` |
| S6 | CI (migrate + integration) + reports | ✅ | `.github/workflows/ci.yml` compose lane |

## 3. Deliverables
- Alembic migration creating `workspace_sessions`, `application_tasks`,
  `task_attempts`, `model_jobs`, `command_outbox`, `outbox_events`,
  `idempotency_records`, `audit_events`, `dead_letter_commands`.
- SQLAlchemy 2.0 models with CHECK-constrained state columns + `ON DELETE RESTRICT` FKs.
- State machines for workspace/task/attempt/model_job/command with `assert_transition`.
- Repository helpers + `create_task` atomic service with idempotency.

## 4. Test results (all green)
| Test | Class | Result |
|---|---|---|
| migration up→down→up | **Critical** — data integrity | ✅ |
| atomic create success | **Critical** — core | ✅ |
| atomic create rollback (injected failure, no partial commit) | **Critical** — data integrity | ✅ |
| idempotency (sequential + 8-way concurrent → 1 task) | **Critical** — data integrity | ✅ |
| DB rejects illegal state (CHECK) | **Critical** — arch consistency | ✅ |
| FK `ON DELETE RESTRICT` | **Critical** — data integrity | ✅ |
| state-machine legality (unit) | **Critical** — arch consistency | ✅ |
| ruff / mypy / bandit / pip-audit | mixed | ✅ 0 issues |

Counts: 44 governance + 13 backend + 17 integration = **74 pass, 0 fail** locally.
Bandit 0 issues; pip-audit 0 vulns (dev + backend, incl. new sqlalchemy/alembic).

## 5. Clause conformance
See [`P2_CONFORMANCE_REPORT.md`](P2_CONFORMANCE_REPORT.md). In-scope coverage 100%.
One documented seam: deployment-reference binding in the creation transaction is
deferred to P13 (recorded, not a deviation).

## 6. Known issues / test exceptions
**None.**

## 7. Architecture deviation
**none.**

## 8. State & governance
- `PROJECT_STATE.*` updated (P2 in review).
- Approval: ⬜ pending. Merge: ⬜ open after push.
- Next gate (P3): P2 approved + merged → Command & Event Outbox dispatcher.

## 9. Commit / PR
[`P2_COMMIT_MESSAGE.txt`](P2_COMMIT_MESSAGE.txt) · [`P2_PR_DESCRIPTION.md`](P2_PR_DESCRIPTION.md).
