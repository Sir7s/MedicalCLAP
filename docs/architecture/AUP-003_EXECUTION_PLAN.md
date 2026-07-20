# AUP-003 — Detailed Execution Runbook

Step-by-step plan to distill CT-CLIP (report-aligned teacher) into the PointNet++
point-cloud encoder. Each step lists the action, what it produces, how it's
verified, and its cost. **Gates** are hard stop/go points.

Legend: 🟢 = committable checkpoint (green CI) · ⏱ = rough cost · ⚠ = risk.

---

## Phase 0 — Feasibility & governance (no big download yet)

**0.1 Locate CT-CLIP + license.**
- Fetch the CT-CLIP HuggingFace + GitHub pages; record the model repo id, the
  checkpoint filenames (image encoder / text encoder), and the **license**.
- Verify: license permits research/derivative use (MIT / CC-BY / Apache). Record the exact text.
- ⚠ **GATE 0a:** if the license forbids this use → STOP, report, fall back to the 2D-foundation route.
- ⏱ ~10 min.

**0.2 Get CT-CLIP's model + preprocessing code.**
- Clone/inspect their repo: the CT-ViT image-encoder class, the text encoder, weight-loading,
  and their **exact preprocessing** (HU window, target voxel grid, spacing).
- Output: notes on how to instantiate the model and turn a NIfTI into its input tensor.
- ⏱ ~30 min.

**0.3 Stand up a runtime for CT-CLIP.**
- ⚠ CT-CLIP's code (2024) may not support Python 3.14. Mitigation: create an isolated
  **Python 3.11 venv** (`infra/venv_ctclip`) just for CT-CLIP *inference*. Teacher embeddings are
  cached as plain `.npy`, so distillation still runs in our 3.14 env — the versions are decoupled.
- Install their pinned deps + torch (CUDA if it fits, else CPU).
- Verify: `import` their model class succeeds.
- ⏱ ~30–45 min.

**0.4 Load weights + one-volume smoke.**
- Download the image + text encoder checkpoints.
- Run the image encoder on ONE real CT-RATE volume (their preprocessing) → image embedding;
  run the text encoder on its report → text embedding. Print dims + cosine(img, txt).
- Verify: forward succeeds, embeddings finite, dims recorded; **measure peak VRAM**.
- ⚠ **GATE 0b:** if it won't run on the 6 GB GPU *and* CPU inference is impractically slow →
  STOP, report options (cloud extraction vs 2D route).
- ⏱ ~30 min (+ checkpoint download, size TBD).

**0.5 Governance.** Mark AUP-003 **approved**; add to `approved_architecture_addenda`;
`current_subphase = "P12c"`. 🟢 commit (docs/state only).

---

## Phase 1 — Honest, leakage-free evaluation set

**1.1 Identify CT-RATE's official validation split.**
- CT-CLIP trained on `train`; the `valid` split is its held-out eval. Our volumes are all from
  `train` → evaluating CT-CLIP on our split is train-on-test. So we need `valid`.
- Fetch `dataset/radiology_text_reports/validation_reports.csv` and
  `dataset/multi_abnormality_labels/valid_predicted_labels.csv` from HF.
- ⏱ ~10 min.

**1.2 Teach the tooling about `valid_fixed`.**
- `select.py`/`acquire.py` currently hardcode `train_fixed`. Add a `variant` param so
  `volume_repo_path`/downloader can target `dataset/valid_fixed/...`.
- Build a held-out list of ~500–1000 validation volumes (patient-level, seeded).
- 🟢 commit (tooling + tests). ⏱ ~1 h.

**1.3 Stream-and-cache the held-out volumes.**
- Reuse `scale_acquire` (valid variant): download → point-cloud cache → delete raw.
- Output: point clouds for the held-out set. ⏱ ~2–4 h (download-bound; unattended, resumable).

---

## Phase 2 — Teacher embedding extraction

