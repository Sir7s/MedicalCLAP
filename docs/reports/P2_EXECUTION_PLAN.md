# Phase Execution Plan — P2 · Persistent Database Control Plane

**Source:** Master Plan v1.0 §P2 (p.11); Architecture v2.4.5 SPEC-02 (persistent
control plane, state authority, core tables, state machines) and SPEC-03 §4.1
(atomic creation transaction), §4.2 (command states); Implementation Appendix
IMP-EXEC-001 (`dead_letter_commands`). **Prerequisite:** P1 merged ✅.
**Branch:** `phase/P2-control-plane`.

## Objective
Implement the persistent control plane: core tables, state-machine constants +
validators, a repository layer, and an all-or-nothing transactional task
creation — on the PostgreSQL stood up in P1.

## Scope boundary (H-01)
- ✅ P2: control-plane core tables (workspace/task/attempt/model_job,
  command_outbox, outbox_events, idempotency_records, audit_events,
  dead_letter_commands), state machines, repositories, atomic task creation,
  Alembic up/down.
- ❌ Not P2: the actual dispatcher/publisher/consumer loops (**P3**), supervisor/
  lease/worker (**P4**), artifact/history tables (**P5**), dataset/model/qdrant/
  backup/freeze tables (their phases). Deployment-reference binding inside the
  creation transaction is added in **P13** when deployments exist — P2 implements
  the transaction for the entities that exist now and documents the seam.

## Subphases (strictly sequential)
| # | Subphase | Key artifacts | Critical tests |
|---|---|---|---|
| S1 | Alembic framework | `backend/app/db/base.py`, `backend/alembic.ini`, `backend/alembic/env.py` wired to settings DSN | **migration up/down** round-trip |
| S2 | Core tables + constraints | `backend/app/db/models.py` (9 tables), FKs `ON DELETE RESTRICT`, CHECK/UNIQUE constraints; initial migration | schema matches spec; constraints reject bad rows |
| S3 | State-machine constants + validators | `backend/app/db/states.py` (Task/Attempt/ModelJob/Command/Workspace states + legal transitions), `assert_transition()` | **illegal-state** rejected; legal allowed |
| S4 | Repository layer | `backend/app/db/repository.py` (typed CRUD + guarded transitions) | repo transition guard tests |
| S5 | Transactional task creation | `backend/app/db/service.py::create_task()` (SPEC-03 §4.1) | **atomicity** (no partial commit on injected failure); **concurrency idempotency** |
| S6 | CI + reports + PR | extend `compose` CI lane to run DB integration tests; conformance; exit report | full suite green |

## Atomic creation transaction (SPEC-03 §4.1, P2 subset)
Single DB transaction: (1) lock `application_tasks` row + validate state →
(2) create `task_attempts` + `model_jobs` → (3) increment workspace active-task
count → (4) insert `outbox_events` → (5) insert `command_outbox` → commit.
Any failure rolls back **all** (verified by a failpoint that raises before commit
and asserts zero rows persisted). Idempotency via `idempotency_records`
unique key so concurrent duplicate requests yield exactly one task.

## Tests (critical unless noted)
- Migration up→down→up round-trip (data-integrity).
- Constraint tests: illegal enum state, FK `ON DELETE RESTRICT`, unique idempotency key.
- State-machine: legal vs illegal transitions (architecture-consistency).
- Atomic task creation: success path + injected-failure rollback (no partial commit).
- Concurrency idempotency: N concurrent identical creates → 1 task (data-integrity).
- All DB integration tests auto-skip without Postgres; run in the compose CI lane.

## Deliverables
Alembic migrations, SQLAlchemy models, state validators, repository + service
layers, tests, CI update, Conformance + Exit reports, updated PROJECT_STATE.

## Risks
- **R1:** Modeling drift vs SPEC-02 → mitigated by mapping each table/state to a
  spec reference in the Conformance report.
- **R2:** Async vs sync SQLAlchemy → P2 uses **sync** SQLAlchemy + psycopg
  (already a backend dep) for the control plane; FastAPI endpoints stay minimal
  (no new API surface required by P2).
