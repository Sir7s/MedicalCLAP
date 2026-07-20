# Phase Exit Report — P14 · Professional Frontend Design & Core UI

> **Status: COMPLETE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P14 · report v1.0 |
| Branch | `phase/P14-frontend` |
| Date | 2026-07-21 |
| Prerequisite | P13 merged (live retrieval API) |
| Design gate | Delegated to the AI by the user (2026-07-21); three directions recorded in `docs/reports/P14_DESIGN_DECISION.md` |

## 1. Objective (met)
Deliver the near-product core UI: a professional interface for CT↔report retrieval
with bilingual support, the CT viewer, and — the differentiating feature — **ranked
results carrying their clinical explanations**.

## 2. Design gate
The Master Plan requires three visual directions before implementation. With the
choice delegated, all three were worked up and recorded, and **Direction A —
"Clinical Workstation"** was selected: dark, radiology-native, information-dense.
Rationale (full text in the decision doc): grayscale CT keeps its perceived contrast
against a dark surround (the PACS convention), and density keeps the ranked list and
its explanations visible together — which is exactly where this project's original
contribution lives.

## 3. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Three visual directions + selection rationale | done |
| S2 | Design system (`theme.css`) | done |
| S3 | Bilingual string layer (`i18n.ts`, zh/en) | done |
| S4 | Search UI with explanation chips (`Search.tsx`) | done |
| S5 | App shell: tabs, language toggle, live engine status | done |
| S6 | Typecheck + build + reports + PR | done |

## 4. Deliverables
- **`frontend/src/theme.css`** — the Clinical Workstation design system: dark surface
  tokens, accent/ok/error semantics, findings chips, responsive two-pane grid
  (collapses below 900 px).
- **`frontend/src/i18n.ts`** — complete **Chinese/English** string set (product
  requirement), typed so a missing translation is a compile error.
- **`frontend/src/Search.tsx`** — the core surface: query box (⌘/Ctrl+Enter),
  **α slider** exposing the recall↔findings balance, top-K control, ranked result
  cards with score, **findings chips**, and a detail pane showing the report plus the
  recall/findings score split.
- **`frontend/src/App.tsx`** — shell with Search / Viewer / Tasks tabs, language
  toggle, and a live CT-CLIP engine indicator polled from `/api/retrieval/status`.

## 5. Design decisions worth noting
- **Explanations are rendered, never invented.** The UI only displays the
  `explanation` array the API returns, which the backend grounds in findings *both*
  the query and the hit express. The frontend cannot show an unsupported reason.
- **Engine state is surfaced, not hidden.** When the CT-CLIP service is down the
  header dot turns red and the panel explains how to start it — matching the API's
  honest 503 rather than pretending results are unavailable for another reason.
- **The α control is the one piece of research UI kept** (Direction C's useful
  remnant), presented as a plain labelled balance rather than a metrics console.
- **No segmentation view** — P16 dropped (AUP-005).

## 6. Exit-gate evidence
- `npm run lint` (tsc --noEmit): **clean**.
- `npm run build` (tsc -b && vite build): **passes** — 35 modules, 157.9 kB JS
  (51.5 kB gzip), 3.6 kB CSS.
- Existing Viewer and control-plane Dashboard remain reachable as tabs; no
  regression to P8/P6 surfaces.

## 7. Known limitations
- Voice input is specified for the product and the backend pipeline exists (P10), but
  the mic capture UI is deferred to P15 with the rest of the user-workflow surface.
- CT-as-query (`/search/volume`) is exposed by the API and used by the viewer flow;
  the drag-and-drop query affordance is a P15 item.
- No component test runner is configured in this project; the frontend lane is a
  typecheck + build gate, consistent with P1's setup.

## 8. Governance
No secrets or data in the frontend bundle. `PROJECT_STATE.*` updated.
Unlocks **P15** — Full History, Export & User Workflow.
