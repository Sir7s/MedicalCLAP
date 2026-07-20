# Phase Exit Report — P12 · Retrieval Training & Model Selection

> **Status: COMPLETE — deployable retriever achieved via AUP-005 pivot.**

| Field | Value |
|---|---|
| Phase ID | P12 · report v2.0 |
| Branch | `phase/P12-training` (PR #13) |
| Date | 2026-07-21 |
| Prerequisite | P11 merged |
| Addenda | AUP-001, AUP-002, AUP-004, AUP-005 (all approved) |

## 1. Objective vs outcome
**Objective:** train the retrieval model on real CT-RATE data, select a checkpoint by
held-out validation, report bidirectional Recall@K/mAP/nDCG, and produce a deployment
candidate.

**Outcome:** achieved — but **not** with the originally mandated encoder. The
from-scratch PointNet++ encoder could not clear the random baseline at any locally
achievable data scale; a working retriever was obtained by adopting **CT-CLIP for
recall** and adding an **original findings-grounded explainable re-ranking layer**
(AUP-005). Held-out **R@10 = 0.511** (≈4.6× random, ≈4× the best local model).

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Frozen training config | done |
| S2 | Dataset (point-cloud cache + reports + labels) | done |
| S3 | GPU training loop (AMP, selection, held-out test, model card) | done |
| S4 | Real GPU training + honest metrics | done — at random (documented) |
| S5 | P12a supervised CT-encoder pretraining (AUP-001) | done — first above-random (R@10 0.127) |
| S6 | P12b CT-FM distillation (AUP-002) | done — no gain (0.144) |
| S7 | Augmentation + negative queue + multi-positive | done — no gain on strong base |
| S8 | Data scaling to 3,003 volumes (stream-and-cache) | done — no gain |
| S9 | P12d findings classifier + explainable re-ranker (AUP-004) | done |
| S10 | CT-CLIP integration + held-out evaluation (AUP-005) | done — **deployable** |

## 3. Deliverables
- **Training system:** `ml/models/{train_config,data,train,pretrain,distill,train_aug}.py`
  — AMP, resumable, best-val selection, auto model card, CLI scaling knobs.
- **Data scaling:** `ml/models/scale_acquire.py` — stream-and-cache (download →
  preprocess → delete raw; ~150 KB/volume survives), concurrent + resumable.
- **Deployed retrieval:** CT-CLIP recall + `ml/models/rerank.py` (findings-grounded
  re-rank + explanations) + `ml/models/findings.py` (18-abnormality classifier).
- **Diagnostics:** `ml/models/ctfm_baseline.py` (foundation baseline = the bar to beat).
- **Cloud path:** `ml/notebooks/train_ctrate_colab.ipynb` + `docs/CLOUD_TRAINING.md`.
- **Model card:** `docs/reports/P12_MODEL_CARD.md` (all numbers, honest).

## 4. Exit-gate evidence
- **Real GPU training on real data** — RTX 4050, torch 2.11.0+cu128, verified.
- **Held-out, leakage-free evaluation** — CT-RATE `valid` split (CT-CLIP did not
  train on it); 90 volumes.
- **Deployment candidate** — CT-CLIP recall R@10 **0.511**; + re-rank **0.522**
  (CT→text) / **0.533** (text→CT). Bidirectional, with mAP and nDCG reported.
- **Model selection** — per-epoch validation selection throughout; α swept for the
  re-ranker with the degradation region documented.
- **Reproducible** — seeded configs, per-run manifests, deterministic preprocessing.

## 5. Honest negative result (retained, not hidden)
Five approaches to the mandated from-scratch encoder — baseline, label-pretraining,
CT-FM distillation, augmentation+queue, and 4× data scaling — all plateaued at
**1.0–1.5× random**. A CT-FM frozen-feature baseline reached only 0.153, showing the
limit was not our representation alone but data scale (CT-CLIP: ~25k volumes;
MedP-CLIP: 6.4M images). This is documented in the model card and AUP-005.

## 6. Architecture deviation
**Yes — formalized in AUP-005.** Deployed encoder is CT-CLIP, not PointNet++. The
point-cloud pipeline is reclassified as documented research and removed from the
serving path. P16 (segmentation) dropped in the same amendment. The Freeze Test
Profile must be restated before P20 (AUP-005 §5).

## 7. Tests / CI
`tests/ml/`: metrics, model forward/overfit/checkpoint (P11), training smoke +
resume, pretraining smoke, distillation smoke, re-rank math (CI-safe numpy).
Heavy torch tests auto-skip in CI and are verified locally. ruff + mypy clean.

## 8. Governance
No weights/PHI committed (H-13/H-14) — `runs/` git-ignored; CT-CLIP checkpoint and
caches live outside the repo. New obligation: **CC-BY-NC-SA** (non-commercial,
attribution, share-alike) enforced in P17. `PROJECT_STATE.*` updated.
Unlocks **P13** — Qdrant Index & Real Retrieval Integration.
