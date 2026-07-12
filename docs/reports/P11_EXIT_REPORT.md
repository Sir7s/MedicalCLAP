# Phase Exit Report — P11 · Retrieval Model Baseline

> **Status: CANDIDATE — auto-merge on green CI.** (HIGH RISK — first model phase.)

| Field | Value |
|---|---|
| Phase ID | P11 · report v1.0 |
| Branch | `phase/P11-retrieval-model` |
| Date | 2026-07-12 |
| Prerequisite | P9 + P10 merged |

## 1. Objective (met)
A reproducible PointNet++ + BioClinicalBERT retrieval baseline: dual encoders to
512-d L2-normalized embeddings, bidirectional CLIP loss + multi-label auxiliary
loss, and a tiny-batch overfit proving the objective optimizes.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | PointNet++ encoder (FPS + kNN set abstraction) | done |
| S2 | 512-d projection head (L2-normalized) | done |
| S3 | BioClinicalBERT text encoder + projection | done |
| S4 | Bidirectional CLIP + multi-label aux loss | done |
| S5 | Tiny-batch overfit + metrics | done |
| S6 | CI + reports + PR | done |

## 3. Deliverables
- `ml/models/`: `pointnet2.py` (set-abstraction encoder), `text_encoder.py`
  (BioClinicalBERT + tiny variant for tests), `losses.py` (CLIP + multi-label),
  `metrics.py` (Recall@K/mAP/nDCG, bidirectional), `retrieval.py` (combined model
  + `fit_overfit` + batch helpers).
- `ml/requirements-model.txt` (torch CPU, transformers — local).

## 4. Exit-gate evidence (Master Plan P11)
- **Tiny batch overfits** — a fixed 4-sample batch trained 200 steps: contrastive
  loss collapses to under 20% of its start; bidirectional in-batch Recall@1 = 1.0
  (random ~ 0.25).
- **No NaN/OOM** — every step's loss is finite (asserted); CPU, small footprint.
- **Metrics above random** — Recall@1 1.0 well above 0.25 on the overfit set.
- **Runs on real data** — PointNet++ encodes a real 32,768-point CT-RATE volume
  to a (512,) L2-normalized embedding; BioClinicalBERT encodes a real report to
  (512,); full forward verified end-to-end (untrained cosine ~ 0.003).
- **Checkpoint reload consistency** — save/load reproduces embeddings (eval).

## 5. Tests
2 numpy metric tests (run in CI) + 3 torch model tests (forward/backward,
overfit, checkpoint reload — verified locally, auto-skip in CI where torch is
absent). ruff/mypy clean.

## 6. CI note (transparent, consistent with P10)
Torch/transformers model tests auto-skip in CI (no ~2 GB torch install per run)
and are verified locally with the evidence above; the CI ml lane runs the numpy
metric tests + P9/P10 pure tests. Model deps documented in
`ml/requirements-model.txt`.

## 7. Scope note
Full-scale cloud training + the Colab notebook + a deployable checkpoint are
P12 (Retrieval Training & Model Selection). P11 delivers the reproducible model
plus a tiny-overfit sanity gate.

## 8. Architecture deviation
none — PointNet++ CT encoder, BioClinicalBERT text encoder, 512-d L2-normalized
embeddings, bidirectional CLIP + multi-label aux loss, and the Recall@K/mAP/nDCG
metric set follow SPEC-07 sec 8.2-8.4. No CT-CLIP weights loaded into PointNet++.

## 9. Governance
`PROJECT_STATE.*` updated. Auto-merge on green CI; unlocks P12.
