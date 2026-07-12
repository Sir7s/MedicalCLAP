"""Local Chinese->English translation (P10, SPEC-01 §2.2).

Uses Argos Translate — a lightweight, fully offline (after the one-time package
download) zh->en model, matching the architecture's 'lightweight/fast/local'
requirement. Query text is never logged (H-14).
"""
from __future__ import annotations

_ready = False


def ensure_model() -> None:
    """Download + install the zh->en package once (idempotent)."""
    global _ready
    if _ready:
        return
    import argostranslate.package
    import argostranslate.translate

    installed = {
        (lang.code, t.to_lang.code)
        for lang in argostranslate.translate.get_installed_languages()
        for t in lang.translations_from
    }
    if ("zh", "en") not in installed:
        argostranslate.package.update_package_index()
        avail = argostranslate.package.get_available_packages()
        pkg = next(p for p in avail if p.from_code == "zh" and p.to_code == "en")
        argostranslate.package.install_from_path(pkg.download())
    _ready = True


def translate_zh_en(text: str) -> str:
    import argostranslate.translate

    ensure_model()
    return argostranslate.translate.translate(text, "zh", "en").strip()
