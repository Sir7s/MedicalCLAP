# Phase Exit Report — P18 · Backup, Restore & Failure Recovery

> **Status: COMPLETE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P18 · report v1.0 |
| Branch | `phase/P18-backup-restore` |
| Date | 2026-07-21 |
| Prerequisite | P17 merged |
| Scope source | AUP-005 (checkpoint as an un-committed restorable artifact) |

## 1. Objective (met)
A single CLI that can **create**, **verify**, **list** and **restore** a backup of the
local system, with integrity guarantees and honest reporting of anything it could not
capture.

## 2. Deliverable
**`scripts/backup.py`** with four subcommands:

| Command | Behaviour |
|---|---|
| `create --out DIR` | pg_dump of the control plane, gzipped workspace archive, Qdrant index state, and a `manifest.json` with sha256 + size per component |
| `verify PATH` | recomputes every checksum; exits non-zero on corruption |
| `restore PATH [--yes]` | **verifies first and refuses on mismatch**; without `--yes` prints a dry-run plan |
| `list DIR` | lists backups with an OK/CORRUPT verdict each |

## 3. Two design decisions worth stating
**Large third-party assets are recorded, not copied.** The ~1.7 GB CT-CLIP checkpoint
is not embedded in every backup: the manifest records its path, size, **source URL**
and **licence**, and the restore plan lists it under `refetch`. Copying it would bloat
backups and casually redistribute a **CC-BY-NC-SA** asset — the wrong default. The
system is still fully restorable; the checkpoint is re-downloaded rather than unpacked.

**A bad restore is worse than no restore.** `restore` runs `verify` first and raises
rather than unpacking a corrupted archive over live data. Dry-run is the default.

## 4. Honesty fix found while testing
The first implementation reported Qdrant as **`ok` with zero points while Qdrant was
actually unreachable** — `count()` swallows connection errors and returns 0, so an
empty-but-healthy index was indistinguishable from a dead one. `capture_qdrant` now
probes connectivity explicitly (`get_collections()`) and records
`skipped: qdrant unreachable: …`. Restoring from a backup that silently claimed an
empty index would have been a real data-loss trap.

## 5. Exit-gate evidence (9 tests, CI)
- Backup creates and **verifies clean**; workspace contents round-trip through the archive.
- **Corruption is detected**: a single flipped bit (same file size) fails verification
  with a checksum error; a deleted component fails with a missing-file error.
- **Restore refuses** a corrupted backup (raises), and the dry-run plan reports what
  would be restored vs re-fetched without touching anything.
- **Manifest records external-artifact provenance** — source URL, licence, restore
  instructions for the checkpoint.
- **Unavailable components are recorded with a reason**, never silently dropped;
  a missing workspace is `skipped` with an explanation.
- CLI exercised end-to-end locally: create → verify (`ok: true`) → list.
- ruff clean; mypy clean (67 files).

## 6. Known limitations
- `pg_dump`/`psql` must be on PATH for database capture/restore; absence is recorded
  as `skipped`, not silently ignored.
- The Qdrant index is captured as **state** (collections + counts), not as a binary
  snapshot — it is deterministically re-buildable via `scripts/index_ctclip.py`, which
  the manifest note says explicitly.

## 7. Governance
Backups may contain user workspace data; they are written outside the repository and
are git-ignored. No weights or datasets are redistributed (H-14; CC-BY-NC-SA honoured).
`PROJECT_STATE.*` updated. Unlocks **P19** — Full Integration, Performance & Regression.
