"""English speech-to-text (P10, SPEC-01 §2.2).

Uses faster-whisper (CTranslate2, CPU, no PyTorch) with the `base` model for
offline English transcription. Model is loaded lazily and cached. English only.
"""
from __future__ import annotations

MODEL_SIZE = "base"

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path: str, language: str = "en") -> str:
    segments, _info = get_model().transcribe(audio_path, language=language)
    return " ".join(seg.text for seg in segments).strip()
