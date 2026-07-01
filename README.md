# 3D Medical CLIP

> Local 3D chest-CT ↔ radiology-report retrieval, history management, and an
> experimental text-guided 3D segmentation platform.

[![CI](https://github.com/Sir7s/MedicalCLAP/actions/workflows/ci.yml/badge.svg)](https://github.com/Sir7s/MedicalCLAP/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ⚠️ Medical disclaimer

**For research and demonstration use only. Not intended for clinical diagnosis
or treatment decisions.** Similarity scores are embedding distances, **not**
diagnostic probabilities. Model-generated highlights and segmentations require
independent expert review. This project is **not** a medical device, diagnostic
system, or clinical decision-support system.

---

## What this is

A portfolio-grade, locally-runnable research platform built strictly against a
frozen specification bundle. The primary capability is **bidirectional retrieval**
between a 3D chest CT and free-text radiology reports; segmentation is an
experimental, gated feature.

| Capability | Summary |
|---|---|
| Retrieval (primary) | CT→Report and Report→CT over CT-RATE; PointNet++ image encoder + BioClinicalBERT text encoder, 512-d L2-normalized embeddings; evaluated with Recall@K, mAP, nDCG |
| Viewer | Upload a single chest CT (NIfTI); 3 orthogonal views, WW/WL, basic volume rendering, polygon annotation |
| Bilingual UX | Chinese/English UI; Chinese text locally translated to English before retrieval; English voice input (local Whisper) |
| History & export | Full history (lightweight / full-archive / re-executable profiles), PDF + JSON export |
| Segmentation (experimental) | Text-guided 3D segmentation over ReXGroundingCT, gated by a formal feasibility gate (SPEC-10) |

## Tech stack (target)

Frontend: React + Tailwind + vtk.js · Backend: FastAPI control plane ·
PostgreSQL (durable truth) · Redis (queue/stream/cache) · Qdrant (versioned
vector index) · Docker Compose (reproducible local deployment).

> The full service topology and dependencies come online across phases P1–P13;
> this repository is currently at **P0 (bootstrap)** — see governance below.

## Status & governance

This project is executed as a strict, phased program. The authoritative sources
are version-locked under [`docs/specs/`](docs/specs/) and pinned by
[`SPEC_MANIFEST.json`](docs/specs/SPEC_MANIFEST.json):

- Architecture Specification Bundle **v2.4.5** (`final_freeze_candidate`)
- Master Phased AI Execution Plan **v1.0**
- Implementation Appendix **v1.1**
- Freeze Test Profile **v1.1**

Current phase: **P0 — Specification Baseline & Repository Bootstrap**.
Phase state lives in [`PROJECT_STATE.md`](PROJECT_STATE.md) /
[`project_state.json`](project_state.json). Each phase ships on its own branch
and pull request, passes CI, and requires explicit approval before the next
phase begins.

## Repository layout

```
backend/      FastAPI control plane            (P1+)
frontend/     React + vtk.js UI                (P1+)
services/     dispatcher, outbox publisher,
              model service supervisor         (P3+)
ml/           encoders, training, evaluation   (P9+)
infra/        docker-compose, env, ops         (P1+)
scripts/      developer & governance scripts
docs/         specs (locked), templates, governance
tests/        governance + smoke tests
```

## Data & privacy

No restricted datasets, model weights, PHI, or secrets are committed to this
public repository (enforced by `.gitignore` and `tests/test_repo_structure.py`).
CT-RATE, ReXGroundingCT, and BIMCV-R are obtained separately under their own
licenses.

## Development

Requirements are introduced per phase. For the current P0 governance checks:

```bash
# run the local CI mirror (lint, type-check, tests, security, manifest check)
bash scripts/ci_local.sh
```

## License

[MIT](LICENSE) © 2026 Sir7s (Max Qiu)
