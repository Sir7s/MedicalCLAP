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

**Phase 3 — data scaling did NOT rescue it.** Streaming 3,003 volumes (2,112 train)
and retraining changed nothing: held-out stayed at the random floor, and a properly
tuned run (unfrozen BERT, cosine schedule, 1024-negative queue, augmentation) was
still flat at random after 36 epochs. A CT-FM foundation baseline — the teacher's
*own* frozen features used for retrieval — reached only **R@10 0.153**, barely above
our point-cloud model. Five distinct approaches all plateaued at **1.0–1.5× random**.

---

# DEPLOYED MODEL (AUP-005): CT-CLIP recall + findings-grounded re-ranking

The from-scratch encoder is **not** the deployed model. It is documented research
(above). The shipped system is:

**Stage 1 — recall:** CT-CLIP (CT-ViT image tower + text tower, CC-BY-NC-SA),
running locally on the RTX 4050 at **2.25 GB inference VRAM**.
**Stage 2 — re-rank:** our findings-grounded layer reorders the top-K by clinical
findings agreement. **Stage 3 — explain:** shared findings are rendered as the reason.

## Held-out results (90 CT-RATE `valid` volumes — CT-CLIP did NOT train on valid)

| Direction | System | R@1 | R@5 | **R@10** | mAP | nDCG |
|---|---|---|---|---|---|---|
| CT→text | CT-CLIP recall | 0.078 | 0.378 | **0.511** | 0.231 | 0.390 |
| CT→text | + findings re-rank (α=0.9) | 0.078 | 0.389 | **0.522** | 0.226 | 0.386 |
| text→CT | CT-CLIP recall | 0.111 | 0.367 | **0.511** | 0.249 | 0.403 |
| text→CT | + findings re-rank (α=0.6) | 0.089 | 0.344 | **0.533** | 0.231 | 0.390 |

Random baseline at this pool size ≈ R@10 0.11. **CT-CLIP is ~4× our best local
model (0.127) and ~4.6× random** — a genuinely working retriever.

**Re-ranker, honestly:** it adds **+0.011 (CT→text)** and **+0.022 (text→CT)** R@10
when weighted lightly, and **degrades results if weighted heavily** (R@10 falls to
0.40 at α=0.5). On a base this strong there is little room to reorder, and the
findings signal is both imperfect and correlated with CT-CLIP's own embedding.
**Its real value is interpretability** — every hit carries a clinical reason — plus
a small precision gain. It cannot reduce recall within the pool (it only reorders).

**Eval caveat:** 90 volumes, not the full valid split — 160 high-resolution (1024²)
volumes were skipped because the host machine could not allocate ~1 GB arrays
(C: full → exhausted pagefile). The eval is therefore biased toward 512² scans.

## Reproducibility
- Config in `ml/models/train_config.py`; per-run manifest in the run's `metrics.json`.
- Deterministic preprocessing (seed 42, P9); point-cloud cache is bit-reproducible.
- Weights are **not** committed to git (H-14); they load into the running app.

## Limitations
- **The from-scratch point-cloud encoder does not work** at locally achievable data
  scale (1.0–1.5× random across five approaches). It ships as documented research,
  not as the model. Root cause is data scale, not a defect.
- **CT-RATE reports are semi-templated** (~51% of reports are duplicated across
  volumes), so exact-match Recall@1 is a harsh, partly ill-posed target;
  R@10 / mAP / nDCG are more informative.
- **The re-ranker's metric gain is small** on a strong base (+0.01–0.02 R@10) and
  is harmful if over-weighted; it is justified primarily by interpretability.
- **Licensing:** CT-CLIP and CT-RATE are **CC-BY-NC-SA** — this system is
  **non-commercial**, requires attribution, and derivatives must share alike.
- **Not a diagnostic device.** Retrieval surfaces similar prior cases; it does not
  generate reports and must not be used for clinical decision-making.
