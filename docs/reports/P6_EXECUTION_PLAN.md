# Phase Execution Plan — P6 · Minimum Control Plane Validation

**Source:** Master Plan §P6 (p.15); Architecture SPEC-01 §2.4 (event outbox →
publisher → stream → WebSocket), SPEC-08 §9.3 (WS event-sequence dedup/replay).
**Prerequisite:** P5 merged ✅ (`0ce0b9a`). **Branch:** `phase/P6-validation`.
**Merge:** requires fresh user approval (standing grant ended at P5).

## Objective
End-to-end validation of the P2–P5 control plane as the stable baseline before
real data/models: minimal dashboard, WebSocket status with sequence-gap
recovery, a full-loop integration suite, and a P0–P6 clause conformance report.

## Scope boundary (H-01)
✅ Control-plane API (workspace/task create + status), WS event stream with
replay, in-process control-plane runner (dispatcher+supervisor+publisher tick),
minimal dashboard page, e2e tests, conformance + tech docs.
❌ No real retrieval/models (P11+), no viewer (P8), no design system (P14),
no auth hardening beyond loopback posture (P17).

## Subphases
| # | Subphase | Critical tests |
|---|---|---|
| S1 | Control-plane API: create workspace/task, task status, event replay endpoint | API status flow |
| S2 | WebSocket `/ws/{workspace_id}` (sequence-ordered, `after` replay) + runner loop + minimal dashboard | WS replay + gap recovery |
| S3 | Full-loop integration suite | **e2e mock retrieval** (API→dispatch→lease→worker→completed), **supervisor crash recovery e2e**, **event gap recovery**, **history save/reopen** |
| S4 | Clause-level Conformance Report (P0–P6) + tech doc | doc completeness |
| S5 | Fix all critical defects found | re-run suite |
| S6 | CI + reports + PR (await user approval) | full suite green |

## Key designs
- **Runner**: `controlplane/runner.py` `tick()` = dispatch_pending → supervisor
  consume/claim → publish_pending; a daemon thread in the backend (env-gated
  `MEDCLIP_RUN_CONTROLPLANE=1`, on in compose) makes the live demo self-driving;
  tests call `tick()` deterministically.
- **WS contract** (SPEC-08 §9.3 subset): client supplies `?after=<seq>`; server
  replays persisted outbox events (DB is the durable truth) in sequence order,
  then streams new ones; client dedups by `event_sequence`. Full session-auth
  arrives in P17 (loopback-only posture until then — documented).
- **Event gap recovery**: REST `GET /api/workspaces/{id}/events?after=` returns
  gapless ordered events from the outbox table.
