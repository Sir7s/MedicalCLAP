# Model Card — 3D Medical CLIP Retrieval (P12)

**Task:** bidirectional CT volume ↔ radiology report retrieval on CT-RATE chest CT.

## Architecture (SPEC-07 §8.2–8.4, unchanged from P11)
- **CT encoder:** PointNet++ set-abstraction over (x, y, z, density) points → 512-d, L2-normalized.
- **Text encoder:** Bio_ClinicalBERT → 512-d projection, L2-normalized.
- **Objective:** symmetric CLIP InfoNCE (bidirectional) + multi-label auxiliary BCE.
- **Selection:** best mean(val CT→text, text→CT Recall@1) across epochs.

## Training pipeline (delivered, validated on real GPU)
`ml/models/train.py` + `data.py` + `train_config.py`: deterministic P9 point-cloud
cache → tokenized reports (P10) → 18-dim CT-RATE labels → AMP training loop →
per-epoch validation → best-checkpoint selection → held-out test → `metrics.json`
+ model card. Resumable (`--resume` from `last.pt`) to survive cloud disconnects.
Refuses silent CPU fallback so a GPU run is never quietly downgraded.

## Local runs (RTX 4050 Laptop, 6 GB, torch 2.11.0+cu128) — HONEST

Held-out test, CT→text. Random baselines (118 test): R@1 ≈ 0.009, R@10 ≈ 0.085.

| Run | Train vols | Test R@1 | Test R@5 | **Test R@10** | mAP | nDCG |
|-----|-----------|----------|----------|---------------|-----|------|
| From-scratch, full fine-tune | 160 | 0.025 | — | — | — | — |
| From-scratch, frozen text | 160 | 0.025 | — | 0.125* | — | — |
| From-scratch, frozen text | 556 | 0.017 | 0.025 | **0.051** | 0.045 | 0.197 |
| **P12a-pretrained, frozen text** | **556** | **0.025** | **0.068** | **0.127** | **0.071** | **0.224** |

\* small-test-size artifact at 160 vols. The 556-volume rows are the reliable comparison.

**Phase 1 (from scratch): at/below random.** Training-set retrieval is near-perfect
(R@5 ≈ 0.98) and the eval path is verified correct (no bug), but held-out is at the
random baseline — from-scratch 556-vol R@10 (0.051) is actually *below* chance
(0.085). Root cause: the PointNet++ CT encoder trains **from scratch** and 556
volumes ≈ 2 % of CT-CLIP's ~25 k; best val epoch = 1 (immediate overfitting).

**Phase 2 — P12a supervised CT-encoder pretraining (AUP-001): first above-random
model.** Pretraining the CT encoder on the 18-dim abnormality labels (train split
only; best pretrain val BCE 0.43) and initializing retrieval from those weights
lifts held-out **R@10 from 0.051 (below random) to 0.127 (1.5× random)**, R@5 from
0.025 to 0.068, mAP from 0.045 to 0.071, and text→CT R@10 from 0.068 to 0.110.

**Decision-gate read (AUP-001 §6).** The lift is real and in the right direction —
the CT encoder *does* learn generalizable features, so the point-cloud
representation is **not** a hard wall. It did not reach the ambitious R@10 ≳ 0.20
target, so this is the best *local* model to date (above random, still modest) but
not yet a strong/deployable retriever. Remaining gap is now data-scale-bound, which
justifies escalating to Option 4 (distill a CT foundation) and/or larger-scale
(cloud) training — both compound with P12a pretraining.

## Cloud training (the usable model) — `ml/notebooks/train_ctrate_colab.ipynb`
Trains the identical pipeline on a larger CT-RATE subset (`TARGET_VOLUMES`,
default 3000, scalable toward the full train set) at 32 768 points. Persistent
Google-Drive point-cloud cache + resumable checkpoints make it robust to Colab
session limits. See `docs/CLOUD_TRAINING.md`. **The cloud-trained checkpoint and
its real held-out metrics are pending the user's run and will be recorded here.**

## Reproducibility
- Config in `ml/models/train_config.py`; per-run manifest in the run's `metrics.json`.
- Deterministic preprocessing (seed 42, P9); point-cloud cache is bit-reproducible.
- Weights are **not** committed to git (H-14); they load into the running app.

## Limitations
- The best local checkpoint (P12a-pretrained) is **above random but still weak**
  (R@10 ≈ 0.127) — usable to wire end-to-end retrieval (P13), not yet a strong
  retriever. Stronger quality needs Option 4 and/or larger-scale training.
- CT-RATE reports are semi-templated; Recall@1 is a harsh single-match metric —
  R@10 / mAP / nDCG are more informative here.
