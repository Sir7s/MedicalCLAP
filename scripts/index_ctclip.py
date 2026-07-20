"""Index cached CT-CLIP embeddings into Qdrant (P13).

Reads the `.npz` cache produced by the CT-CLIP extraction (img / txt / zs / lab per
volume) and upserts two collections: `ct_volumes` (image embeddings, searched by a
text query) and `ct_reports` (report embeddings, searched by a CT query).

    python scripts/index_ctclip.py --cache D:/ctclip_work/ctclip_valid_cache
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[0].parent / "backend"))

from app.retrieval.index import (  # noqa: E402
    ensure_collections,
    get_client,
    upsert_reports,
    upsert_volumes,
)

REPORTS_CSV = Path("data/ct_rate/dataset/radiology_text_reports/validation_reports.csv")


def load_reports() -> dict[str, str]:
    out: dict[str, str] = {}
    if REPORTS_CSV.is_file():
        with REPORTS_CSV.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out[row["VolumeName"]] = (
                    f"{row.get('Findings_EN', '')} {row.get('Impressions_EN', '')}".strip()
                )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="D:/ctclip_work/ctclip_valid_cache")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = sorted(Path(args.cache).glob("*.npz"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"no cached embeddings under {args.cache}")

    reports = load_reports()
    client = get_client()
    ensure_collections(client)

    vol_recs, rep_recs = [], []
    for i, f in enumerate(files):
        d = np.load(f)
        vol = f.name.replace(".npz", "")
        findings = d["zs"].astype(float).tolist() if "zs" in d else []
        labels = d["lab"].astype(float).tolist() if "lab" in d else []
        text = reports.get(vol, "")
        # volumes collection: image embedding, payload carries zero-shot findings
        vol_recs.append({"id": i, "vector": d["img"].astype(float).tolist(),
                         "volume": vol, "report": text, "findings": findings})
        # reports collection: report embedding, payload carries the report's labels
        rep_recs.append({"id": i, "vector": d["txt"].astype(float).tolist(),
                         "volume": vol, "report": text, "findings": labels})

    n_v = upsert_volumes(client, vol_recs)
    n_r = upsert_reports(client, rep_recs)
    print(f"indexed {n_v} volumes and {n_r} reports from {args.cache}")


if __name__ == "__main__":
    main()
