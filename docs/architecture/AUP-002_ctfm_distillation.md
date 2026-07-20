# Architecture Update Proposal — AUP-002

## CT-Foundation Distillation into PointNet++ (new stage P12b)

| Field | Value |
|---|---|
| Proposal ID | AUP-002 |
| Status | **APPROVED** 2026-07-12 (Architecture Update Flow) |
| Date | 2026-07-12 |
| Affects | Adds Master Plan stage **P12b**. No change to the locked Architecture Bundle (v2.4.5) / Master Plan (v1.0); recorded as an approved addendum. |
| Builds on | AUP-001 (P12a) — supervised pretraining lifted held-out R@10 0.051→0.127 |
| Decision | User chose "Option 4" after P12a confirmed the encoder learns transferable features |

---

## 1. Goal
Give the PointNet++ CT encoder a real visual foundation by **distilling features
from a pretrained CT foundation model** (the "teacher") into our encoder (the
"student"), then fine-tuning retrieval from the distilled weights. P12a proved the
encoder responds to a better init; a foundation teacher is the strongest such init.

## 2. Teacher: CT-FM (`surajpaib/CT-FM-SegResNet`)
- **What:** MONAI `SegResNetDS` (~77M params) pretrained by contrastive learning on
  **148k CT scans** (Imaging Data Commons); validated by its authors on whole-body
  segmentation, triage, and **medical image retrieval**.
- **License:** **MIT** — free to use.
- **Why it fits:** large-scale CT visual knowledge, retrieval-proven, small enough to
  run locally, standard deps (PyTorch + MONAI).
- **Not CT-CLIP:** deliberately avoids the CT-CLIP encoder the spec restricts.

## 3. Design (P12b)
**Stage A — teacher feature extraction (one-time, cached, train split only):**
For each train-split volume: load the CT volume, preprocess to CT-FM's expected
input (RAS→SPL orientation, resample, HU-normalize per CT-FM), run the SegResNetDS
**encoder**, global-pool the bottleneck feature map → a teacher embedding `t_v`.
Cache `t_v` to disk (`data/ct_rate/ctfm_cache/<vol>.npy`, a few KB each). After this,
the teacher is no longer needed.

**Stage B — student distillation:**
PointNet++ encodes the point cloud of the same volume → `s_v` (512-d). A small
projection aligns dims. Loss = feature-matching (cosine / MSE on L2-normalized
embeddings), **optionally combined with the P12a multi-label BCE** (multi-objective
pretraining — both signals reuse existing infra). Export the distilled CT-encoder
weights (`encoder.pt`).

**Stage C — retrieval fine-tune:** `train.py --init-ct-encoder <distilled encoder.pt>`
(the exact hook already added in P12a). Everything downstream is unchanged.

## 4. What does NOT change (scope is additive)
Encoders (PointNet++ / Bio_ClinicalBERT), 512-d embeddings, point count, retrieval
objective, and metrics are all unchanged. P12b is a **pretraining stage** that
produces an initialization; it adds no architecture component to the deployed model.
The CT-FM teacher is used **only offline** to produce target features — it is not
part of the retrieval model.

## 5. Compliance
- **CT-CLIP policy** (*"must not load incompatible CT image encoder weights into
  PointNet++"*): honored two ways — (a) the teacher is CT-FM, **not** CT-CLIP;
  (b) we **distill features, never load teacher weights** into PointNet++.
- **License:** CT-FM is MIT. **H-13/H-14:** no PHI/weights committed; teacher weights
  and feature cache are git-ignored (they load/generate at runtime).
- **Leakage:** teacher features + distillation use the **train split only**.

## 6. New dependency & feasibility risks (honest)
- **MONAI** becomes a local-only dep (like torch/transformers — NOT added to the CI
  ml lane). Must confirm it installs on Python 3.14; if not, run teacher extraction
  in a small separate env / on CPU (it is a one-time offline pass).
- **Teacher VRAM:** SegResNetDS on a full CT may exceed 6 GB. Mitigation: extract at
  reduced resolution and/or on **CPU** — it is one-time and cached, so slowness is
  acceptable and **stays local** (no cloud).
- **Feature hook:** need to tap the SegResNetDS encoder bottleneck (forward hook or
  encoder submodule) rather than the segmentation head — a small implementation task.
- If any blocker proves hard, we fall back to P12a's result (already merged-ready).

## 7. Decision gate
Compare `P12b-distilled → retrieval` held-out test to P12a (R@10 0.127) and
from-scratch (0.051):
- **Meaningful lift over P12a** (e.g. CT→text **R@10 ≳ 0.20**) → distillation works;
  adopt the distilled encoder as P12's deployment candidate.
- **≈ P12a / no lift** → the point-cloud representation is capping transfer; do not
  chase further, adopt the better of P12a/P12b and either proceed to P13 or open the
  representation question (a separate, larger Architecture Update).

## 8. Governance on approval
No locked-doc version change (additive stage). Record
`docs/architecture/AUP-002_ctfm_distillation.md` in `approved_architecture_addenda`;
set `current_subphase: "P12b"`. Implement on `phase/P12-training`; green CI; run
locally; record real metrics in `docs/reports/P12_MODEL_CARD.md` against §7.

## 9. Approval requested
Approve: (a) stage **P12b** distillation, (b) **CT-FM (MIT)** as the teacher,
(c) train-split-only + feature-cache design, (d) MONAI as a local-only dep with the
§6 fallbacks, (e) the §7 decision gate. On approval I implement and run.
