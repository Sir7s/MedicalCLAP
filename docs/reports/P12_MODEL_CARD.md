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

## Local validation runs (RTX 4050 Laptop, 6 GB, torch 2.11.0+cu128) — HONEST, data-limited

| Run | Train vols | Trainable params | Train R@5 | **Test R@1** | **Test R@10** |
|-----|-----------|------------------|-----------|--------------|---------------|
| Full fine-tune | 160 | 108.9 M | 0.98 | 0.025 | — |
| Frozen backbone | 160 | 589 K | ~0.98 | 0.025 | 0.125 |
| Frozen backbone | 556 (full local subset) | 589 K | high | 0.017 | 0.051 |

**Interpretation.** Training-set retrieval is near-perfect and the eval path is
verified correct (no bug), but **held-out retrieval is at the random baseline**
across all three runs. Root cause is data scale, not a defect: the PointNet++ CT
encoder is trained **from scratch** (no pretrained visual prior) and 556 volumes
is ~2 % of the ~25 k volumes CT-CLIP used. The best validation epoch on the full
local subset was **epoch 1**, i.e. it began overfitting immediately. This matches
the spec's own strategy — local compute is for *subset validation*, real training
is Colab/Kaggle.

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
- Local checkpoints are **not deployable** as retrieval models (at-random on held-out).
- CT-RATE reports are semi-templated; Recall@1 is a harsh single-match metric —
  R@10 / mAP / nDCG are more informative once a real model is trained.
