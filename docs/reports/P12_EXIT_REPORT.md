# Phase Exit Report — P12 · Retrieval Training & Model Selection

> **Status: PIPELINE DELIVERED — cloud checkpoint PENDING (do not merge until real
> cloud metrics are recorded).** User decision: train on cloud (Colab/Kaggle).

| Field | Value |
|---|---|
| Phase ID | P12 · report v1.0 |
| Branch | `phase/P12-training` |
| Date | 2026-07-12 |
| Prerequisite | P11 merged |

## 1. Objective
Train the P11 retrieval model on real CT-RATE data, select the best checkpoint by
held-out validation, and report bidirectional Recall@K / mAP / nDCG. Produce a
reproducible, resumable training system and a deployment-candidate checkpoint.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Frozen training config (reproducibility) | done |
| S2 | Dataset: point-cloud cache + tokenized reports + 18-dim labels | done |
| S3 | GPU training loop (AMP, best-val selection, held-out test, model card) | done |
| S4 | Real GPU training + honest metrics (local) | done — data-limited (see §4) |
| S5 | Resumable checkpointing + cloud (Colab/Kaggle) training notebook | done |
| S6 | Cloud training run → real checkpoint + metrics | **PENDING (user runs)** |

## 3. Deliverables
- `ml/models/train_config.py` — frozen `TrainConfig` (data/opt/runtime), scalable via CLI.
- `ml/models/data.py` — point-cloud cache (env-configurable roots for cloud),
  report pairing, CT-RATE label loading, torch dataset + collate.
- `ml/models/train.py` — AMP training loop, best-val checkpoint selection,
  held-out test eval, auto model card, **resumable** (`--resume` from `last.pt`),
  CLI scaling knobs (`--n-train/--points/--batch/--epochs/--no-freeze`), refuses
  silent CPU fallback.
- `ml/notebooks/train_ctrate_colab.ipynb` — end-to-end cloud training on a larger
  CT-RATE subset, reusing the exact validated code. `docs/CLOUD_TRAINING.md`.
- `tests/ml/test_train.py` — full-loop smoke + resume tests (torch; auto-skip in CI).
- `docs/reports/P12_MODEL_CARD.md` — committed model card (local baseline + cloud path).

## 4. Local training evidence (real GPU, HONEST — data-limited)
RTX 4050 Laptop (6 GB), torch 2.11.0+cu128, CUDA 12.8. Three runs:

| Run | Train vols | Params trained | Train R@5 | Test R@1 | Test R@10 |
|-----|-----------|----------------|-----------|----------|-----------|
| Full fine-tune | 160 | 108.9 M | 0.98 | 0.025 | — |
| Frozen backbone | 160 | 589 K | ~0.98 | 0.025 | 0.125 |
| Frozen backbone | 556 (full local) | 589 K | high | 0.017 | 0.051 |

- **Pipeline validated:** the model demonstrably learns (memorizes train,
  R@5 ≈ 0.98); eval path proven correct (train-set retrieval strong in eval mode —
  no BatchNorm/eval bug); AMP + checkpointing + selection all work.
- **Held-out at random:** across the full local data budget the model does not
  generalize (test at/below the random baseline; best val epoch = 1). **Not a bug —
  a data-scale limit.** The PointNet++ CT encoder trains from scratch and 556
  volumes ≈ 2 % of CT-CLIP's ~25 k. Matches the spec (local = validate subsets;
  real training = Colab/Kaggle).

## 5. Exit-gate status (Master Plan P12)
- Training/selection/metrics **pipeline**: MET (real GPU, reproducible, resumable).
- **Generalizing checkpoint + real held-out metrics**: **NOT YET MET** — requires
  the cloud run. This report is **not** a completion claim; P12 is finalized once
  the cloud `metrics.json` is recorded and (if it clears the retrieval bar) merged.

## 6. Decision log
Local training conclusively data-limited (3 runs). Presented to user as a
resource fork (accept-local vs cloud vs keep-local). **User chose: run cloud
training now** — deliver the notebook, user runs it, returns the checkpoint
before we proceed to P13.

## 7. Tests / CI
`tests/ml/test_train.py` (smoke + resume) join the P11 torch tests: verified
locally, auto-skip in CI where torch is absent (consistent with P10/P11). numpy
metric tests still run in CI. ruff + mypy clean. No new CI-audited dependencies.

## 8. Architecture deviation
none — encoders, 512-d embeddings, bidirectional CLIP + multi-label aux, and the
metric set are unchanged from SPEC-07. Freezing the text backbone is a training
strategy (regularization), not an architecture change; the spec already uses
encoder-freezing for the segmentation head.

## 9. Governance
No weights/PHI committed (H-13/H-14): `runs/` git-ignored; checkpoints load into
the app. `PROJECT_STATE.*` updated. **Hold merge** until cloud metrics are in.
