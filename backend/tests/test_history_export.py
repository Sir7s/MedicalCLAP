"""P15 — history export rendering (JSON/CSV), incl. CSV injection hardening."""
from __future__ import annotations

import csv
import io
import json

import pytest

from app.history import export


def _record():
    return {
        "id": "rec-1",
        "title": "effusion search",
        "payload": {
            "query": "large pleural effusion",
            "results": [
                {"rank": 1, "volume": "a.nii.gz", "score": 0.91, "recall_score": 0.88,
                 "findings_match": 0.72, "explanation": ["Pleural effusion", "Cardiomegaly"],
                 "report": "Bilateral effusion.\nEnlarged heart."},
                {"rank": 2, "volume": "b.nii.gz", "score": 0.77, "recall_score": 0.80,
                 "findings_match": 0.31, "explanation": [], "report": "Clear study."},
            ],
        },
    }


def test_json_export_is_valid_and_carries_disclaimer():
    body, media, name = export.render(_record(), "json")
    assert media.startswith("application/json")
    assert name.endswith(".json")
    parsed = json.loads(body)
    assert parsed["disclaimer"] == export.DISCLAIMER
    assert len(parsed["payload"]["results"]) == 2


def test_csv_export_has_one_row_per_hit_with_explanations():
    body, media, name = export.render(_record(), "csv")
    assert media.startswith("text/csv")
    assert name.endswith(".csv")
    rows = list(csv.reader(io.StringIO(body)))
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "rank")
    data = [r for r in rows[header_idx + 1:] if r]
    assert len(data) == 2
    assert data[0][1] == "a.nii.gz"
    assert "Pleural effusion; Cardiomegaly" in data[0][5]
    assert "\n" not in data[0][6]          # report newlines flattened for CSV


def test_csv_escapes_formula_injection():
    rec = _record()
    rec["payload"]["results"][0]["volume"] = "=cmd|'/c calc'!A1"
    body, _, _ = export.render(rec, "csv")
    rows = list(csv.reader(io.StringIO(body)))
    cell = next(r[1] for r in rows if len(r) > 1 and "cmd" in r[1])
    assert cell.startswith("'"), "risky leading character must be escaped"


def test_disclaimer_present_in_csv():
    body, _, _ = export.render(_record(), "csv")
    assert export.DISCLAIMER in body


def test_unsupported_format_rejected():
    with pytest.raises(ValueError):
        export.render(_record(), "pdf")


def test_record_without_results_still_exports():
    body, _, _ = export.render({"id": "x", "title": "empty", "payload": {}}, "csv")
    assert "rank" in body  # header still written
