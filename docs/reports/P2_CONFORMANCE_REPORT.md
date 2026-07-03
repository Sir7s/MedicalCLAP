# Implementation Conformance Report — P2

Per Implementation Appendix v1.1 **IMP-GOV-001/002**.

## Scope
P2 implements the persistent control-plane core (SPEC-02 §3.2 subset) + the
atomic creation transaction (SPEC-03 §4.1, for entities that exist now) + the
dead-letter table (IMP-EXEC-001). Full EXEC/HIST/STOR/BACK/DATA runtime
behavior remains in later phases.

## Architecture / clause mapping
| Spec / clause | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-02 §3.2 | Core control-plane tables | implemented | `backend/app/db/models.py`; migration `2d80d962a004` |
| SPEC-02 §3.3 | Workspace states; child FKs `ON DELETE RESTRICT` | implemented | `states.WORKSPACE_*`; FKs in models; `test_fk_ondelete_restrict` |
| SPEC-02 §3.4 | Task / Attempt / Model Job state machines | implemented | `states.py`; `test_states.py` |
| SPEC-03 §4.1 | Atomic creation (all-or-nothing) | implemented (P2 subset) | `service.create_task`; `test_atomic_create_success/_rollback_on_failure` |
| SPEC-03 §4.2 | Command state machine | implemented | `states.COMMAND_*`; `test_states.py` |
| IMP-EXEC-001 | `dead_letter_commands` table | implemented (schema) | `models.DeadLetterCommand`; migration |
| Idempotency | duplicate requests → one task | implemented | `idempotency_records` unique; `test_idempotent_*` |

### Documented seam (not a deviation)
SPEC-03 §4.1 step 3 (bind Deployment Execution Reference) is **deferred to P13**
when `model_deployments` exists. P2 implements the transaction for the entities
present now; the atomicity property is fully honored for them. Recorded here so
the P13 conformance report closes the seam.

## Deferred mandatory clauses (not_applicable in P2)
`IMP-EXEC-002..013`, `IMP-HIST-*`, `IMP-STOR-*`, `IMP-BACK-*`, `IMP-DATA-*` —
implemented in their phases; the dispatcher/consumer/lease/worker loops that
exercise the command/lease columns arrive in P3–P4.

## Summary
In-scope mandatory coverage 100%; deviations 0.
