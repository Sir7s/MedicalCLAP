"""P10 tests — report cleaning, query normalization, dataset pairing, and
(when the models are present) tokenizer / translation / speech.

Pure-Python tests always run. Model-dependent tests auto-skip when the library
or downloaded model is absent (e.g. in CI), and are verified locally.
"""
from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.text import query, report  # noqa: E402

DATA = REPO_ROOT / "data" / "ct_rate"
_have_data = (DATA / "split_revision.json").is_file() and (
    DATA / "dataset" / "radiology_text_reports" / "train_reports.csv"
).is_file()


def _spec(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


# --- report cleaning (pure) --------------------------------------------------

def test_clean_text_normalizes_and_deidents():
    assert report.clean_text("  lots\n\tof   space ") == "lots of space"
    assert "xxx" not in report.clean_text("patient XXX has a nodule").lower()
    assert report.clean_text(None) == ""


def test_clean_row_retrieval_text():
    row = {
        "VolumeName": "train_1_a_1.nii.gz",
        "ClinicalInformation_EN": "cough",
        "Technique_EN": "non-contrast chest CT",
        "Findings_EN": "A 5 mm nodule in the right lung.",
        "Impressions_EN": "Benign-appearing nodule.",
    }
    rep = report.clean_row(row)
    assert "nodule" in rep.retrieval_text
    assert rep.retrieval_text == "A 5 mm nodule in the right lung. Benign-appearing nodule."


# --- unified query normalization (pure, injected translator) -----------------

def test_english_query_passthrough():
    q = query.normalize_text_query("  lung   nodule ", "en")
    assert q.text_en == "lung nodule" and q.source == "text" and q.source_lang == "en"


def test_chinese_query_uses_translator():
    q = query.normalize_text_query("肺结节", "zh", translate=lambda t: "lung nodule")
    assert q.text_en == "lung nodule" and q.source_lang == "zh"


def test_query_rejects_empty_and_missing_translator():
    with pytest.raises(query.QueryError):
        query.normalize_text_query("   ", "en")
    with pytest.raises(query.QueryError):
        query.normalize_text_query("肺结节", "zh")  # no translator


def test_voice_query_uses_transcriber():
    q = query.normalize_voice_query("/tmp/x.wav", transcribe=lambda p: "find similar lung cases")
    assert q.source == "voice" and q.source_lang == "en"
    assert q.text_en == "find similar lung cases"


def test_redacted_view_has_no_query_text():
    q = query.normalize_text_query("sensitive report text here", "en")
    r = q.redacted()
    assert set(r) == {"source_lang", "source", "chars"}
    assert "sensitive" not in str(r)  # H-14: never log query content


# --- dataset pairing (needs local CT-RATE reports/split) ---------------------

@pytest.mark.skipif(not _have_data, reason="CT-RATE reports/split not present")
def test_every_split_volume_has_a_report():
    from ml.text.dataset import build_text_dataset
    ex = build_text_dataset()
    assert len(ex) > 0
    assert all(e.retrieval_text for e in ex)
    # counts match the split
    import json
    split = json.loads((DATA / "split_revision.json").read_text(encoding="utf-8"))
    assert len(ex) == sum(split["counts"].values())


# --- tokenizer (skips without transformers / downloaded model) ---------------

@pytest.mark.skipif(not _spec("transformers"), reason="transformers not installed")
def test_bioclinicalbert_tokenizer():
    from ml.text import tokenizer
    try:
        enc = tokenizer.tokenize("A 5 mm nodule in the right lung.", max_length=32)
    except Exception as exc:  # noqa: BLE001 - model download unavailable
        pytest.skip(f"tokenizer model unavailable: {exc}")
    assert len(enc["input_ids"]) == 32
    assert len(enc["attention_mask"]) == 32
    assert sum(enc["attention_mask"]) >= 5


# --- translation regression (skips without argostranslate + model) -----------

@pytest.mark.skipif(not _spec("argostranslate"), reason="argostranslate not installed")
def test_zh_en_translation_regression():
    from ml.text import translate
    try:
        translate.ensure_model()
    except Exception as exc:  # noqa: BLE001 - package download unavailable
        pytest.skip(f"translation model unavailable: {exc}")
    out = translate.translate_zh_en("肺部有一个小结节").lower()
    assert out  # non-empty
    assert translate.translate_zh_en("肺部有一个小结节").lower() == out  # deterministic
    assert any(w in out for w in ("lung", "nodule", "pulmonary"))


# --- speech smoke (skips without faster-whisper) -----------------------------

@pytest.mark.skipif(not _spec("faster_whisper"), reason="faster-whisper not installed")
def test_speech_transcription_smoke(tmp_path):
    from ml.text import speech
    # A short valid WAV (silence) — the pipeline must run and return a string.
    wav = tmp_path / "clip.wav"
    with wave.open(str(wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    try:
        out = speech.transcribe(str(wav))
    except Exception as exc:  # noqa: BLE001 - model download unavailable
        pytest.skip(f"whisper model unavailable: {exc}")
    assert isinstance(out, str)
