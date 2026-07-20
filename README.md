# 3D Medical CLIP

> Local 3D chest-CT ↔ radiology-report retrieval with **findings-grounded,
> explainable re-ranking** — every result tells you *which clinical findings* it
> shares with your query.

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
between a 3D chest CT and free-text radiology reports, served on a single 6 GB
laptop GPU.

| Capability | Summary |
|---|---|
| Retrieval (primary) | CT→Report and Report→CT over CT-RATE; **CT-CLIP** recall (512-d cosine, Qdrant ANN) evaluated with Recall@K, mAP and nDCG on a leakage-free held-out split |
| **Explainable re-ranking** | The recalled pool is re-scored by clinical-findings overlap and each hit is explained by the findings it *shares* with the query — the project's original contribution |
| Viewer | Upload a single chest CT (NIfTI); 3 orthogonal views, WW/WL, basic volume rendering, polygon annotation |
| Bilingual UX | Chinese/English UI; Chinese text locally translated to English before retrieval; English voice input (local Whisper) |
| History & export | Full search history with JSON + CSV export |

### How the re-ranking works

Retrieval runs in two stages. CT-CLIP recalls a candidate pool by embedding
similarity; the re-ranker then blends that score with clinical-findings agreement:

```
score = α · recall_similarity  +  (1 − α) · findings_match
```

Two invariants make it trustworthy, and both are tested:

- **It permutes, never drops.** Re-ranking can only reorder the recalled pool, so it
  can never lower the recall ceiling — and `α = 1.0` reproduces pure recall ordering.
- **Explanations are grounded.** A hit is only ever explained by findings that *both*
  the query and that hit express. The system cannot invent a justification.

Explanations are also effectively free: **~0.2 ms** to re-rank and explain a
50-candidate pool.

### Results

| Metric | Value |
|---|---|
| Held-out CT→text **R@10** | **0.511** (90 CT-RATE `valid` volumes, leakage-free) |
| Re-rank + explain latency (top-50) | p50 **0.19 ms** |
| Inference VRAM ceiling | **2.25 GB** — runs on a 6 GB laptop GPU |

Full numbers: [`docs/reports/P12_MODEL_SELECTION.md`](docs/reports/P12_MODEL_SELECTION.md)
and [`docs/reports/P19_PERFORMANCE.md`](docs/reports/P19_PERFORMANCE.md).

> **On the encoder.** A from-scratch PointNet++ point-cloud encoder was built and
> evaluated first, across five documented approaches including CT-FM distillation and
> augmentation. None generalised beyond ~1.5× random at locally achievable data scale;
> the best reached R@10 0.153 against CT-CLIP's 0.511. That work is kept as documented
> research under `ml/`, and the pivot to a pretrained foundation encoder is recorded in
> [AUP-005](docs/architecture/AUP-005_architecture_pivot_and_scope.md). Negative results
> are reported, not buried.

## Tech stack

Frontend: React + Vite (bilingual, dark clinical UI) · Backend: FastAPI control plane ·
PostgreSQL (durable truth) · Redis (queue/stream/cache) · Qdrant (vector index) ·
CT-CLIP GPU inference service · Docker Compose (reproducible local deployment).

## Status & governance

This project is executed as a strict, phased program. The authoritative sources
are version-locked under [`docs/specs/`](docs/specs/) and pinned by
[`SPEC_MANIFEST.json`](docs/specs/SPEC_MANIFEST.json):

- Architecture Specification Bundle **v2.4.5** (`final_freeze_candidate`)
- Master Phased AI Execution Plan **v1.0**
- Implementation Appendix **v1.1**
- Freeze Test Profile **v1.1**

Architecture changes went through a formal Architecture Update Flow; the five
proposals are under [`docs/architecture/`](docs/architecture/).

**Status: complete — the freeze run passed on 2026-07-21.** All phases P0–P20 shipped
on their own branch and pull request with green CI. The freeze evidence, clause by
clause, is in [`docs/reports/P20_FREEZE_RUN.md`](docs/reports/P20_FREEZE_RUN.md),
against the profile as amended by
[`FREEZE_TEST_PROFILE_AMENDMENT.md`](docs/specs/FREEZE_TEST_PROFILE_AMENDMENT.md).
Phase state lives in [`PROJECT_STATE.md`](PROJECT_STATE.md) /
[`project_state.json`](project_state.json).

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
CT-RATE and any other datasets are obtained separately under their own licenses.
CT-RATE is de-identified public research data; the application is single-user and
local-first, and all services bind to `127.0.0.1`. See [SECURITY.md](SECURITY.md).

## Development

```bash
# 1. datastores (Postgres, Redis, Qdrant)
docker compose -f infra/docker-compose.yml up -d

# 2. backend control plane
cd backend && uvicorn app.main:app --reload

# 3. CT-CLIP inference service (needs a GPU + the checkpoint, see below)
python ml/serving/ctclip_service.py

# 4. frontend
cd frontend && npm install && npm run dev
```

The CT-CLIP checkpoint (~1.7 GB) is **not** redistributed here — download it from
upstream under its own CC-BY-NC-SA licence. Retrieval returns **503** when the
inference service is unavailable; it never degrades silently or invents results.

```bash
# run the local CI mirror (lint, type-check, tests, security, manifest check)
bash scripts/ci_local.sh
```

## License

The **source code in this repository** is [MIT](LICENSE) © 2026 Sir7s (Max Qiu).

> ### ⚠️ The deployed system is non-commercial
> The retrieval stack depends on **CT-CLIP** and **CT-RATE**, both licensed
> **CC-BY-NC-SA 4.0**. Running this system with those components is therefore
> **non-commercial only**, requires **attribution**, and obliges derivatives to be
> shared under compatible terms.
>
> The MIT licence covers *our code only* — it cannot and does not grant commercial
> rights over third-party models or data. For commercial use you must obtain
> permission from the upstream owners or substitute those components.

Full attribution and per-component licences: **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**.
No third-party weights or datasets are redistributed here; they are downloaded by
the user at setup time.
