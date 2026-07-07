# Phase Execution Plan — P5 · Artifact, Workspace & Lightweight History

**Source:** Master Plan §P5 (p.14); Architecture SPEC-04 (workspace/artifact
storage, atomic finalize, references, storage reservation, cleanup gates),
SPEC-05 (history state machine, chunk storage, verification seal); Appendix
IMP-HIST-001..004, IMP-STOR-001..003; Freeze FR-STOR-001/003/005/006/007/009/012.
**Prerequisite:** P4 merged ✅ (`5d5b188`). **Branch:** `phase/P5-artifacts`.
**Merge pre-authorization:** granted 2026-07-07 conditional on green CI.

## Objective
Atomic artifact finalize (`.partial → fsync → SHA-256 → atomic rename`),
workspace file layout with lease-revision paths, dual reference lifecycles
(source/snapshot), storage reservation with atomic quota checks, and the
lightweight-history state machine with chunked artifact storage + verification
seal — incomplete artifacts and non-ready history are never visible.

## Scope boundary (H-01)
✅ P5: tables (history_records/save_operations/artifacts/chunks, source/snapshot
references, storage_reservations), paths module, atomic finalize + manifests,
reference lifecycle, reservation, lightweight-history save flow, History API v0.
❌ Not P5: dashboard/WebSocket (P6), full-archive/re-executable profiles (P15),
backup/restore (P18), PDF/JSON export (P15).

## Subphases
| # | Subphase | Critical tests |
|---|---|---|
| S1 | Volume/file-path layout (lease-revision artifact dirs) | path shape unit tests |
| S2 | Atomic finalize `.partial→fsync→sha256→rename` + manifest | **artifact crash consistency** (failpoint before rename) |
| S3 | Tables migration + Source/Snapshot references (IMP-HIST-001/002) | **reference anti-GC** (FR-STOR-001); snapshot immutability (FR-STOR-003) |
| S4 | Storage reservation, atomic quota (IMP-STOR-001/002/003) | **concurrent no-oversell** (FR-STOR-012 subset) |
| S5 | Lightweight history state machine + chunked artifacts + seal (IMP-HIST-003/004) + History API v0 | **history crash recovery** (FR-STOR-009); late-chunk rejection (FR-STOR-005); index continuity (FR-STOR-006); corruption (FR-STOR-007) |
| S6 | CI + reports + PR + (authorized) merge | full suite green |

## Key designs
- Artifact path: `model_jobs/{job_id}/lease-{revision}/…` (SPEC-04 §5.3); base
  dir env-configurable (`MEDCLIP_WORKSPACE_ROOT`, default `./workspace_data`).
- Finalize: write `.partial` → flush+fsync → sha256 → `os.replace` → fsync
  parent dir (best-effort on Windows) → sidecar manifest JSON. Finalized files
  read-only. Incomplete = `.partial` only ⇒ invisible to readers.
- References: `workspace_source_references` protect originals until snapshot
  manifest finalized; `history_snapshot_references` protect snapshots until
  history ready/cleanup (IMP-HIST-002 order enforced in service code).
- Reservation: quota row per (backend, filesystem_identity) locked FOR UPDATE;
  active sum + request ≤ quota else rejected (IMP-STOR-002).
- History: `preparing → snapshotting → writing_artifacts → verifying → ready`;
  chunked artifact (8 MB default; small in tests), seal flips `writing →
  verifying` + `verification_generation+1`; late chunks rejected at the DB
  layer by status check; final short transaction re-validates count/size/
  continuity + hashes. Only `ready` records are listable (SPEC-05).

## Coverage
Storage/history modules are data-integrity-critical → target high coverage via
the FR-mapped tests; API v0 is a thin wrapper (smoke-tested).
