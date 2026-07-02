# Phase Execution Plan — P1 · Local Infrastructure & Developer Experience

**Source:** Master Plan v1.0 §P1 (p.10); Architecture v2.4.5 SPEC-01 §2.4–2.5
(service list), SPEC-08 §9.1 (bind 127.0.0.1). **Prerequisite:** P0 effective ✅
(PR #1 merged). **Branch:** `phase/P1-infrastructure`.

## Objective
Stand up a reproducible Windows 11 + WSL2 + Docker Desktop development
environment: one command brings up PostgreSQL, Redis, and Qdrant plus a FastAPI
backend and a React/Vite frontend skeleton, with config, logging, health checks,
and an environment-check script.

## ⛔ Blocking prerequisite (must resolve before S2+)
`docker` is **not installed / not on PATH** on this machine (Docker Desktop
absent; WSL2 `Ubuntu` present but **Stopped**). P1's exit gate is *"one command
starts all base services"* and its critical tests require containers to run —
these **cannot be executed or honestly evidenced without Docker**. Per H-02/H-03
I will not fake bring-up results. Resolution options are listed at the bottom.

## Scope boundary (H-01)
- ✅ P1: datastores (PostgreSQL/Redis/Qdrant), FastAPI app skeleton + `/health`,
  React/Vite skeleton, config/logging, one-command up, env-check, dev guide,
  **base image digest locks**.
- ❌ Not P1: DB schema/migrations (P2), command dispatcher / outbox publisher /
  model_service logic (P3+), any model or retrieval code, real UI pages (P8/P14).
  Those service dirs stay placeholders or get empty health-only stubs.

## Subphases (strictly sequential)

| # | Subphase | Key files | Evidence / tests |
|---|---|---|---|
| S1 | Compose + **pinned image digests** + env template | `infra/docker-compose.yml`, `infra/.env.example`, `docs/DEPENDENCY_LOCK.md` update | compose `config` validates; digests recorded |
| S2 | Bring up PostgreSQL / Redis / Qdrant (127.0.0.1 only) | compose service defs, named volumes | **container health checks** pass; ports bound to loopback only |
| S3 | FastAPI backend + React/Vite frontend skeletons | `backend/app/main.py` (+`/health`), `backend/requirements.txt`, `frontend/` (Vite app) | backend unit test hits `/health`; `vite build` succeeds |
| S4 | Config, structured logging, health/readiness | `backend/app/config.py`, `backend/app/logging.py`, `/health` aggregating datastore pings | **cross-service network test** (backend reaches PG/Redis/Qdrant) |
| S5 | One-command up + environment preflight + dev guide | `scripts/dev_up.sh`, `scripts/env_check.sh`, `docs/DEVELOPMENT.md` | **WSL2 path/volume permission test**; clean-clone bring-up |

## Critical vs non-critical tests (Master Plan §6)
| Test | Class | Basis |
|---|---|---|
| Container health checks (S2) | **Critical** | core functionality / recovery |
| Cross-service network reachability (S4) | **Critical** | core functionality |
| Loopback-only binding (no public exposure) | **Critical** | security (SPEC-08) |
| WSL2 path/volume permissions (S5) | **Critical** | data integrity / reproducibility |
| No secret / local-path leakage | **Critical** | security (H-14) |
| `vite build`, lint/type | Non-critical | supporting |

## Coverage policy (risk-based)
Backend health/config code: aim high (this is core plumbing). Frontend skeleton:
build-only. No uniform global % (still mostly scaffolding).

## CI additions
Extend `.github/workflows/ci.yml`: real `docker-build` (compose config validate +
build backend image), backend pytest lane, frontend `npm ci && vite build`.
Compose bring-up itself is validated locally (GitHub runners can run compose, but
GPU/WSL specifics are local — documented).

## Risks
- **R1 (blocking):** No Docker → S2/S4/S5 unexecutable. → resolve first.
- **R2:** Image digest pinning needs registry access (Docker or `skopeo`). If
  Docker is unavailable I can fetch digests via registry API, else defer to S1
  once Docker is up.
- **R3:** WSL2 volume-permission quirks on Windows bind mounts → use named
  volumes for datastores, document path rules.

## Deliverables
`docker-compose.yml`, backend+frontend skeletons, config/logging/health,
`dev_up.sh`/`env_check.sh`, `DEVELOPMENT.md`, digest locks, tests, CI update,
Phase Exit Report + Conformance + updated PROJECT_STATE.

## Resolution options for the Docker prerequisite
1. **Install Docker Desktop** (recommended) — enable WSL2 integration, start it,
   then I execute P1 fully with real health-check evidence.
2. **I author all non-runtime P1 artifacts now** (compose, skeletons, scripts,
   docs, digests via registry API) and mark the runtime bring-up subphases
   **blocked/deferred** with a Known-Issues entry until Docker is available — no
   fabricated results.
3. **Pause P1** until you're ready to set up Docker.
