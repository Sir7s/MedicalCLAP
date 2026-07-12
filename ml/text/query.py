"""Unified query normalization (P10, SPEC-01 §2.2 / §2.4).

Any input — English text, Chinese text (translated locally to English), or
English speech (transcribed) — is normalized to a single English retrieval
query. Translator/transcriber are injected so the core is testable without the
heavy models. Query text is never logged (H-14).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_WS = re.compile(r"\s+")


def _norm_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class NormalizedQuery:
    text_en: str
    source_lang: str      # "en" | "zh"
    source: str           # "text" | "voice"

    def redacted(self) -> dict:
        """Log-safe view: metadata only, never the query text (H-14)."""
        return {"source_lang": self.source_lang, "source": self.source,
                "chars": len(self.text_en)}


class QueryError(ValueError):
    pass


def normalize_text_query(
    text: str,
    source_lang: str = "en",
    *,
    translate: Callable[[str], str] | None = None,
) -> NormalizedQuery:
    text = _norm_ws(text)
    if not text:
        raise QueryError("empty query")
    if source_lang == "zh":
        if translate is None:
            raise QueryError("zh query requires a translator")
        text_en = _norm_ws(translate(text))
        if not text_en:
            raise QueryError("translation produced empty text")
    elif source_lang == "en":
        text_en = text
    else:
        raise QueryError(f"unsupported source_lang {source_lang!r}")
    return NormalizedQuery(text_en=text_en, source_lang=source_lang, source="text")


def normalize_voice_query(
    audio_path: str,
    *,
    transcribe: Callable[[str], str],
) -> NormalizedQuery:
    text_en = _norm_ws(transcribe(audio_path))
    if not text_en:
        raise QueryError("transcription produced empty text")
    return NormalizedQuery(text_en=text_en, source_lang="en", source="voice")
