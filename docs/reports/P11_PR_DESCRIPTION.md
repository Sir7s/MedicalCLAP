# Phase P11 — Retrieval Model Baseline

PointNet++ CT encoder + BioClinicalBERT text encoder to 512-d L2-normalized
embeddings, bidirectional CLIP loss + multi-label aux loss, with a tiny-batch
overfit sanity gate. First model phase (torch, CPU).

## Exit-gate evidence
- Tiny 4-sample batch overfits in 200 steps: contrastive loss under 20% of
  start; bidirectional in-batch Recall@1 = 1.0 (random 0.25); all losses finite.
- Runs on real data: real 32,768-pt CT-RATE volume to PointNet++ (512-d); real
  report to BioClinicalBERT (512-d); full forward verified end-to-end.
- Checkpoint save/reload reproduces embeddings.

## Test summary
2 numpy metric tests (CI) + 3 torch model tests (forward/backward, overfit,
checkpoint reload — verified locally, auto-skip in CI). ruff/mypy clean.

## CI note
Torch/transformers model tests auto-skip in CI (avoid ~2 GB install/run);
verified locally. CI ml lane runs numpy metric tests + P9/P10 pure tests. Model
deps in `ml/requirements-model.txt`.

## Change log
- `ml/models/` (pointnet2, text_encoder, losses, metrics, retrieval).
- `ml/requirements-model.txt` (torch, transformers).
- Tests: `tests/ml/test_model.py`.

## Scope
Full cloud training + Colab notebook + deployable checkpoint = P12.

## Approval
Auto-merge on green CI. Unlocks P12 — Retrieval Training & Model Selection.
