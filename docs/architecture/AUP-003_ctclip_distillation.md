# Architecture Update Proposal — AUP-003

## Report-aligned distillation: CT-CLIP → PointNet++ point-cloud encoder

| Field | Value |
|---|---|
| Proposal ID | AUP-003 |
| Status | **DRAFT — awaiting user approval** (Architecture Update Flow, step 1) |
| Date | 2026-07-15 |
| Affects | Adds a teacher + eval protocol to stage **P12b/P12c**. No change to the locked bundle (PointNet++ stays the deployed encoder); recorded as an approved addendum. Extends AUP-002. |
| Trigger | All from-scratch/self-supervised local approaches plateau at ~1.0–1.5× random; a *report-aligned* teacher is the missing ingredient. |

---

## 1. Idea in one sentence
Keep our **original point-cloud CT encoder** as the contribution, but teach it with a
**report-aligned foundation model (CT-CLIP)** instead of learning from scratch — producing
*"an efficient point-cloud 3D-CT retriever that inherits voxel-ViT quality at a fraction of
the compute."*

## 2. Why this, why now
- Five local attempts (from-scratch, P12a label-pretrain, P12b CT-FM distill, augmentation,
  tuned-scale) all stall near random. Root cause: the encoder never acquires *report-relevant*
  visual knowledge from a few thousand pairs.
- P12b distilled **CT-FM**, which is self-supervised and **not** report-aligned — so the target
  carried no retrieval signal. **CT-CLIP's image embeddings *are* aligned to reports** (it was
  contrastively trained on CT-RATE), so matching them transfers the retrieval signal directly.
- Distillation gives **dense supervision** (a rich 512-d target per volume) — the data-efficient
  remedy for small data.

## 3. Originality & compliance
- **Original:** point-cloud CT-report retrieval is novel (the field uses heavy voxel ViTs). The
  contribution is the efficient representation + the distillation recipe — ours.
- **Compliant:** we match CT-CLIP's *outputs* (distillation); we do **not** load CT-CLIP weights
  into PointNet++. This is the exact mechanism AUP-002 already approved — only the teacher changes
  (CT-CLIP instead of CT-FM). PointNet++ remains the deployed encoder (spec mandate intact).
- **Licensing gate:** CT-CLIP must be released under a license that permits this use (verified in
  Phase 0 before any download).

## 4. Phased execution plan

### Phase 0 — Feasibility & governance (de-risk before committing)
- Locate CT-CLIP release (HF/GitHub); confirm **license** permits research use.
- Download the CT-CLIP **image encoder + text encoder** weights.
- Verify it **runs on the RTX 4050 (6 GB)** for *inference*: measure VRAM at batch 1; if it
  doesn't fit, fall back to CPU inference for the one-time embedding extraction (slow but fine) or
  reduced precision / patch-wise.
- Record CT-CLIP's embedding dims + joint space.
- **Gate:** if license or execution is infeasible, stop and report. Else finalize AUP-003 (approved
  addendum, no locked-bundle change), set subphase P12c.

### Phase 1 — Honest evaluation target (avoid leakage)
- CT-CLIP was trained on CT-RATE **train**; our volumes come from that pool. So our current split is
  **train-on-test for CT-CLIP** and cannot give honest numbers.
- Acquire CT-RATE's **official validation split** (which CT-CLIP held out) via the stream-and-cache
  tool → a clean, leakage-free test set for *both* the teacher and our student.
- Measure **CT-CLIP's own retrieval** (R@1/5/10, mAP, nDCG) on that held-out set = the teacher
  ceiling and the honest bar.

### Phase 2 — Teacher embedding extraction (reuse the CT-FM pattern)
- Run CT-CLIP image encoder over all cached train volumes → cache a report-aligned image embedding
  per volume (`ctclip_cache/`, git-ignored). Same idempotent/resumable infra as `ctfm_teacher.py`.
- Cache CT-CLIP text embeddings for the reports (teacher's text tower).

### Phase 3 — Distillation training
- Train PointNet++ (init from the P12a-pretrained encoder) to match the cached CT-CLIP image
  embeddings (cosine + MSE), with a projection into CT-CLIP's joint dim. Optionally add a light
  report-contrastive term and the 18-label aux. Reuse/extend `distill.py`. Resumable, local, 6 GB.

### Phase 4 — Retrieval evaluation & decision gate
- Evaluate the **distilled point-cloud encoder** on the Phase-1 held-out set, retrieving against
  CT-CLIP text embeddings (and/or our text tower). Report the full metric set.
- **Decision gate:**
  - **Success:** distilled point-cloud reaches a meaningful fraction of the CT-CLIP teacher (target:
    held-out R@10 well above our 0.15 plateau, e.g. ≳ 0.30, and ≳ 50% of the teacher's R@10).
    → this becomes the deployment candidate; an original, efficient, working CT-report retriever.
  - **Failure:** if it still can't clear the teacher-relative bar, we have decisive evidence the
    point-cloud representation itself caps quality → then choose (a) adopt CT-CLIP directly, or
    (b) accept the modest model and build the platform.

### Phase 5 — Finalize
- Model card (student vs teacher, held-out metrics), AUP-003 conformance report, update
  `PROJECT_STATE.*`, P12 exit report. No weights committed (H-14). Wire the encoder into P13 (Qdrant).

## 5. Risks & mitigations
| Risk | Mitigation |
|---|---|
| CT-CLIP too big for 6 GB | CPU inference for one-time extraction; reduced precision; patch-wise |
| License forbids use | Verified in Phase 0 before download; abort if incompatible |
| Evaluation leakage (CT-RATE overlap) | Phase 1 uses CT-CLIP's held-out validation split |
| Distillation still plateaus (point-cloud ceiling) | The decision gate turns this into a clear, informative result, not wasted effort |

## 6. Governance actions on approval
- Record AUP-003 in `approved_architecture_addenda`; set `current_subphase: "P12c"`.
- `architecture_version` stays 2.4.5 / `master_plan_version` 1.0 (locked bundle unchanged; PointNet++
  remains the deployed encoder, CT-CLIP is a teacher + eval reference).
- Execute Phases 0→5 on the `phase/P12-training` branch; green CI at each committable step.

## 7. Approval requested
Approve executing this plan, starting with the **Phase 0 feasibility gate** (license + 6 GB check)
before any large download or training. On approval I verify CT-CLIP, then proceed phase by phase,
pausing only if Phase 0 finds it infeasible.
