# Phase Exit Report — P4 · Supervisor, Lease, Fencing & Mock Worker

> **Status: CANDIDATE.** Authoritative once merged (H-15). The user granted
> advance approval for this phase's merge on 2026-07-07, conditional on all
> critical tests and CI passing.

| Field | Value |
|---|---|
| Phase ID | P4 · report v1.0 |
| Architecture bundle | v2.4.5 |
| Branch | `phase/P4-supervisor` |
| Date | 2026-07-07 |
| Prerequisite | P3 merged (`aeac92a`) ✅ |

## 1. Objective (met)
Unique Lease Owner with fencing, a real (spawned) mock GPU worker speaking the
two-phase startup handshake, persist-before-begin enforcement, stage watchdog,
and forced cancel — with old leases provably unable to commit.

## 2. Subphase completion
| # | Subphase | Status | Evidence |
|---|---|---|---|
| S1 | Supervisor consumer + atomic lease acquisition | ✅ | `backend/app/supervisor/consumer.py` |
| S2 | Lease/fencing/heartbeat + recovery scanner + budget migration | ✅ | `lease.py`, `scanner.py`, migration `a690573bf986` |
| S3 | Startup nonce + IPC protocol | ✅ | `ipc.py` (+11 unit tests) |
| S4 | Mock GPU worker + two-phase handshake | ✅ | `worker.py`, `handshake.py` |
| S5 | Stage watchdog + forced cancel | ✅ | `watchdog.py` |
| S6 | CI + reports + PR | ✅ | compose lane runs supervisor tests |

## 3. Exit-gate evidence (Master Plan P4 gates)
- **Old lease cannot commit** — FR-EXEC-006 test: stale owner's state write and
  result commit both rejected (`FencedOut`), DB unchanged. ✅
- **Crash after ACK recoverable** — expired-lease takeover via scanner: job →
  recovery_required → queued, command republished with the SAME generation,
  new supervisor leases at revision+1. ✅
- **Mock worker full flow completes** — real `multiprocessing` spawn:
  consume → lease → spawn → startup_ready → persisted execution_started →
  begin_execution → 4 stages → result → job `completed`, attempt `succeeded`,
  command `resolved(succeeded)`. ✅

## 4. Test results (all green)
| Test | Freeze ref | Class | Result |
|---|---|---|---|
| fresh lease acquisition + binding | — | **Critical** — core | ✅ |
| lease-commit-before-ACK crash → single lease | FR-EXEC-003 | **Critical** — recovery | ✅ |
| fencing: old revision blocked | FR-EXEC-006 | **Critical** — data integrity | ✅ |
| recovery budget isolation + stable reset | FR-EXEC-007 | **Critical** — recovery | ✅ |
| startup_ready gating + full mock flow | FR-EXEC-008 | **Critical** — core | ✅ |
| persist failure ⇒ no begin_execution | FR-EXEC-013 | **Critical** — recovery | ✅ |
| worker exits when begin never arrives | IMP-EXEC-012 | **Critical** — recovery | ✅ |
| forced cancel → cancelled_forced, result refused | FR-EXEC-010 | **Critical** — core | ✅ |
| nonce replay / sequence / UUID / revision rejection (unit) | FR-EXEC-012 | **Critical** — security | ✅ |
| watchdog: progress vs deadline semantics (unit) | FR-EXEC-009 | **Critical** — recovery | ✅ |
| migration verified against non-empty tables | — | **Critical** — data integrity | ✅ |

Counts: 44 governance + 26 backend + 33 integration = **103 pass, 0 fail** locally.
ruff/mypy clean; bandit 0 issues; pip-audit 0 vulns.

## 5. Clause conformance
See [`P4_CONFORMANCE_REPORT.md`](P4_CONFORMANCE_REPORT.md) — in-scope coverage
100%, deviations 0, two documented scope notes (error-code taxonomy → P7+;
dedicated FR-EXEC-004 e2e variant → P6).

## 6. Known issues / test exceptions
**None.** (One migration defect — NOT NULL without server defaults — was found
by testing against non-empty tables and **fixed** before commit, not excepted.)

## 7. Architecture deviation
**none.**

## 8. State & governance
- `PROJECT_STATE.*` updated.
- User approval: ✅ granted in advance (2026-07-07), conditional on green CI.
- Merge + P5 entry: authorized upon green CI.

## 9. Commit / PR
[`P4_COMMIT_MESSAGE.txt`](P4_COMMIT_MESSAGE.txt) · [`P4_PR_DESCRIPTION.md`](P4_PR_DESCRIPTION.md).
