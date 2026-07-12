# P12 · Retrieval Training & Model Selection (pipeline + cloud path)

Trains the P11 PointNet++/Bio_ClinicalBERT retrieval model on real CT-RATE data,
selects the best checkpoint by held-out validation, and reports bidirectional
Recall@K / mAP / nDCG. Delivers a reproducible, **resumable** training system and
a cloud (Colab/Kaggle) notebook for full-scale training.

## What's here
- **Training pipeline** — `ml/models/{train_config,data,train}.py`: point-cloud
  cache (env-configurable roots), report+label pairing, AMP loop, best-val
  selection, held-out test, auto model card, `--resume`, CLI scaling knobs.
- **Cloud notebook** — `ml/notebooks/train_ctrate_colab.ipynb` +
  `docs/CLOUD_TRAINING.md`: end-to-end CT-RATE training on a larger subset,
  Drive-cached + resumable, reusing the exact validated code.
- **Tests** — `tests/ml/test_train.py` (full-loop smoke + resume; torch, auto-skip in CI).
- **Docs** — `docs/reports/P12_{EXIT_REPORT,CONFORMANCE_REPORT,MODEL_CARD}.md`.

## Real GPU validation (RTX 4050, torch 2.11.0+cu128) — honest, data-limited
Model learns (train R@5 ≈ 0.98, eval path proven correct) but held-out retrieval
is at random across the full local data budget (556 volumes; best val epoch = 1).
Root cause is data scale — the from-scratch PointNet++ needs ≫ 556 volumes — not a
bug. Hence the cloud path.

## Status — DO NOT MERGE yet
Per the user's decision (run cloud training now), this PR is open so the notebook
can clone the branch and CI can run. **Finalize + merge only after the cloud run
returns real held-out metrics** (recorded into `P12_MODEL_CARD.md`). Weights are
never committed (H-14). Unblocks P13 (Qdrant index + retrieval) with the
cloud-trained checkpoint.

## CI
Green expected: torch model/train tests auto-skip (consistent with P10/P11);
numpy metric tests run; ruff + mypy clean; no new CI-audited deps.
