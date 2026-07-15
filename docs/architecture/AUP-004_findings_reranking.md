# Architecture Update Proposal — AUP-004

## Findings-grounded, explainable re-ranking on a foundation recall core

| Field | Value |
|---|---|
| Proposal ID | AUP-004 |
| Status | **APPROVED** 2026-07-15 (user directed: "come up with a plan and execute") |
| Date | 2026-07-15 |
| Affects | Adds a two-stage retrieval design (recall → findings re-rank → explain). Locked bundle unchanged; recorded as an approved addendum. Supersedes the pure-distillation direction of AUP-003 (kept as an optional efficiency track). |
| Trigger | From-scratch encoders can't reach good retrieval locally; the reliable path is a proven recall core + an original precision/interpretability layer. |

---

## 1. Design in one picture
```
query (text / CT)
   │
   ├─ Stage 1  RECALL  ── CT-CLIP embedding similarity ─► top-K candidates
   │                       (fallback: CT-FM / our encoder if CT-CLIP infeasible)
   │
   └─ Stage 2  RE-RANK ── 18-finding classifier ──► findings match
                          score = α·sim + (1-α)·findings_match  ─► reordered top-K
                                                              │
                          Stage 3  EXPLAIN ── overlapping findings ─► "both show effusion + cardiomegaly"
```
Stage 1 owns **recall** (proven). Stages 2–3 are the **original contribution**: precision +
interpretability. The re-ranker only reorders within the pool, so it can never hurt recall.

## 2. Why this is the chosen design
- **Recall is anchored** by a proven model (near-guaranteed), so the risky part is removed.
- **The original work is CT-CLIP-independent**: the findings classifier + re-ranker + explanations
  are built and validated *now* on features we already have cached (CT-FM). CT-CLIP is a drop-in
  recall upgrade behind a feasibility gate — if it won't run on 6 GB, the system still works on a
  fallback recall source. No single point of failure.
- **Interpretable, clinically-grounded retrieval** is a genuine, defensible contribution and a
  standout demo feature.

## 3. Execution stages (front-load the certain, original parts)

### Stage A — 18-finding classifier (now; CT-CLIP-independent) 🟢
- Train a multi-label classifier on cached **CT-FM features** (3,003 vols) against the 18 labels.
- Report held-out **AUROC / precision / recall / F1** (macro + per class).
- Deliverable: `ml/models/findings.py` + saved classifier + metrics. This is also the "guaranteed
  floor" — a working, measurable model regardless of what happens with CT-CLIP.

### Stage B — Re-rank + explain framework (CT-CLIP-independent) 🟢
- `ml/models/rerank.py`: given a query findings-vector + candidate findings-vectors + Stage-1
  similarities, compute `score = α·sim + (1-α)·findings_match`, reorder, and emit the overlapping
  findings as the explanation string.
- Text query → findings: a synonym/keyword map over the 18 finding names (MVP), upgradeable to a
  small text classifier.
- Validate the twist: measure **Precision@K / nDCG with vs. without** the re-ranker, using a base
  recall source (CT-FM similarity or our P12a encoder) — proves the contribution before CT-CLIP.

### Stage C — CT-CLIP recall integration (feasibility-gated) ⚠
- Phase 0 gate: CT-CLIP **license** + **6 GB / Python-3.14** check (isolated 3.11 venv if needed).
- If feasible: pull CT-RATE's held-out **valid** split (leakage-free), cache CT-CLIP embeddings,
  plug in as Stage-1 recall, re-measure end-to-end.
- If infeasible: keep the best local recall source; the re-ranking system stands on its own.

### Stage D — Finalize & wire to platform 🟢
- Model card, metrics, AUP-004 conformance, P12 exit report, state update, PR, green CI.
- Hand the two-stage retriever to **P13** (Qdrant index + API), surfacing the explanation strings in the UI.

## 4. Evaluation
- **Classifier:** macro/per-class AUROC, precision, recall, F1 (held-out).
- **Re-ranker (the contribution):** Precision@K, mAP, nDCG **with vs. without** re-ranking — the
  delta is the result. Plus qualitative explanation strings.
- Honest notes: labels are model-generated (pseudo-labels); CT-CLIP eval uses the leakage-free valid split.

## 5. Governance
- Recorded in `approved_architecture_addenda`; `current_subphase = "P12d"`. Locked bundle unchanged.
- Executed on `phase/P12-training`; green CI at each 🟢 checkpoint. No weights/PHI committed (H-13/H-14).
