"""CT-RATE radiology report cleaning & segmentation (P10).

Produces the stable English text used both to build the training text dataset
and (via the tokenizer) as the report side of retrieval. Pure-stdlib and
deterministic. No report text is ever logged (H-14).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT = Path("data/ct_rate")
TRAIN_REPORTS = DATA_ROOT / "dataset" / "radiology_text_reports" / "train_reports.csv"

# Report columns in CT-RATE (English).
CLINICAL = "ClinicalInformation_EN"
TECHNIQUE = "Technique_EN"
FINDINGS = "Findings_EN"
IMPRESSIONS = "Impressions_EN"

_WS = re.compile(r"\s+")
_DEID = re.compile(r"\b(xxx+|___+|\[?\bredacted\b\]?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CleanReport:
    volume_name: str
    clinical: str
    technique: str
    findings: str
    impressions: str

    @property
    def retrieval_text(self) -> str:
        """The text used for retrieval: findings + impressions (the diagnostic core)."""
        parts = [p for p in (self.findings, self.impressions) if p]
        return " ".join(parts).strip()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = _DEID.sub(" ", value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = _WS.sub(" ", text)
    return text.strip()


def clean_row(row: dict) -> CleanReport:
    return CleanReport(
        volume_name=row["VolumeName"],
        clinical=clean_text(row.get(CLINICAL)),
        technique=clean_text(row.get(TECHNIQUE)),
        findings=clean_text(row.get(FINDINGS)),
        impressions=clean_text(row.get(IMPRESSIONS)),
    )


def load_reports(csv_path: Path = TRAIN_REPORTS) -> dict[str, CleanReport]:
    """Map VolumeName -> CleanReport for the whole reports CSV."""
    out: dict[str, CleanReport] = {}
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rep = clean_row(row)
            out[rep.volume_name] = rep
    return out
