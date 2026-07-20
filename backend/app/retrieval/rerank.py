"""Findings-grounded explainable re-ranking (P13 serving side; AUP-004/AUP-005).

Reorders the recall stage's top-K by agreement between the query's findings and each
candidate's findings, and renders the shared findings as a human-readable reason.

    score = alpha * recall_score + (1 - alpha) * findings_match

Invariants (asserted in tests):
  * re-ranking only permutes the candidate pool -- it can never drop a hit, so the
    recall ceiling is preserved;
  * an explanation only ever cites findings that BOTH sides express.

Mirrors `ml/models/rerank.py` (the research implementation) but is dependency-free
so the backend does not import the ML stack.
"""
from __future__ import annotations

from dataclasses import dataclass

# CT-RATE 18 abnormality labels, in the dataset's column order.
FINDING_NAMES = [
    "Medical material", "Arterial wall calcification", "Cardiomegaly",
    "Pericardial effusion", "Coronary artery wall calcification", "Hiatal hernia",
    "Lymphadenopathy", "Emphysema", "Atelectasis", "Lung nodule", "Lung opacity",
    "Pulmonary fibrotic sequela", "Pleural effusion", "Mosaic attenuation pattern",
    "Peribronchial thickening", "Consolidation", "Bronchiectasis",
    "Interlobular septal thickening",
]
DEFAULT_ALPHA = 0.9   # tuned on held-out valid: light findings weight helps, heavy hurts
PRESENT = 0.5         # threshold for "this finding is expressed"


@dataclass
class RankedHit:
    volume: str
    score: float
    recall_score: float
    findings_match: float
    report: str
    explanation: list[str]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def shared_findings(query: list[float], candidate: list[float],
                    names: list[str] | None = None, thresh: float = PRESENT) -> list[str]:
    """Findings BOTH sides express -> the reason shown to the user."""
    names = names or FINDING_NAMES
    n = min(len(query), len(candidate), len(names))
    return [names[k] for k in range(n) if query[k] >= thresh and candidate[k] >= thresh]


def rerank(query_findings: list[float], hits: list, alpha: float = DEFAULT_ALPHA,
           names: list[str] | None = None) -> list[RankedHit]:
    """Reorder `hits` (objects with .volume/.score/.findings/.report) by the blend."""
    if not hits:
        return []
    alpha = min(max(alpha, 0.0), 1.0)
    recall_n = _minmax([h.score for h in hits])
    matches = [_cosine(query_findings, list(h.findings)) for h in hits]
    match_n = _minmax(matches)

    ranked = [
        RankedHit(
            volume=h.volume,
            score=alpha * recall_n[i] + (1.0 - alpha) * match_n[i],
            recall_score=float(h.score),
            findings_match=float(matches[i]),
            report=h.report,
            explanation=shared_findings(query_findings, list(h.findings), names),
        )
        for i, h in enumerate(hits)
    ]
    ranked.sort(key=lambda r: -r.score)
    return ranked
