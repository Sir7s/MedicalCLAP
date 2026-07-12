# Phase Exit Report — P10 · Text Pipeline & Bilingual Input

> **Status: CANDIDATE — auto-merge on green CI.**

| Field | Value |
|---|---|
| Phase ID | P10 · report v1.0 |
| Branch | `phase/P10-text` |
| Date | 2026-07-12 |
| Prerequisite | P7 merged ✅ |

## 1. Objective (met)
Clean CT-RATE reports for training/retrieval, tokenize with BioClinicalBERT,
translate Chinese input to English locally, transcribe English speech offline,
and normalize any input into a single English retrieval query.

## 2. Subphases
| # | Subphase | Status |
|---|---|---|
| S1 | Report cleaning + segmentation | ✅ |
| S2 | BioClinicalBERT tokenizer pipeline | ✅ |
| S3 | Lightweight local zh→en translation (Argos) | ✅ |
| S4 | English speech-to-text (faster-whisper base) | ✅ |
| S5 | Unified query normalization + text dataset builder | ✅ |
| S6 | CI + reports + PR | ✅ |

## 3. Deliverables
- `ml/text/`: `report.py` (clean/segment + de-ident), `tokenizer.py`
  (BioClinicalBERT), `translate.py` (Argos zh→en, offline), `speech.py`
  (faster-whisper base, CPU), `query.py` (unified normalization + log-safe view),
  `dataset.py` (report↔volume pairing).
- Model choices (user-approved): Argos Translate zh→en, Whisper `base`,
  `emilyalsentzer/Bio_ClinicalBERT` tokenizer. **No PyTorch in the query/tokenize
  path** (torch only arrives transitively via Argos' stanza; recorded in
  `ml/requirements-text.txt`).

## 4. Exit-gate evidence (Master Plan P10)
- **Report training input stable** — every one of the 801 split volumes pairs to
  a non-empty cleaned English report (`test_every_split_volume_has_a_report`). ✅
- **Chinese & English both form an English query** — English passes through;
  Chinese is translated locally (verified: "肺部有一个小结节" → English containing
  "lung"); voice → transcribed English. ✅
- **English speech transcribes offline** — faster-whisper base runs on a local
  WAV, returns text, no network at inference. ✅

## 5. Tests (all green)
8 pure tests (report cleaning, query normalization for en/zh/voice, empty/
missing-translator rejection, **H-14 log-safe redaction**, dataset pairing) +
3 model tests (BioClinicalBERT tokenizer padding, zh→en regression + determinism,
Whisper smoke). ruff/mypy clean.

## 6. CI note (transparent)
The three model-dependent tests download models (~100 MB Argos + ~140 MB Whisper
+ tokenizer). Following the project's heavy-prerequisite pattern (cf. compose/
data lanes), they **auto-skip in CI** and are verified locally (evidence above);
the CI ml lane runs the 8 pure text tests + the P9 preprocessing tests. This
keeps CI fast and free of large per-run model downloads.

## 7. Security
Query/report text is never logged; `NormalizedQuery.redacted()` exposes metadata
only (`test_redacted_view_has_no_query_text`). De-identification pass on reports.

## 8. Architecture deviation
**none** — BioClinicalBERT tokenizer, local lightweight translation, English-only
offline speech, unified English query all follow SPEC-01 §2.2 / SPEC-07 §8.3.

## 9. Governance
`PROJECT_STATE.*` updated. Auto-merge on green CI; unlocks P11 — Retrieval Model
Baseline (first PyTorch/PointNet++ phase).
