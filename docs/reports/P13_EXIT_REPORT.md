# Phase Exit Report — P13 · Qdrant Index & Real Retrieval Integration

> **Status: COMPLETE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P13 · report v1.0 |
| Branch | `phase/P13-retrieval-integration` |
| Date | 2026-07-21 |
| Prerequisite | P12 merged (CT-CLIP retriever + explainable re-rank) |
| Scope source | AUP-005 (amended P13 scope) |

## 1. Objective (met)
Turn the P12 retriever into a live service: index CT-CLIP embeddings in Qdrant,
expose two-stage search (recall → findings re-rank → explanations) over the API, and
replace P4's **mock** GPU worker with **real CT-CLIP inference**.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Qdrant collections + upsert/search layer | done |
| S2 | Serving-side findings re-rank + explanations | done |
| S3 | CT-CLIP inference service (real GPU worker) | done |
| S4 | Retrieval API + router wiring | done |
| S5 | Corpus indexer | done |
| S6 | Tests (CI + infra + backend lanes), reports, PR | done |

## 3. Deliverables
- **`backend/app/retrieval/index.py`** — two Qdrant collections (`ct_volumes`,
  `ct_reports`), 512-d cosine, idempotent creation, upsert/search/count helpers.
- **`backend/app/retrieval/rerank.py`** — dependency-free findings-grounded re-rank
  (`score = α·recall + (1−α)·findings_match`) + grounded explanations. Mirrors the
  research implementation so the API container never imports the ML stack.
- **`backend/app/retrieval/embedder.py`** — HTTP client for CT-CLIP; unavailability is
  an explicit, reportable state (no silent degradation).
- **`backend/app/retrieval/service.py` / `api.py`** — orchestration and routes:
  `GET /api/retrieval/status`, `POST /api/retrieval/search/text`,
  `POST /api/retrieval/search/volume`.
- **`ml/serving/ctclip_service.py`** — **the real GPU worker**: loads CT-CLIP, exposes
  `/health`, `/warmup`, `/embed/text`, `/embed/volume` (with zero-shot findings),
  using CT-CLIP's documented preprocessing.
- **`scripts/index_ctclip.py`** — indexes the cached embeddings into both collections.

## 4. Key design decisions
- **CT-CLIP runs as a host-side service, not inside the API container.** Its 2024
  research-code stack + CUDA build + 1.7 GB checkpoint are deliberately isolated;
  the backend talks to it over loopback. This keeps the API image light and avoids
  containerising CUDA on a disk-constrained host. Documented as an implementation
  choice (same spirit as P8's canvas viewer).
- **Re-rank logic is duplicated, not imported.** `backend/app/retrieval/rerank.py` is
  pure Python so the serving path has no numpy/torch dependency; `ml/models/rerank.py`
  remains the research version. Both are covered by tests asserting the same invariants.
- **Honest failure mode.** If CT-CLIP is unreachable, search returns **503**, never
  fabricated results.

## 5. Exit-gate evidence
- **Re-rank invariants proven** (`tests/test_retrieval_rerank.py`, CI): re-ranking is a
  permutation (recall ceiling preserved), findings agreement promotes the matching
  candidate, α=1 preserves recall order, and **explanations only ever cite findings
  both sides express**.
- **Qdrant integration** (`tests/infra/test_retrieval_qdrant.py`, compose lane):
  idempotent collection creation, upsert → nearest-neighbour search returns the
  correct volume, end-to-end re-rank preserves the pool.
- **API contract** (`backend/tests/test_retrieval_api.py`, backend lane): ranked
  results with explanations for both query types, 503 on embedder outage, α=1
  ordering, request validation.
- ruff + mypy clean (`backend/app` 46 files, `scripts tests ml` 63 files).

## 6. Architecture deviation
None beyond AUP-005 (already approved). P13 implements the amended architecture:
CT-CLIP recall + findings-grounded explainable re-ranking, PointNet++ absent from
the serving path.

## 7. Known limitations
- The Qdrant and CT-CLIP paths are exercised in CI (compose lane) and by unit tests;
  a full local end-to-end run needs Docker up and the CT-CLIP service started
  (`docs/RETRIEVAL_SERVING.md`).
- Text→CT re-ranking uses the top recalled report's findings as the query proxy; a
  dedicated text→findings extractor is a future refinement.

## 8. Governance
No weights/PHI committed (H-13/H-14). CC-BY-NC-SA obligations tracked for P17.
`PROJECT_STATE.*` updated. Unlocks **P14** — Professional Frontend Design & Core UI.
