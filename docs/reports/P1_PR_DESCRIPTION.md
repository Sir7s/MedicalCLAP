# Phase P1 — Local Infrastructure & Developer Experience

Reproducible local dev environment: **one command** (`bash scripts/dev_up.sh`)
brings up PostgreSQL, Redis, Qdrant, a FastAPI backend, and a React/Vite
frontend — all bound to `127.0.0.1`. No future-phase functionality (H-01).

## Subphases completed
- [x] S1 — Compose + digest-pinned datastore images + env template
- [x] S2 — Datastores up, healthchecked, loopback-only
- [x] S3 — FastAPI + React/Vite skeletons (build + serve)
- [x] S4 — Config, JSON logging, CORS, datastore-aware `/health/ready`
- [x] S5 — One-command up + env preflight + dev guide + WSL2 volume test
- [x] S6 — CI extended (governance/backend/frontend/security/compose)

## Test summary (all green)
| Lane | Class | Result |
|---|---|---|
| container health / loopback binding | critical | passed |
| cross-service reachability (`/health/ready`) | critical | passed |
| WSL2 named-volume permission | critical | passed |
| no secret/data committed (git-tracked scan) | critical | passed |
| bandit / pip-audit (dev + backend) | critical | 0 issues / 0 vulns |
| ruff / mypy / frontend build | non-critical | passed |

**71 tests pass** (55 governance + 5 backend + 11 integration). Full evidence:
[`docs/reports/P1_EXIT_REPORT.md`](docs/reports/P1_EXIT_REPORT.md).

## Change log
- `infra/docker-compose.yml` (5 services, digest-pinned, loopback-only, healthchecks, named volumes) + `.env.example`.
- `backend/` FastAPI app: `/health`, `/health/ready`, CORS, JSON logging, config; digest-pinned Dockerfile; non-root.
- `frontend/` React+Vite+TS skeleton; digest-pinned Dockerfile; healthcheck.
- `scripts/dev_up.sh`, `scripts/env_check.sh`; `docs/DEVELOPMENT.md`.
- CI extended to backend/frontend/compose lanes; local mirror extended.
- Image digests recorded in `docs/specs/VERSION_LOCK.md`.
- Safety tests now scan **git-tracked** files (correctly ignores local `.env`/datasets).

## Conformance & deviations
- [`docs/reports/P1_CONFORMANCE_REPORT.md`](docs/reports/P1_CONFORMANCE_REPORT.md) — SPEC-01 topology + SPEC-08 loopback satisfied; runtime clauses `not_applicable` to P1.
- Architecture deviation: **none**.

## Checklist
- [x] No restricted data, weights, secrets, or PHI committed (H-13/H-14)
- [x] `PROJECT_STATE.{md,json}` updated and consistent
- [x] Phase Exit Report attached; no Known Issues report needed
- [x] `bash scripts/ci_local.sh` green locally

## Reviewer action
Approve to make the P1 Exit Report authoritative and unblock **P2 — Persistent
Database Control Plane**. Do not merge before explicit approval.
