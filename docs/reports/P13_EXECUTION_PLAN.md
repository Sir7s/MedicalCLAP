# Phase Execution Plan — P13 · Qdrant Index & Real Retrieval Integration

> **STATUS: WIP / DRAFT — NOT AN OFFICIAL PHASE.** Master Plan P13 precondition
> is "P12 生效". The repo is at **P9 (in_review)**; P10–P12 (text pipeline,
> model training) are not done. This branch (`phase/P13-qdrant-retrieval`) is
> built now against **placeholder embeddings** so the index/digest/search/eval
> code is ready when P12 lands. Do **not** treat this as a phase exit or merge to
> `main` until P12 is merged and the owner (Max / `Sir7s`) approves. Respects
> Hard Constraint **H-01** (no future-phase work) by staying WIP-isolated.

## Goal (Master Plan P13)
Build a **versioned vector index** and replace the mock retrieval with real
retrieval. Subphases: (1) Payload Schema → (2) CT/Report Embeddings → (3)
versioned Qdrant Collection → (4) Content Digest → (5) real Retrieval Job.

## Files (this WIP scaffold)
| Path | Role | Owner |
|---|---|---|
| `ml/retrieval/payload.py` | Payload schema + Canonical JSON (Subphase 1) | scaffolded |
| `ml/retrieval/embeddings.py` | `load_embeddings()` — **placeholder**, one-line swap for real encoder (Subphase 2) | scaffolded |
| `ml/retrieval/qdrant_index.py` | 512-d cosine collection, versioned name, ingest (Subphase 3) | scaffolded |
| `ml/retrieval/digest.py` | Content digest §7.5 / IMP-DATA-001 (Subphase 4) | scaffolded |
| `ml/retrieval/search.py` | CT→Text / Text→CT (Subphase 5) | **Shunyu (TODO)** |
| `ml/retrieval/eval.py` | Recall@1/5/10, mAP, nDCG (§8.4) | **Shunyu (TODO)** |
| `tests/ml/test_retrieval_*.py` | plumbing tests (pass) + search/eval skeletons (skipped) | mixed |

## Commands
```bash
python -m pytest tests/ml/test_retrieval_*.py   # 16 pass, 6 skip (search/eval WIP)
ruff check ml/retrieval tests/ml
# real index (needs qdrant-client + a running Qdrant), later subphase:
# python -m ml.retrieval.qdrant_index ...
```

## Clause Mapping
| Clause | Where implemented |
|---|---|
| §7.5 / IMP-DATA-001 (content digest, float32-LE, sorted point_id, Canonical JSON, no NaN/Inf) | `digest.py` |
| §8.2/§8.3 (512-d L2-normalized embeddings) | `embeddings.py` contract + tests |
| §8.6 (deployment-bound distance = cosine) | `qdrant_index.DISTANCE` |
| §7.4 (fixed version-bound collection name, not alias) | `qdrant_index.collection_name` |
| §2.2/§8.4 (CT-only & Text-only, no hybrid; Recall/mAP/nDCG both directions) | `search.py`, `eval.py` (TODO) |
| §8.7 (similarity ≠ diagnostic probability) | noted in `search.py`; enforce at UI/PDF/JSON layer |
| IMP-EXEC-013 (QDRANT_TEMPORARILY_UNAVAILABLE retryable) | handled by worker/caller, later subphase |
| IMP-DATA-002 (restore validation: metadata/count/dim/metric/config hash/manifest hash/sampling) | later subphase (needs deployment tables) |

## Deferred to later subphases (need coordination / real model)
- Deployment & rollback tables `model_deployments / active_model_deployment /
  deployment_references` (§7.4/§3.1) + alembic migration + restore validation
  (IMP-DATA-002).
- Wiring retrieval as a Model Job through Supervisor/GPU-worker (SPEC-03) with the
  §4.9 watchdog profile; `qdrant_storage` storage reservation (§5.5).

## Open items to confirm with owner (the only 3 not fixed by spec)
1. **How real embeddings arrive** — `encode()` call vs exported `.npy`/`.parquet`
   (single interface: `embeddings.load_embeddings`).
2. **case_id / point_id pairing** — so a CT links to its matching report for eval
   ground truth (constant in `payload.make_point_id`).
3. **Canonical JSON profile** — spec says "Canonical JSON" without citing RFC 8785;
   current impl = sorted-keys/compact/UTF-8/no-NaN (matches JCS for string/int
   payloads). Confirm if a stricter profile is required.

## Risks
- Placeholder embeddings ≠ real distribution: metrics are only a smoke test until
  P12. Contract (512-d/float32/L2-norm/finite) is enforced so the swap is safe.
- Qdrant point-id must be int/UUID: logical string `point_id` lives in the payload
  and drives the digest; Qdrant id is a deterministic UUID5 of it.
