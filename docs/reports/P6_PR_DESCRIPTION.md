# Phase P6 — Minimum Control Plane Validation

End-to-end validation of the P2–P5 control plane as the stable baseline before
real data/models: control-plane API, WebSocket status with replay, self-driving
runner, minimal dashboard, and a full-loop e2e suite.

## Exit-gate evidence
| Gate | Evidence |
|---|---|
| e2e mock retrieval | API → dispatch → lease → spawned worker → completed; gapless, fully-published event trail |
| supervisor crash recovery | lease-before-ACK crash mid-flow → pending-claim recovery → completed at revision 1 |
| event gap recovery | REST replay gapless after any `after`; WS replay + dedup |
| history save/reopen | save → list → reopen `ready`; non-ready invisible |

## Defects found by validation (all fixed, none excepted)
1. Per-request engine/pool construction → Postgres connection exhaustion (cached engine per DSN).
2. Pure-push WebSocket never detected client disconnect (receive-with-timeout loop).
3. ApplicationTask states never driven to terminal (handshake now closes the SPEC-02 task machine + emits `task_completed` + decrements active count).

## Test summary
**121 tests pass** (44 governance + 26 backend + 51 integration incl. 6 e2e);
frontend builds; ruff/mypy/bandit/pip-audit clean; full P2–P5 regression green.
Evidence: [`docs/reports/P6_EXIT_REPORT.md`](docs/reports/P6_EXIT_REPORT.md) ·
cumulative conformance: [`docs/reports/P6_CONFORMANCE_REPORT.md`](docs/reports/P6_CONFORMANCE_REPORT.md).

## Change log
- `backend/app/controlplane/`: `api.py`, `ws.py`, `runner.py` (tick + background loop, env-gated).
- `backend/app/supervisor/handshake.py`: drives task states + completion event.
- `backend/app/db/base.py`: process-wide cached engine (pool fix).
- `backend/Dockerfile` + compose: migrations on container start; runner enabled.
- `frontend/src/Dashboard.tsx` (+App wiring): minimal live dashboard (tasks + WS events).
- Tests: `tests/infra/test_controlplane_e2e.py` (6).

## Approval
**Requires fresh user approval to merge** (standing grant ended at P5).
Merging approves the control-plane baseline and unlocks P7 — CT-RATE Acquisition.
