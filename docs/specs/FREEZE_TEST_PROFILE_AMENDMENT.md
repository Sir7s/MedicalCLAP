# Freeze Test Profile — Amendment (required by AUP-005 §5)

| Field | Value |
|---|---|
| Amends | Freeze Test Profile v1.1 (`3D_Medical_CLIP_Freeze_Test_Profile_v1.1_CN.pdf`) |
| Reason | AUP-005 changed the deployed retrieval architecture and dropped P16 |
| Status | **Authoritative for the P20 Freeze Run** |
| Date | 2026-07-21 |

The locked profile asserts behaviour of a **PointNet++** retrieval system and includes
**segmentation** clauses. Neither describes the system that exists. Running the freeze
suite against the original text would certify a fiction, so the clauses below replace
them. Everything the original profile says about the control plane, storage, history,
and crash-recovery is **unchanged and still binding**.

---

## A. Superseded clauses

| Original clause | Disposition |
|---|---|
| Retrieval quality asserted on the PointNet++ point-cloud encoder | **Replaced** by §B.1 |
| Point-cloud encoder inference assertions (32,768-point sampling in the serving path) | **Replaced** by §B.2 — the point-cloud pipeline is research-only (AUP-005) |
| Text-guided 3D segmentation clauses (P16) | **Removed** — P16 dropped |
| Retrieval evaluated on the local train-derived split | **Replaced** by §B.3 (leakage-free) |

## B. Replacement clauses (asserted by the freeze run)

### B.1 — Retrieval quality (deployed architecture)
The deployed retriever is **CT-CLIP recall + findings-grounded re-ranking**.
- Held-out CT→text **R@10 ≥ 0.40** on a leakage-free split.
  *Measured: **0.511** (90 CT-RATE `valid` volumes) — PASS.*
- Bidirectional retrieval reported with Recall@1/5/10, mAP and nDCG.
  *Measured both directions — PASS.*

### B.2 — Inference viability
- CT-CLIP loads and embeds a real CT volume on the target GPU.
  *Verified P13; peak **2.25 GB** VRAM on a 6 GB card — PASS.*
- The point-cloud encoder is **absent from the serving path**.
  *`backend/app/retrieval/` imports no ML stack — PASS.*

### B.3 — Evaluation integrity
- Retrieval metrics are computed on data the recall model did **not** train on
  (CT-RATE `valid`), never on a train-derived split. — PASS.

### B.4 — Re-ranker invariants (new; the project's original contribution)
- Re-ranking is a **permutation** of the recalled pool: it can reorder but never drop
  a candidate, so the recall ceiling is preserved. — PASS (unit + e2e).
- An explanation cites **only findings both the query and the hit express**. — PASS.
- α = 1.0 reproduces pure recall ordering. — PASS.

### B.5 — Honest failure
- With the inference service unavailable, retrieval returns **503**; it never returns
  fabricated or silently degraded results. — PASS (unit + e2e).

### B.6 — Governance & licensing
- No weights, datasets, PHI or secrets tracked in git. — PASS (9 hardening tests).
- Third-party licences documented; the **CC-BY-NC-SA non-commercial restriction** is
  stated in the README. — PASS.

### B.7 — Durability
- A backup verifies by checksum; a corrupted backup is **refused** on restore. — PASS.
- Large third-party artifacts are restorable by recorded provenance. — PASS.

## C. Unchanged clauses (still binding)
Control-plane atomicity and state-machine legality (P2), outbox exactly-once and
dead-letter behaviour (P3), lease/fencing/handshake and forced cancel (P4), artifact
sealing and chunk verification (P5), NIfTI ingestion and viewer (P8), preprocessing
determinism (P9), and the bilingual text pipeline (P10).

## D. Freeze verdict rule
`FREEZE_PASSED` may be recorded only if **every** clause in §B and §C passes in one
run, with the evidence recorded in `docs/reports/P20_FREEZE_RUN.md`.