**2.1 `ml/models/ctclip_teacher.py`** (mirrors `ctfm_teacher.py`).
- Lazy-load CT-CLIP (in the 3.11 venv via subprocess, or same env if 3.14 works); preprocess a
  volume per CT-CLIP's spec; return its image embedding. Cache to `data/ct_rate/ctclip_cache/` (git-ignored).
- Also a function to embed report text with CT-CLIP's text tower.
- 🟢 commit (module + smoke test that skips without weights). ⏱ ~2 h.

**2.2 Extract teacher embeddings.**
- ⚠ **We deleted the train raws during stream-and-cache** (kept only point clouds + CT-FM). CT-CLIP
  needs voxels, so this step **re-downloads** each raw: stream download → CT-CLIP embed → cache → delete.
- Run over: the ~2,112 train volumes (distillation targets) + the held-out valid volumes.
- Output: `ctclip_cache/<vol>.npy` (image emb) for all; report text embeddings cached too.
- ⏱ **the big cost** — re-download (~2,600 vols) + CT-CLIP inference each. Est. ~half a day,
  unattended/resumable. (If GPU too small, CT-CLIP runs on CPU here — slower but one-time.)

---

## Phase 3 — Distillation training

**3.1 `ml/models/ctclip_distill.py`** (extends `distill.py`).
- Dataset per train volume: `(point_cloud, ctclip_img_emb, report_ctclip_txt_emb, label)`.
- Student: PointNet++ (init from `runs/p12a_scaled/encoder.pt`) → projection into CT-CLIP's joint dim.
- Loss: `cosine + MSE` to the teacher image embedding (primary) `+ λ·contrastive` to the teacher
  text embedding `+ γ·label-BCE`. Train-split only; val slice for selection. Resumable, AMP, 6 GB.
- 🟢 commit (module + smoke test). ⏱ ~2 h build.

**3.2 Run distillation.** ⏱ ~1–2 h GPU (local).

---

## Phase 4 — Retrieval evaluation + decision gate

**4.1 Evaluate the distilled student** on the Phase-1 held-out set: encode point clouds → project →
retrieve against CT-CLIP **text** embeddings of the held-out reports. Report R@1/5/10, mAP, nDCG,
both directions. Also content-aware R@K (dedupe identical reports).

**4.2 Reference numbers on the same held-out set:** CT-CLIP teacher's own retrieval (the ceiling),
our 0.15 plateau, random floor.

**4.3 ⚠ GATE 4 (decision):**
- **Success** → held-out R@10 clearly beats 0.15 (target ≳ 0.30) **and** ≥ ~50 % of the teacher's R@10.
  The distilled point-cloud encoder becomes P12's deployment candidate — an original, efficient,
  working CT↔report retriever.
- **Partial** → above plateau but < 50 % of teacher: ship as best-available, note the gap.
- **Failure** → still ~plateau: decisive proof the point-cloud representation caps quality. Then
  choose (a) adopt CT-CLIP directly (bigger pivot), or (b) accept the modest model + build the platform.

---

## Phase 5 — Finalize

**5.1** Write model card (student vs teacher, held-out metrics), `metrics.json`, AUP-003 conformance
report, P12 exit report; update `PROJECT_STATE.*`. No weights committed (H-14).
**5.2** Green CI; update PR #13. 🟢
**5.3** Hand the distilled encoder to **P13** (Qdrant index + real retrieval integration).

---

## Cost & risk summary
| Item | Cost | Risk / mitigation |
|---|---|---|
| CT-CLIP license | — | GATE 0a; abort if incompatible |
| Py 3.14 incompatibility | ~45 min | isolated 3.11 venv for inference; caches decouple it |
| 6 GB VRAM for CT-CLIP | — | GATE 0b; CPU fallback for one-time extraction |
| Re-download raws (deleted) | ~half day | stream download→embed→delete; unattended/resumable |
| Distillation still plateaus | ~2 h | GATE 4 makes even failure decisive |

**Total wall-clock:** ~1–1.5 days, almost all unattended (downloads + extraction), with ~1 day of
my build/eval work interleaved. Every heavy step is resumable.
