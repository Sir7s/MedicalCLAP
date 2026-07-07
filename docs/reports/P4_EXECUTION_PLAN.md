# Phase Execution Plan — P4 · Supervisor, Lease, Fencing & Mock Worker

**Source:** Master Plan §P4 (p.13); Architecture SPEC-03 §4.3 (unique lease
owner), §4.4 (consumption order), §4.5 (fencing), §4.6 (recovery scanner),
§4.8 (GPU worker protocol), §4.9 (stage watchdog), §4.10 (forced termination);
Appendix IMP-EXEC-003..013; Freeze Profile FR-EXEC-003/004/006/007/008/010/012/013.
**Prerequisite:** P3 merged ✅ (`aeac92a`). **Branch:** `phase/P4-supervisor`.

## Objective
The unique Lease Owner: a Model Job Supervisor that atomically acquires and
fences leases, performs the two-phase GPU startup handshake with a mock worker
(spawned via `multiprocessing`), enforces persist-before-begin, watches stage
deadlines, and can force-cancel — with old leases provably unable to commit.

## Scope boundary (H-01)
- ✅ P4: lease acquire/renew/fencing, recovery counters + scanner, startup nonce
  + IPC validation, mock GPU worker (simulated stages — **no real model**),
  two-phase handshake, watchdog + forced cancel, migration for the new columns.
- ❌ Not P4: artifact finalize / workspace files (**P5**), real GPU/model code
  (**P11+**), dashboard/WebSocket (**P6**).

## Subphases (sequential)
| # | Subphase | Artifacts | Critical tests |
|---|---|---|---|
| S1 | Supervisor consumer + atomic lease acquisition | `backend/app/supervisor/consumer.py` | lease-before-ACK crash (FR-EXEC-003); safe-duplicate per IMP-EXEC-003 |
| S2 | Lease/fencing/heartbeat + recovery scanner + counters migration | `lease.py`, `scanner.py`, Alembic migration | fencing (FR-EXEC-006); counter isolation (FR-EXEC-007); expired-lease takeover |
| S3 | Startup nonce + IPC protocol | `ipc.py` | nonce replay rejected (FR-EXEC-012); sequence monotonicity |
| S4 | Mock GPU worker + two-phase handshake | `worker.py`, `handshake.py` | startup_ready ≠ execution (FR-EXEC-008); persist-before-begin (FR-EXEC-013); full mock flow |
| S5 | Stage watchdog + forced cancel | `watchdog.py` | forced cancel → cancelled_forced, no result (FR-EXEC-010); long-stage not killed early (FR-EXEC-009, unit) |
| S6 | CI + reports + PR | ci runs supervisor tests | full suite green |

## Key designs
- **Consumption order (SPEC-03 §4.4):** receive → load command+job → validate
  generation → **atomically** (job `queued→leased`, `execution_lease_revision+=1`,
  owner id, expiry, heartbeat; command `dispatched→worker_received→lease_acquired`,
  bind owner+revision) → commit → **ACK** → spawn worker.
- **Safe duplicate (IMP-EXEC-003):** re-delivered message is ACK-only iff
  aggregate, generation, lease revision, owner all match AND lease unexpired AND
  heartbeat fresh; else the job goes `recovery_required` — never guessed.
- **Fencing (SPEC-03 §4.5):** every supervisor write goes through a fenced
  helper that re-validates `(worker_instance_id, execution_lease_revision)`
  in the same transaction; stale owners get `FencedOut` and change nothing.
- **Recovery budgets (IMP-EXEC-005/006/007):** migration adds
  `recovery_window_started_at`, `last_recovery_at`,
  `consecutive_recovery_failures`, `total_recovery_attempts`,
  `delivery_attempts`, `lease_recovery_attempts` to `command_outbox` and
  `execution_attempts` to `model_jobs`; stable-run reset clears only the
  consecutive counter.
- **Two-phase handshake (IMP-EXEC-010..013):** spawn → child `startup_ready` →
  supervisor persists `execution_started` in one fenced transaction (command →
  `execution_started`, attempt → `running`, job → `loading_model`, store PID /
  child UUID / nonce hash, event outbox) → only then `begin_execution`. Persist
  failure ⇒ no begin; child times out waiting and exits.
- **IPC validation (IMP-EXEC-008/009):** all child messages carry job id, lease
  revision, 128-bit nonce, child UUID, monotonic sequence; any mismatch is
  dropped + counted; replayed (stale-nonce) messages rejected.
- **Forced cancel (SPEC-03 §4.10):** cooperative stop → grace → terminate →
  grace → kill → join; job → `cancelling → cancelled_forced`; fenced result
  commit is refused afterwards.

## Tests (critical; integration auto-skips without PG+Redis; run in compose lane)
FR-EXEC-003 lease-commit-before-ACK crash → duplicate ACKed, single lease;
FR-EXEC-006 old-revision writes rejected; FR-EXEC-007 budget isolation;
FR-EXEC-008 spawn does not advance state before startup_ready persisted;
FR-EXEC-012 nonce replay rejected; FR-EXEC-013 persist failure ⇒ no begin;
FR-EXEC-010 forced cancel; end-to-end mock flow queued→completed.

## Risks
- **R1:** `multiprocessing` spawn on Windows + CI Linux differences → worker
  entrypoint is a top-level importable function; tests use generous timeouts.
- **R2:** flaky timing in handshake tests → all waits are event/queue-based with
  explicit deadlines, no sleeps as synchronization.

## Deliverables
Supervisor package, migration, mock worker, watchdog, IPC validator, tests,
CI update, Conformance + Exit reports, updated PROJECT_STATE.
