# Phase Execution Plan — P3 · Command & Event Outbox

**Source:** Master Plan §P3 (p.12); Architecture SPEC-01 §2.4 (outbox→dispatcher→
queue; event outbox→publisher→stream), SPEC-03 §4.2/§4.6/§4.7; Appendix
IMP-EXEC-001..004; Freeze Profile §5 (failpoints), FR-EXEC-001/002/005/011.
**Prerequisite:** P2 merged ✅. **Branch:** `phase/P3-outbox`.

## Objective
Reliable delivery from the DB to the execution queue and the event stream:
Command Dispatcher, Event Outbox Publisher, dead-letter protocol, a Redis Stream
consumer group, and the first failpoints — proving committed commands are never
lost and duplicate delivery never produces duplicate business effects.

## Scope boundary (H-01)
- ✅ P3: dispatcher, publisher, dead-letter, consumer group (with a **mock**
  processing step that validates + dedups + acks), failpoint framework, recovery.
- ❌ Not P3: real lease/fencing/heartbeat and GPU worker (**P4**), artifacts (**P5**).
  The consumer's processing is a mock that stops at "validated & recorded".

## Subphases (sequential)
| # | Subphase | Artifacts | Critical tests |
|---|---|---|---|
| S1 | Command Dispatcher | `backend/app/queue/redis_client.py`, `dispatcher.py` | send-before-mark + commit-crash recovery |
| S2 | Event Outbox Publisher | `backend/app/queue/publisher.py` | events published in sequence, idempotent |
| S3 | Dead-letter protocol | `backend/app/queue/deadletter.py` | invalid msg → persisted + audit + ACK, no auto-replay (IMP-EXEC-001/002) |
| S4 | Redis Stream consumer group | `backend/app/queue/consumer.py` | duplicate message dedup; XAUTOCLAIM pending recovery |
| S5 | Failpoints + crash tests | `backend/app/failpoints.py`, tests | FR-EXEC-001/002/005/011 |
| S6 | CI + reports + PR | ci.yml, reports | full suite green |

## Reliability model
- **Execution queue** = Redis Stream `exec:commands`; **event stream** =
  `events:stream`. Consumer group `supervisors` on the exec stream.
- **Dispatcher**: `pending → dispatching` (commit) → `XADD` → `dispatching →
  dispatched` (commit). Crash between commit and send, or between send and mark,
  is recovered by re-dispatching stuck `pending`/`dispatching` commands
  (re-`XADD`); the consumer **dedups** by `(command_id, command_generation)` via
  `idempotency_records`, so at most one business effect (FR-EXEC-001/002/005).
- **Dead-letter** (IMP-EXEC-001/002): missing command/job, schema/generation
  mismatch → persist `dead_letter_commands` + audit event + `XACK`; never
  auto-replayed (FR-EXEC-011).
- **Pending claim**: a crashed consumer's un-acked messages are reclaimed with
  `XAUTOCLAIM` and reprocessed idempotently.

## Failpoints (Freeze Profile §5; test-only, `failpoints_disabled=true` in prod)
`FP-EXEC-AFTER-COMMAND-COMMIT`, `FP-EXEC-AFTER-QUEUE-SEND`,
`FP-EXEC-BEFORE-DISPATCH-MARK` — armed by tests to inject crashes at exact points.

## Tests (critical)
FR-EXEC-001 commit crash → recovered; FR-EXEC-002 send-before-mark → one effect;
FR-EXEC-005 duplicate message → one effect; FR-EXEC-011 dead-letter; pending
claim recovery; publisher ordering/idempotency. Auto-skip without Redis+PG; run
in the compose CI lane.

## Deliverables
Dispatcher/publisher/consumer/dead-letter/failpoint modules, tests, CI update,
Conformance + Exit reports, updated PROJECT_STATE.
