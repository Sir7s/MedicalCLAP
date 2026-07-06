# Implementation Conformance Report — P3

Per Implementation Appendix v1.1 **IMP-GOV-001/002**.

## Scope
P3 implements reliable delivery from the DB to the execution queue and event
stream: dispatcher, publisher, dead-letter protocol, consumer group (mock
processing), and failpoints. Real lease/fencing/GPU execution remains P4.

## Clause / spec mapping
| Spec / clause | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-01 §2.4 | Command Outbox → Dispatcher → exec queue; Event Outbox → Publisher → stream | implemented | `dispatcher.py`, `publisher.py` |
| SPEC-03 §4.2 | Command state flow pending→dispatching→dispatched | implemented | `dispatcher.dispatch_one` |
| SPEC-03 §4.6/4.7 | Recovery of stuck commands; dedup on redelivery | implemented | `dispatch_pending`; `consumer._mark_processed` |
| IMP-EXEC-001 | Invalid messages persisted to dead-letter + audit, then ACK | implemented | `deadletter.py`; `test_dead_letter_*` |
| IMP-EXEC-002 | Dead letters never auto-replayed | implemented | no replay path; `resolution_status='unresolved'` |
| IMP-EXEC-003 | Duplicate-message safety (dedup by command+generation) | implemented (P3 subset) | `consumer.process_message`; `test_duplicate_message_deduped` |
| IMP-EXEC-004 | Generation handling (behind=superseded, ahead=dead-letter) | implemented | `consumer.process_message` |
| Freeze §5 | Failpoints, disabled in prod | implemented | `failpoints.py` (`MEDCLIP_FAILPOINTS` gate) |

### Freeze tests exercised
- FR-EXEC-001 (commit crash → not lost) — `test_commit_crash_command_not_lost`
- FR-EXEC-002 (send-before-mark → one effect) — `test_send_before_mark_recovers_single_effect`
- FR-EXEC-005 (duplicate message) — `test_duplicate_message_deduped`
- FR-EXEC-011 (dead-letter missing command) — `test_dead_letter_missing_command`
- Pending claim recovery — `test_pending_claim_reprocesses_abandoned_message`

### Documented scope note (not a deviation)
The consumer's "processing" is a **mock** in P3 (validate + dedup + ACK). The
full lease-owner acquisition, fencing, and GPU worker handshake (IMP-EXEC-003's
lease/owner clauses) land in **P4**; P3 proves the delivery/dedup/dead-letter
substrate they build on.

## Summary
In-scope coverage 100%; deviations 0.
