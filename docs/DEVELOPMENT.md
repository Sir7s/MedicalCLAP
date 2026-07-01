# Development Guide

Local development environment for 3D Medical CLIP (introduced in **P1**).

## Prerequisites

- Windows 11 with **WSL2** (Ubuntu) and **Docker Desktop** (WSL2 integration enabled).
- Docker Desktop running (whale icon → "running").
- Python 3.11+ and Node 20+ only needed for running tests/lint outside containers.

Check your machine:

```bash
bash scripts/env_check.sh
```

## One-command bring-up

```bash
bash scripts/dev_up.sh          # build + start the whole stack, wait for health
bash scripts/dev_up.sh down     # stop (keeps data volumes)
bash scripts/dev_up.sh nuke     # stop and delete data volumes
```

On success:

| Service | URL / address |
|---|---|
| Frontend | http://127.0.0.1:5173 |
| Backend API | http://127.0.0.1:8000 — `/health`, `/health/ready`, `/docs` |
| PostgreSQL | 127.0.0.1:5432 |
| Redis | 127.0.0.1:6379 |
| Qdrant | http://127.0.0.1:6333 |

All services bind to **127.0.0.1 only** (Architecture SPEC-08). Nothing is
exposed on a public interface.

## Configuration

Copy `infra/.env.example` → `infra/.env` (auto-created by `dev_up.sh`) and edit.
`infra/.env` is git-ignored and must never be committed. Image versions are
pinned by digest in `infra/docker-compose.yml` (see `docs/specs/VERSION_LOCK.md`).

## Layout (as of P1)

```
backend/   FastAPI app (app/main.py: /health, /health/ready), Dockerfile, tests
frontend/  React + Vite + TS skeleton, Dockerfile
infra/     docker-compose.yml, .env.example
scripts/   env_check.sh, dev_up.sh, ci_local.sh, spec_manifest.py
tests/     governance tests + tests/infra (integration, auto-skip if stack down)
```

## Tests

```bash
# Unit / governance (no Docker needed) — from repo root
python -m pytest tests -q

# Backend unit tests
cd backend && python -m pytest -q

# Integration tests (require the stack: bash scripts/dev_up.sh)
python -m pytest tests/infra -q

# Full local CI mirror
bash scripts/ci_local.sh
```

> On this machine the dev toolchain lives in a specific Python. If `python`
> lacks pytest/ruff, use that interpreter or `PYTHON=<path> bash scripts/ci_local.sh`.

## Reproducing on another machine

1. Install Docker Desktop + WSL2, clone the repo.
2. `bash scripts/env_check.sh` then `bash scripts/dev_up.sh`.
3. Because images are digest-pinned and app images build from the repo, the
   stack is byte-reproducible up to base-image availability.

## Notes

- Datastores use **named Docker volumes** (`pgdata`, `redisdata`, `qdrantdata`)
  rather than host bind mounts, to avoid WSL2/Windows path-permission issues.
- This is a research/demo prototype — not for clinical use.
