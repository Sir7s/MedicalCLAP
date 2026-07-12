# Phase P10 — Text Pipeline & Bilingual Input

Report cleaning, BioClinicalBERT tokenization, local zh→en translation (Argos),
offline English speech (faster-whisper base), and unified English query
normalization. No PyTorch in the tokenize/query path; no report text logged.

## Exit-gate evidence
- Report training input stable — all 801 split volumes pair to a cleaned English report.
- Chinese & English both normalize to an English query (zh translated locally; verified).
- English speech transcribes offline (faster-whisper base).

## Test summary
8 pure tests (report cleaning, query normalization en/zh/voice, empty/missing-
translator rejection, H-14 log-safe redaction, dataset pairing) + 3 model tests
(tokenizer padding, zh→en regression+determinism, Whisper smoke). ruff/mypy clean.

## CI note
Model-dependent tests (~240 MB of models) auto-skip in CI and are verified
locally (project's heavy-prerequisite pattern); CI ml lane runs the 8 pure text
tests + P9 preprocessing. Model deps documented in `ml/requirements-text.txt`.

## Change log
- `ml/text/` (report, tokenizer, translate, speech, query, dataset).
- `ml/requirements-text.txt` (transformers, argostranslate, faster-whisper).
- Tests: `tests/ml/test_text.py`.

## Approval
Auto-merge on green CI. Unlocks P11 — Retrieval Model Baseline.
