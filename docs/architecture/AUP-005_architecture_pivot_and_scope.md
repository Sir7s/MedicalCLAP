# Architecture Update Proposal — AUP-005

## Retrieval architecture pivot (CT-CLIP + findings re-rank) and P16 removal

| Field | Value |
|---|---|
| Proposal ID | AUP-005 |
| Status | **APPROVED** 2026-07-20 (user directed: drop P16, replan remaining phases) |
| Date | 2026-07-20 |
| Supersedes | The PointNet++-as-deployed-encoder assumption in AUP-001/002/003/004 |
| Affects | Deployed retrieval architecture; Master Plan scope (P16 removed); Freeze Test Profile (P20); phases P13–P20 |

---

## 1. Why this amendment exists
Two facts have diverged from the original plan and must be recorded before the
validation phases (P17–P20) run, or those phases would be validating a system
that does not exist:

1. **The mandated encoder does not work at achievable scale.** Five documented
   attempts (from-scratch, P12a label-pretraining, P12b CT-FM distillation,
   augmentation + queue, tuned data-scaling to 2,112 volumes) all plateaued at
   **1.0–1.5× random** on held-out data. Root cause is data scale: the from-scratch
   PointNet++ CT encoder needs orders of magnitude more paired data than is locally
   obtainable (CT-CLIP used ~25k volumes; MedP-CLIP shows the regime is millions).
2. **A working system was achieved by a different route.** CT-CLIP (voxel CT-ViT,
   CC-BY-NC-SA) runs locally on the 6 GB GPU (2.25 GB inference) and delivers
   **held-out R@10 = 0.511** — ~4× the best local model — with our
   findings-grounded re-ranking layer adding interpretability and a small precision
   lift (+0.011 CT→text, +0.022 text→CT R@10).

## 2. Amended retrieval architecture (the deployed system)
```
query (text / voice / zh->en, or CT)
   │
   ├─ Stage 1  RECALL     CT-CLIP (CT-ViT image tower + text tower) -> 512-d, Qdrant ANN
   │
   ├─ Stage 2  RE-RANK    findings agreement (zero-shot / 18-label) reorders top-K
   │
   └─ Stage 3  EXPLAIN    shared findings rendered as the reason for each hit
```
- **Deployed image encoder: CT-CLIP CT-ViT** (was: PointNet++).
- **Original contribution: the findings-grounded explainable re-ranking layer** (Stages 2–3).
- **PointNet++ / point-cloud pipeline (P9, P11, P12a/b) is reclassified as documented
  research** — retained in-repo as an honest negative result, **removed from the
  serving path**. It is no longer a deployment dependency.

### Compliance note (supersedes prior reading)
The original CT-CLIP policy ("must not load incompatible CT image encoder weights
into PointNet++") existed to prevent silently substituting another model *inside*
our encoder. We are not doing that: we are **adopting CT-CLIP as an acknowledged,
cited, separately-licensed component**, with our contribution layered on top. This
is an explicit, recorded architecture decision rather than a policy circumvention.
**New obligation:** CT-CLIP and CT-RATE are **CC-BY-NC-SA** — the project is
**non-commercial**, requires attribution, and derivatives must share alike (see P17).

## 3. Scope change: P16 removed
**P16 (Text-guided 3D Segmentation) is dropped**, per user decision and consistent
with the recorded rule *"retrieval has priority if time conflicts"* and its
`planned_experimental` status. Consequences:
- `segmentation.required_for_final_demo` -> **false**; status -> `dropped`.
- ReXGroundingCT is no longer an acquisition target.
- No segmentation view (P14), no segmentation artifacts in history/export (P15),
  no segmentation paths in integration (P19) or the freeze profile (P20).
- Its stated architecture (frozen PointNet++ + text-conditioned seg head) is moot
  regardless, since PointNet++ is no longer the deployed encoder.

## 4. Amended remaining phases

| Phase | Amended scope |
|---|---|
| **P13** — Qdrant & Real Retrieval | Index **CT-CLIP** embeddings; re-ranker + explanations in the API. **Newly in scope:** a *real* GPU worker running CT-CLIP inference (P4's worker was a mock), and CT-CLIP deps + 1.7 GB checkpoint in the serving image. |
| **P14** — Frontend (3 directions, user picks) | Bilingual/voice query, CT viewer, ranked results **with explanations**. No segmentation view. |
| **P15** — History, Export, Workflow | Unchanged minus segmentation artifacts. |
| ~~**P16**~~ | **Dropped** (this AUP). |
| **P17** — Security / Privacy / Public repo | Adds **CC-BY-NC-SA compliance**: attribution, share-alike, explicit non-commercial notice, third-party model licensing. |
| **P18** — Backup / Restore | Must treat the **1.7 GB CT-CLIP checkpoint** as an un-committed, restorable artifact (H-14 unchanged). |
| **P19** — Integration / Performance | Must measure **CT-CLIP inference latency and ~2.5 GB VRAM** in the serving path; capacity planning for a 6 GB GPU. |
| **P20** — Freeze Run / Release | Runs against the **amended** Freeze Test Profile (see §5). |

## 5. Freeze Test Profile impact (required before P20)
The profile's retrieval clauses assume the PointNet++ architecture. Before P20 they
must be restated against the deployed system:
- Retrieval quality asserted on **CT-CLIP + re-rank**, on a **leakage-free held-out
  split** (CT-RATE `valid`), not on train-derived data.
- Replace point-cloud encoder assertions with CT-CLIP inference assertions
  (load, embed, VRAM ceiling, determinism).
- Add re-ranker assertions: never reduces recall within the pool; explanations
  reference only findings both query and hit express.
- Remove segmentation clauses.

## 6. Honest record (kept, not hidden)
The point-cloud investigation stays documented in `docs/reports/P12_MODEL_CARD.md`
and AUP-001/002/003: five approaches, their measured failures, the CT-FM baseline
(R@10 0.153), and the data-scale conclusion. The project's contribution is the
**explainable retrieval layer plus an honest negative result**, not a claim that
the from-scratch encoder worked.

## 7. Governance actions
- Record AUP-005 in `approved_architecture_addenda`.
- `project_state.json`: `segmentation.status = "dropped"`,
  `required_for_final_demo = false`; add `retrieval_architecture` reflecting §2;
  note the deployed-encoder change and the non-commercial licence obligation.
- `PROJECT_STATE.md`: mirror the above; mark P16 dropped in the roadmap.
- Locked bundle versions (architecture 2.4.5 / plan 1.0) remain the *baseline*
  documents; this addendum records the delta, consistent with AUP-001/002/004.
