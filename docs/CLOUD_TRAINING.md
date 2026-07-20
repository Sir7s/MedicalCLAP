# Cloud Training (P12) — CT-RATE Retrieval

Local RTX-4050 runs proved the training pipeline works but cannot produce a
*generalizing* retrieval model: the from-scratch PointNet++ CT encoder needs far
more data than a local subset provides (see `docs/reports/P12_MODEL_CARD.md`).
This guide runs the **same validated code** at scale on a free cloud GPU.

## Notebook
`ml/notebooks/train_ctrate_colab.ipynb` — open it in
[Google Colab](https://colab.research.google.com/) (Kaggle works too; see below).

## What you need (all free)
1. A Google account (Colab + a few GB of Google Drive).
2. A Hugging Face account + **read token** — https://huggingface.co/settings/tokens
3. Accept the CT-RATE terms (one click) —
   https://huggingface.co/datasets/ibrahimhamamci/CT-RATE

## Steps
1. **Runtime → Change runtime type → GPU** (T4 is enough; A100/L4 faster).
2. Run the cells top to bottom. They: check the GPU → install deps → clone this
   repo (branch `phase/P12-training`) → mount Drive → take your HF token →
   build a patient-level split → download the volumes → preprocess to a
   Drive-backed point-cloud cache → train → show metrics → zip the checkpoint.
3. **`TARGET_VOLUMES`** (cell 6) controls scale. Default 3000 (~2000 train). Larger
   → better generalization but longer download/preprocess; raise it toward the full
   ~20 k train set as compute allows.

## Resuming across disconnects
Colab Free sessions time out. Everything is resumable:
- **Point-cloud cache** lives on Drive (`MEDCLIP_CACHE_DIR`); already-cached
  volumes are skipped. Once cached, raw volumes are no longer needed.
- **Training** writes `last.pt` every epoch to the Drive run dir; re-running the
  train cell with `--resume` (already set) continues from the last epoch.

So after a disconnect: reconnect, re-run the setup cells (clone/mount/token/config),
then re-run the download → preprocess → train cells. They pick up where they left off.

## Output → hand back to finalize P12
The run dir on Drive (`runs/p12_cloud/`) and the downloaded zip contain:
- `best.pt` — the val-selected checkpoint (the deployable model).
- `metrics.json` — real held-out test metrics + run manifest.
- `model_card.md` — auto-generated card for this run.

Return `metrics.json` (and keep `best.pt` for the app). P12 is finalized by
recording those real metrics; the checkpoint feeds P13 (Qdrant index + retrieval).
Weights are **never** committed to git (H-14) — they load into the running app.

## Kaggle fallback
Kaggle Notebooks (Settings → Accelerator → GPU T4 ×2) work with minor edits:
- Replace the Google-Drive mount with `/kaggle/working` for `MEDCLIP_CACHE_DIR`
  and the run dir (persisted within a session; commit the notebook to persist
  outputs across sessions, or push the cache to a Kaggle Dataset).
- Add CT-RATE as an input dataset, or keep the HF download cells.
Everything else (clone, split, preprocess, train `--resume`) is identical.
