"""History export (P15).

Renders a saved history record to a downloadable artifact. Two formats:

* **json** — the full record verbatim (query, every hit, scores, explanations).
* **csv**  — one row per retrieved hit, for spreadsheet review.

Every export carries the research-use disclaimer, and CSV fields are sanitised
against spreadsheet formula injection (a leading `=`, `+`, `-` or `@` is escaped).
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

DISCLAIMER = (
    "Research and demonstration use only. "
    "Not intended for clinical diagnosis or treatment decisions."
)
CSV_COLUMNS = [
    "rank", "volume", "score", "recall_score", "findings_match", "explanation", "report",
]
_RISKY = ("=", "+", "-", "@")


def _safe_cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection without altering the text meaning."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in _RISKY else text


def _results_of(record: dict) -> list[dict]:
    payload = record.get("payload") or record.get("meta") or {}
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
    return []


def to_json(record: dict) -> str:
    body = dict(record)
    body["disclaimer"] = DISCLAIMER
    return json.dumps(body, ensure_ascii=False, indent=2)


def to_csv(record: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([f"# {DISCLAIMER}"])
    writer.writerow([f"# title: {record.get('title', '')}"])
    writer.writerow(CSV_COLUMNS)
    for r in _results_of(record):
        writer.writerow([
            _safe_cell(r.get("rank")),
            _safe_cell(r.get("volume")),
            _safe_cell(r.get("score")),
            _safe_cell(r.get("recall_score")),
            _safe_cell(r.get("findings_match")),
            _safe_cell("; ".join(r.get("explanation") or [])),
            _safe_cell((r.get("report") or "").replace("\n", " ").strip()),
        ])
    return buf.getvalue()


def render(record: dict, fmt: str) -> tuple[str, str, str]:
    """Return (body, media_type, filename) for the requested format."""
    fmt = (fmt or "json").lower()
    stem = str(record.get("id", "history"))
    if fmt == "csv":
        return to_csv(record), "text/csv; charset=utf-8", f"{stem}.csv"
    if fmt == "json":
        return to_json(record), "application/json; charset=utf-8", f"{stem}.json"
    raise ValueError(f"unsupported export format: {fmt}")
