# Phase Exit Report — P6 · Minimum Control Plane Validation

> **Status: CANDIDATE — awaiting user approval + merge** (the standing merge
> grant ended at P5; H-15 requires fresh approval for this PR).

| Field | Value |
|---|---|
| Phase ID | P6 · report v1.0 |
| Branch | `phase/P6-validation` |
| Date | 2026-07-07 |
| Prerequisite | P5 merged (`0ce0b9a`) ✅ |

## 1. Objective (met)
End-to-end validation of the P2–P5 control plane as the stable baseline before
real data/models: minimal dashboard, WebSocket status with replay, a full-loop
e2e suite, and the cumulative P0–P6 conformance report.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Control-plane API (workspaces/tasks/status/event replay) | ✅ |
| S2 | WebSocket `/ws/{workspace_id}?after=` + runner + minimal dashboard | ✅ |
| S3 | Full-loop e2e suite (6 tests) | ✅ |
| S4 | Cumulative P0–P6 conformance report | ✅ |
| S5 | Critical defects found → **fixed** (below) | ✅ |
| S6 | CI + reports + PR | ✅ |

## 3. Exit-gate evidence (Master Plan P6 gates)
- **End-to-end mock retrieval** — API create → dispatch → lease → real spawned
  worker handshake → `completed/succeeded/resolved`, gapless event trail, all
  events published. ✅
- **Supervisor crash recovery** — lease-commit-before-ACK crash mid-flow; the
  next ticks recover via pending-claim and finish at lease revision 1 (no
  double-lease, no duplicate execution). ✅
- **Event gap recovery** — REST replay returns gapless ordered tail after any
  sequence; WS replays from `after` with client-side dedup. ✅
- **History save/reopen** — save via API → listed → reopened `ready`;
  non-existent/non-ready invisible (404). ✅
- **No architecture deviation.** ✅

## 4. Defects found by this phase's validation (all FIXED, none excepted)
1. **Connection-pool leak** — every API call built a new SQLAlchemy engine;
   Postgres connections exhausted under the e2e suite. Fixed: process-wide
   cached engine per DSN (`db/base.py`).
2. **WS disconnect hang** — pure-push WebSocket loop never observed client
   close. Fixed: `receive` with timeout doubling as the poll interval.
3. **Undriven task states** — ApplicationTask stayed `queued` forever; jobs
   completed but tasks never did. Fixed: handshake drives task
   `queued→running→completed`, emits `task_completed`, decrements the
   workspace active-task count.

This is precisely the class of integration defect P6 exists to catch before
real data (P7+) lands on the control plane.

## 5. Test results
**121 tests pass, 0 fail** (44 governance + 26 backend + 51 integration incl.
6 new e2e); frontend builds (dashboard included); ruff/mypy/bandit/pip-audit
clean. Full regression of P2–P5 suites re-run green after the fixes.

## 6. Conformance
[`P6_CONFORMANCE_REPORT.md`](P6_CONFORMANCE_REPORT.md) — all mandatory clauses
in scope through P6 implemented; 0 deviations.

## 7. Known issues / exceptions
**None.**

## 8. Governance
`PROJECT_STATE.*` updated. **User approval + merge required** to make this the
approved control-plane baseline and unlock P7 (CT-RATE Acquisition).
