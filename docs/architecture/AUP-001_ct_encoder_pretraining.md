# Architecture Update Proposal — AUP-001

## Supervised CT-Encoder Pretraining (new stage P12a)

| Field | Value |
|---|---|
| Proposal ID | AUP-001 |
| Status | **APPROVED** 2026-07-12 (Architecture Update Flow) |
| Date | 2026-07-12 |
| Affects | Adds Master Plan stage **P12a**. **No change** to the locked Architecture Bundle (v2.4.5) or Master Plan (v1.0) documents — recorded as an approved addendum (see §7). |
| Trigger | P12 finding: the CT encoder cold-starts and cannot generalize |
| Prereq | Architecture is `final_freeze_candidate` (not frozen) — change permitted via this flow |

---

## 1. Problem (evidence-based)
P12 trained the retrieval model on real CT-RATE data across three runs up to the
full local subset (556 train / 118 test). Result: the model **memorizes training
pairs (train R@5 ≈ 0.98) but generalizes at ~random on held-out data** (test
CT→text R@1 = 0.017, R@10 = 0.051; random R@10 = 0.085; best val epoch = 1).

Root cause: the **PointNet++ CT encoder is randomly initialized and learns "how to
see a chest CT" from scratch**, using only the contrastive signal of a few hundred
CT↔report pairs. The text encoder is a pretrained foundation (Bio_ClinicalBERT);
the image encoder has no such foundation. That asymmetry is the wall.

## 2. Proposed change
Insert a **supervised pretraining stage, P12a**, *before* retrieval fine-tuning:

1. Train PointNet++ + a linear multi-label head on the **18-dim CT-RATE
   multi-abnormality labels** we already have, over the **train-split volumes only**.
2. Save the pretrained encoder weights.
3. Initialize the P12 retrieval model's CT encoder from those weights, then run the
   existing retrieval training (unchanged) as fine-tuning.

This gives the CT encoder a warm start on a clinically-relevant task instead of a
cold start, directly attacking the cause in §1.

## 3. What does NOT change (scope is additive)
- **Encoders:** PointNet++ (image) + Bio_ClinicalBERT (text) — unchanged.
- **Embedding dim** 512, **point count**, **retrieval objective** (bidirectional
  CLIP + multi-label aux), **metric set** (Recall@K / mAP / nDCG) — all unchanged.
- No new external model, no downloaded weights. P12a is a **training stage + a
  pretraining objective**, not a new architecture component.

## 4. Compliance
- **CT-CLIP weights policy** (*"must not load incompatible CT image encoder weights
  into PointNet++"*): honored — the encoder is trained on **our own** point clouds
  and labels; nothing external is loaded.
- **SPEC-07 §8.4** already sanctions the 18-dim multi-abnormality labels as the
  auxiliary loss; P12a promotes that same signal to a dedicated warm-start stage.
- **H-13 / H-14:** no PHI, no weights committed (`runs/` git-ignored).
- **Leakage:** pretraining uses **train-split patients only** (val/test excluded),
  so held-out retrieval evaluation stays clean.

## 5. Recipe (for the implementation, post-approval)
- Loss: multi-label BCE-with-logits on the 18 classes.
- Optimizer AdamW, seed 42, AMP, RTX 4050; points per current config; ~30–60 epochs
  with best-by-val-mAP selection.
- Output: `encoder.pt` (CT-encoder state only). Retrieval training gains a
  `--init-ct-encoder <path>` option to load it; everything else identical.
- Fully local; no cloud dependency.

## 6. Decision gate (why this stage is also a diagnostic)
After `P12a pretrain → retrieval fine-tune`, compare held-out test to the
from-scratch baseline (R@1 = 0.017, R@10 = 0.051):

- **Clear lift** (e.g. test CT→text **R@10 ≳ 0.20**, ~2.5× random, and mean R@1
  ≳ 0.03, several× random) → the encoder *can* learn generalizable features;
  proceed, and Option 4 (distill a CT foundation) becomes a justified next escalation.
- **≈ random / unchanged** → the **point-cloud representation itself is the wall**;
  do not sink effort into Option 4 — reopen the image-representation question
  (voxel encoder) as a separate, larger Architecture Update.

Either outcome is decision-useful; this is the cheapest way to learn which wall we hit.

## 7. Governance actions on approval
The locked spec bundle is **not** modified: P12a adds no architecture-bundle
content (encoders, dims, objective, metrics are unchanged), so `architecture_version`
stays **2.4.5** and `master_plan_version` stays **1.0** — both remain consistent
with their hash-locked PDFs (`test_doc_integrity`). AUP-001 is instead recorded as
an **approved addendum**:
1. `project_state.json`: add `approved_architecture_addenda: ["docs/architecture/AUP-001_ct_encoder_pretraining.md"]`;
   set `current_subphase: "P12a"`; note P12 finalization depends on the
   P12a-initialized retrieval run. `PROJECT_STATE.md` mirrors this.
2. Implement per §5 on the current `phase/P12-training` branch; green CI; then the
   local pretrain→retrain run + honest metrics against the §6 gate.
3. The cloud path (PR #13 notebook) remains available as the scale lever /
   Option-4 host; it is not removed.

## 8. Approval requested
Approve: (a) adding stage **P12a** as described, (b) **train-split-only**
pretraining to prevent leakage, (c) the **decision gate** in §6, and (d) the
architecture addendum → **v2.5.0**. On approval I update the Master Plan/state and
implement.
