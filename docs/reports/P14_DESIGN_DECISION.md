# P14 — Visual Direction: three proposals and the selected design

The Master Plan requires three visual directions to be presented before frontend
implementation. The user delegated the choice ("you don't need me to make decision,
decide yourself", 2026-07-21), so the three directions and the rationale for the
selection are recorded here instead of being presented interactively.

---

## Direction A — **Clinical Workstation** (dark, dense) ← **SELECTED**
Radiology-native dark theme. Two panes: query + ranked results on the left, CT viewer
and the explanation panel on the right. Compact rows, monospaced scores, findings
rendered as chips.

- **Pro:** dark UI is the standard in radiology reading (PACS viewers are dark) —
  grayscale CT retains contrast and the display doesn't fight the image.
- **Pro:** information-dense; scanning a ranked list of 10 candidates plus their
  reasons is the core task, and density serves it.
- **Pro:** reads as a professional clinical tool, which is the stated product goal.
- **Con:** less "friendly" for a first-time viewer.

## Direction B — **Clean Clinical** (light, airy)
Light background, generous whitespace, rounded cards, a consumer-health aesthetic.

- **Pro:** approachable, screenshots well for a portfolio.
- **Con:** a bright surround washes out grayscale CT and causes eye strain in the
  actual task; whitespace pushes results below the fold, hurting the core workflow.

## Direction C — **Research Console** (metrics-forward, monospace)
Terminal-inspired, evaluation-first: similarity matrices, per-finding probabilities,
α sweeps exposed as primary UI.

- **Pro:** excellent for inspecting the model — matches how this project was built.
- **Con:** it is a *research* instrument, not a product; the plan asks for a
  "near-product professional interface".

---

## Decision: **Direction A — Clinical Workstation**

**Rationale.** The product is a retrieval tool whose primary surface is grayscale CT
plus a ranked, *explained* candidate list. Direction A is the only one whose visual
system is chosen *for that task* rather than for first impressions: a dark surround is
the medical-imaging convention because it preserves perceived contrast in grayscale,
and density keeps the ranked results and their explanations visible together — which
is where this project's original contribution (findings-grounded explanations) lives.

Direction C's evaluation affordances are not discarded; the useful part (the α
recall/explainability balance) is surfaced as a single labelled control rather than a
research console.

## Design system (implemented)
- **Surface:** `#0d1117` base, `#161b22` panels, `#30363d` borders.
- **Text:** `#e6edf3` primary, `#8b949e` secondary.
- **Accent:** `#58a6ff` (interactive), `#3fb950` (healthy), `#f85149` (error/unavailable).
- **Findings chips:** translucent accent fill, used only for findings that both the
  query and the hit express — the UI can never display an ungrounded reason.
- **Type:** system UI stack; tabular numerals for scores.
- **Layout:** responsive two-pane; collapses to a single column under 900 px.

## Scope note
No segmentation view — P16 was dropped (AUP-005).
