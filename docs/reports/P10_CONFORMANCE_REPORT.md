# Implementation Conformance Report — P10

Per IMP-GOV-001/002; Architecture SPEC-01 §2.2 / SPEC-07 §8.3.

| Spec | Requirement | Status | Evidence |
|---|---|---|---|
| SPEC-07 §8.3 | BioClinicalBERT text tokenization | implemented | `ml/text/tokenizer.py`; padding test |
| SPEC-01 §2.2 | Chinese text translated locally to English before retrieval | implemented | `ml/text/translate.py` (Argos, offline); regression test |
| SPEC-01 §2.2 | English voice input, local Whisper | implemented | `ml/text/speech.py` (faster-whisper base, CPU); smoke test |
| SPEC-01 §2.2 | Unified English retrieval query from any input | implemented | `ml/text/query.py`; en/zh/voice tests |
| Master Plan P10 | Report↔CT pairing; training text stable | implemented | `ml/text/report.py`, `dataset.py`; pairing test (801/801) |
| H-14 | Sensitive text not logged | implemented | `NormalizedQuery.redacted()`; redaction test; de-ident in cleaning |

Model-dependent tests verified locally (auto-skip in CI; see Exit Report §6).
In-scope coverage 100%; deviations 0.
