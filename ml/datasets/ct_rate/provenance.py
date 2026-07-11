"""CT-RATE provenance & license record (P7, SPEC-06 §7.2)."""
from __future__ import annotations

import json
from pathlib import Path

DATA_ROOT = Path("data/ct_rate")
PROVENANCE_JSON = DATA_ROOT / "PROVENANCE.json"

RECORD = {
    "dataset": "CT-RATE",
    "source_organization": "Hamamci et al. (CT-RATE authors)",
    "source_url": "https://huggingface.co/datasets/ibrahimhamamci/CT-RATE",
    "citation": "Hamamci et al., CT-RATE: A 3D chest CT and radiology report dataset.",
    "license": "CT-RATE dataset terms (research use; gated access on HuggingFace)",
    "access": "gated (HuggingFace) — access accepted by the user before download",
    "training_allowed": True,
    "redistribution_allowed": False,
    "commercial_use_allowed": False,
    "deidentification_status": "de-identified by dataset authors",
    "scope_used": "Chest CT only; train_fixed volumes; radiology text reports; "
                  "multi-abnormality labels; acquisition metadata",
    "excluded": [
        "ts_seg (TotalSegmentator masks — out of scope for retrieval)",
        "models/ and models_deprecated/ (CT-CHAT / CT-CLIP weights — never loaded "
        "into PointNet++ per architecture rule)",
    ],
    "privacy_rule": "Raw volumes and report text are stored only under the "
                    "git-ignored data/ tree and are never committed (H-13/H-14). "
                    "Only manifests/hashes/counts are tracked in the repository.",
}


def write_provenance() -> Path:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    PROVENANCE_JSON.write_text(json.dumps(RECORD, indent=2) + "\n", encoding="utf-8")
    return PROVENANCE_JSON


if __name__ == "__main__":
    print("wrote", write_provenance())
