"""Text dataset builder (P10): pair CT volumes with cleaned reports.

Aligns the P7 patient-level split with cleaned CT-RATE reports so every training
volume has a stable English retrieval text. Verifies pairing completeness.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .report import CleanReport, load_reports

DATA_ROOT = Path("data/ct_rate")
SPLIT_JSON = DATA_ROOT / "split_revision.json"


@dataclass(frozen=True)
class TextExample:
    volume_name: str
    split: str
    retrieval_text: str


def build_text_dataset(
    split_json: Path = SPLIT_JSON, reports: dict[str, CleanReport] | None = None
) -> list[TextExample]:
    reports = reports if reports is not None else load_reports()
    split = json.loads(split_json.read_text(encoding="utf-8"))
    examples: list[TextExample] = []
    missing: list[str] = []
    for name, vols in split["volumes"].items():
        for vol in vols:
            rep = reports.get(vol)
            if rep is None or not rep.retrieval_text:
                missing.append(vol)
                continue
            examples.append(TextExample(vol, name, rep.retrieval_text))
    if missing:
        raise ValueError(f"{len(missing)} volumes lack a usable report (e.g. {missing[:3]})")
    return examples
