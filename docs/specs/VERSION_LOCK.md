# Specification Version Lock — P0 Baseline

This file pins the authoritative governance documents for the 3D Medical CLIP
project. It is the human-readable companion to
[`SPEC_MANIFEST.json`](SPEC_MANIFEST.json), which is the machine-checked source
of truth (regenerate with `python scripts/spec_manifest.py --write`, verify with
`--check`).

> Locked during **P0 — Specification Baseline & Repository Bootstrap**.
> Any change to a locked document's bytes changes its SHA-256 and **fails**
> `tests/test_doc_integrity.py`, which forces the Architecture Update Flow
> (Architecture v2.4.5 §14.2) rather than a silent edit.

## Locked authoritative documents

| Spec ID | Document | Version | Status | SHA-256 |
|---|---|---|---|---|
| DOC-ARCH | Architecture Specification Bundle | 2.4.5 | final_freeze_candidate | `d7f98c0baeb933e6cbd18824f407e2fce93cd5f26691499d4adb932945117146` |
| DOC-MASTER | Master Phased AI Execution Plan | 1.0 | approved_execution_baseline | `e7e72d230f022398cbd46368593837c42c595de561a85790bd6049d89dd7a935` |
| DOC-APPENDIX | Implementation Appendix | 1.1 | implementation_ready | `ded514a4a7908a3ec645ef8ced0d33f3b592900bfacdf524db416e030cd3ae9e` |
| DOC-FREEZE | Freeze Test Profile | 1.1 | ready_for_execution | `c5216be79114b087357fdb66ab59652d5846947d7071d9fbe326d24674a7b954` |

**Documents root SHA-256** (normative form `SPEC_ID + NUL + VERSION + NUL + lowercase_hex_sha256 + LF`, sorted by `spec_id`):

```
a989695c517c1c5f71e8e9d9b929be214e02b3bc257c2cc274de8f40f58c3e92
```

## Toolchain baseline (locked for CI reproducibility)

Only the **toolchain** is pinned in P0. Application dependencies
(FastAPI, React, PyTorch, vtk.js, Qdrant client, …) are deliberately **not**
pinned here — they are introduced and locked in the phases that add them
(P1+), per the Master Plan scope boundaries and Hard Constraint H-01.

| Component | Pinned value | Source of truth |
|---|---|---|
| Python (runtime + CI) | 3.11 | `.github/workflows/ci.yml`, `pyproject.toml` |
| Node.js (CI) | 20.x | `.github/workflows/ci.yml`, `frontend/.nvmrc` |
| Lint (Python) | ruff (pinned in `requirements-dev.txt`) | `requirements-dev.txt` |
| Type check (Python) | mypy (pinned in `requirements-dev.txt`) | `requirements-dev.txt` |
| Unit tests | pytest + pytest-cov (pinned) | `requirements-dev.txt` |
| Secret scan | gitleaks (action-pinned by SHA in CI) | `.github/workflows/ci.yml` |
| SAST | bandit (pinned) | `requirements-dev.txt` |
| Dependency audit | pip-audit (pinned) | `requirements-dev.txt` |
| Base container digest | locked in P1 with `docker-compose.yml` | (deferred — P1) |

## Living (unpinned) state

`PROJECT_STATE.md` and `project_state.json` are **living phase state**, updated
every phase. They are intentionally excluded from the immutable document lock
above; their consistency is enforced separately by
`tests/test_project_state_sync.py`.
