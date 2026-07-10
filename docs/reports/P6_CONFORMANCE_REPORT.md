# Implementation Conformance Report — P6 (cumulative P0–P6)

Per Implementation Appendix v1.1 **IMP-GOV-001/002** — clause-level status of
everything implemented through the control-plane baseline.

## Mandatory clause status

| Clause | Status | Evidence (code / tests) |
|---|---|---|
| IMP-EXEC-001 dead-letter persisted, never dropped | implemented | `queue/deadletter.py` · FR-EXEC-011 tests |
| IMP-EXEC-002 no auto-replay | implemented | no replay path; `resolution_status` workflow |
| IMP-EXEC-003 safe-duplicate binding (owner+revision+generation+live lease) | implemented | `supervisor/consumer.py` · FR-EXEC-003/005 tests |
| IMP-EXEC-004 generation triage | implemented | consumer; superseded/dead-letter tests |
| IMP-EXEC-005 recovery window w/ time context | implemented | migration `a690573bf986` · scanner |
| IMP-EXEC-006 stable run clears only consecutive | implemented | `scanner.note_stable_execution` · budget test |
| IMP-EXEC-007 distinct retry budgets | implemented | FR-EXEC-007 test |
| IMP-EXEC-008 128-bit nonce + child UUID per spawn | implemented | `supervisor/ipc.py` |
| IMP-EXEC-009 IPC validation + threshold termination | implemented | ipc unit tests (replay/sequence/UUID) |
| IMP-EXEC-010 startup_ready ≠ execution start | implemented | FR-EXEC-008 test |
| IMP-EXEC-011 8-step durable execution_started tx | implemented | `handshake.persist_execution_started` |
| IMP-EXEC-012/013 persist-fail ⇒ no begin; classified errors | implemented (subset: error taxonomy grows in P7+) | FR-EXEC-013 + begin-timeout tests |
| IMP-HIST-001/002 dual reference lifecycle + order | implemented | `history/service.py` · FR-STOR-001/003 tests |
| IMP-HIST-003/004 verification seal, no long tx, late-chunk reject | implemented | seal tests (FR-STOR-005/006/007) |
| IMP-STOR-001/002/003 reservation, atomic quota, per-fs | implemented | `storage/reservation.py` · FR-STOR-012 test |
| IMP-GOV-001/002 clause-level conformance machinery | implemented | this report chain since P0 |

## P6 validation additions (SPEC-01 §2.4 / SPEC-08 §9.3 subset)
- Control-plane API (workspace/task/status/replay): `controlplane/api.py` — e2e tested.
- WebSocket status with `after` replay + sequence dedup: `controlplane/ws.py`
  (session auth arrives in P17; loopback-only until then — documented posture).
- Runner (`controlplane/runner.py`): dispatch→consume→claim→execute→recover→publish;
  drives the SPEC-02 task machine to terminal states (fixed in P6: task
  queued→running→completed transitions + task_completed event + count decrement).
- Defects found & fixed by this phase's suite: per-request engine/pool leak
  (connection exhaustion), pure-push WS disconnect hang, undriven task states.

## Cumulative critical-test map (Freeze refs exercised so far)
FR-EXEC-001/002/003/005/006/007/008/010/011/012/013 · FR-STOR-001/003/005/006/
007/009/012 (subsets as scoped) · P6 e2e: mock retrieval, supervisor crash
recovery, event gap recovery, WS replay, history save/reopen, API idempotency.

## Summary
Mandatory clauses in scope through P6: **all implemented**, 0 deviations.
Remaining clauses (IMP-DATA-*, IMP-BACK-*) belong to P7+/P18 as planned.
