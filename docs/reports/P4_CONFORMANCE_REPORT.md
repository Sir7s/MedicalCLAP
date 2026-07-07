# Implementation Conformance Report — P4

Per Implementation Appendix v1.1 **IMP-GOV-001/002**.

## Scope
P4 implements the unique Lease Owner: supervisor consumption, lease/fencing/
heartbeat, recovery scanner + budgets, startup nonce + IPC validation, the
two-phase GPU startup handshake with a mock worker, and watchdog/forced-cancel.
Real model execution remains P11+; artifact finalize remains P5.

## Clause / spec mapping
| Spec / clause | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-03 §4.3 | Supervisor is the unique lease owner | implemented | `supervisor/lease.py`, `consumer.py` (single acquisition door) |
| SPEC-03 §4.4 | Consumption order: validate → atomic lease+bind → commit → ACK → spawn | implemented | `consumer.process_execution_message`; `test_fresh_lease_acquisition_and_binding` |
| SPEC-03 §4.5 | Fencing: writes carry owner + revision; stale owners blocked | implemented | `lease.fenced`; FR-EXEC-006 test |
| SPEC-03 §4.6 | Recovery scanner: expired lease → recovery_required + failed_retryable, republish SAME generation | implemented | `scanner.recover_expired_leases`; fencing/budget tests |
| SPEC-03 §4.8 | Worker: spawn, nonce, child UUID, monotonic sequence, no DB writes | implemented | `worker.py` (multiprocessing spawn; DB-free) |
| SPEC-03 §4.9 | Stage watchdog policies | implemented | `watchdog.StageWatch`; FR-EXEC-009 unit tests |
| SPEC-03 §4.10 | cooperative stop → terminate → kill ladder | implemented | `watchdog.forced_terminate`; FR-EXEC-010 test |
| IMP-EXEC-003 | Safe-duplicate = binding+generation+owner+revision+live lease; else recovery_required, never guessed | implemented | `consumer.py`; FR-EXEC-003 test |
| IMP-EXEC-004 | Generation triage (behind=superseded, ahead=dead-letter) | implemented | `consumer.py` (carried from P3, now lease-aware) |
| IMP-EXEC-005 | Recovery counters with time context (window/last/consecutive/total) | implemented | migration `a690573bf986`; `scanner.py` |
| IMP-EXEC-006 | Stable run clears ONLY consecutive failures | implemented | `scanner.note_stable_execution`; budget test |
| IMP-EXEC-007 | Distinct budgets: dispatch / delivery / lease-recovery / execution / attempt | implemented | columns + FR-EXEC-007 test |
| IMP-EXEC-008 | Fresh 128-bit nonce + child UUID per spawn | implemented | `ipc.new_child_identity` (secrets, 128-bit) |
| IMP-EXEC-009 | Validate job/revision/nonce/UUID/sequence; drop + count; terminate on threshold | implemented | `ipc.IpcValidator`; unit tests incl. FR-EXEC-012 |
| IMP-EXEC-010 | startup_ready ≠ execution start | implemented | `worker.py` waits; FR-EXEC-008 test |
| IMP-EXEC-011 | 8-step durable execution_started transaction | implemented | `handshake.persist_execution_started` |
| IMP-EXEC-012/013 | Persist failure ⇒ no begin_execution; child waits/exits | implemented | FR-EXEC-013 test + begin-timeout test |

### Freeze tests exercised
FR-EXEC-003 (lease-before-ACK crash → safe duplicate, single lease),
FR-EXEC-006 (fencing), FR-EXEC-007 (budget isolation), FR-EXEC-008
(startup_ready gating), FR-EXEC-009 (watchdog semantics, unit), FR-EXEC-010
(forced cancel, no result), FR-EXEC-012 (nonce replay), FR-EXEC-013
(persist-before-begin), plus the full mock execution flow (queued→completed).

### Documented scope notes (not deviations)
- IMP-EXEC-013 error-code classification table: the taxonomy applies from P7+
  (dataset/model error codes); the P4 recovery paths use the retryable-only
  subset. Full table lands with the phases that produce those errors.
- FR-EXEC-004 (ACK-after-lease, before GPU start crash) is exercised implicitly
  by the scanner takeover path; the dedicated end-to-end variant joins the P6
  control-plane validation suite.

## Summary
In-scope mandatory coverage 100%; deviations 0.
