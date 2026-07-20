# Phase Exit Report — P15 · Full History, Export & User Workflow

> **Status: COMPLETE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P15 · report v1.0 |
| Branch | `phase/P15-history-export` |
| Date | 2026-07-21 |
| Prerequisite | P14 merged (core UI) |
| Scope | AUP-005: no segmentation artifacts (P16 dropped) |

## 1. Objective (met)
Close the user workflow: a search can be **saved**, **revisited**, and **exported**,
so a session produces something durable rather than transient results on screen.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Persist retrieval results into the P5 history record | done |
| S2 | Export renderer (JSON + CSV) with injection hardening | done |
| S3 | Export endpoint with download headers | done |
| S4 | History UI (list, detail, export) | done |
| S5 | Save action wired into the Search panel | done |
| S6 | Tests, reports, PR | done |

## 3. Deliverables
- **`backend/app/history/export.py`** — renders a saved record to **JSON** (verbatim,
  full result set) or **CSV** (one row per hit: rank, volume, scores, explanation,
  report). Both carry the research-use disclaimer.
- **`GET /api/history/{id}/export?format=json|csv`** — returns the file with a
  `content-disposition` attachment header; unknown formats → 400; non-`ready`
  records stay invisible (404), preserving P5's visibility rule.
- **`backend/app/history/service.py`** — the saved payload is now kept on the record
  (`meta.payload`) so list/get/export are self-describing; the chunked, sealed
  artifact remains the durable copy.
- **`frontend/src/History.tsx`** — saved-search list, detail view with ranked hits and
  their findings chips, and JSON/CSV export buttons.
- **`frontend/src/Search.tsx`** — a **Save** action that lazily creates a workspace on
  first use and persists `{query, alpha, results}`.
- **`frontend/src/i18n.ts`** — history/export strings in both languages.

## 4. Security decision worth noting
**CSV formula injection is neutralised.** Radiology text and volume names are
untrusted input for a spreadsheet: a cell beginning `=`, `+`, `-` or `@` is prefixed
with `'` so Excel/Sheets treats it as text rather than executing it. Covered by a
regression test (`test_csv_escapes_formula_injection`).

## 5. Exit-gate evidence
- **Export rendering** (`backend/tests/test_history_export.py`, 6 tests): valid JSON
  with disclaimer; one CSV row per hit with explanations joined; report newlines
  flattened; **formula injection escaped**; unsupported format rejected; empty
  result set still exports a well-formed file.
- **Backend suite**: 47 tests pass (no regression to P5 history behaviour).
- **Governance suite** + state sync: pass. ruff clean; mypy clean (47 files).
- **Frontend**: `tsc --noEmit` clean; production build passes (162 kB JS / 52.5 kB gzip).

## 6. Known limitations
- Voice capture UI remains unimplemented; the P10 backend pipeline exists and the
  bilingual text path is complete, so this is a UI affordance gap, recorded honestly
  rather than claimed.
- Export covers saved history records; exporting an unsaved, in-flight result set
  requires saving first (deliberate — export reads the durable record).

## 7. Governance
No PHI or secrets in exports beyond the user's own saved content; the disclaimer is
embedded in every exported file. `PROJECT_STATE.*` updated.
Unlocks **P17** — Security, Privacy & Public Repository Hardening (P16 dropped).
