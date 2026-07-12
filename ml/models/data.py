"""Training dataset: CT point-cloud cache + tokenized report + labels (P12).

Preprocesses the chosen split subset to a `.npz` point-cloud cache (via the P9
pipeline), pairs each volume with its cleaned report (P10) and CT-RATE
multi-abnormality labels, and serves tensors for training.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import numpy as np

from ..datasets.ct_rate.select import volume_repo_path
from .train_config import TrainConfig

# Data root is configurable so the same code runs locally and in the cloud
# (Colab/Kaggle mount their dataset/Drive at a different path).
DATA = Path(os.environ.get("MEDCLIP_DATA_ROOT", "data/ct_rate"))
# The point-cloud cache can live on faster/persistent storage (e.g. Google Drive
# in Colab) independently of the raw volumes, via MEDCLIP_CACHE_DIR.
CACHE = Path(os.environ["MEDCLIP_CACHE_DIR"]) if os.environ.get("MEDCLIP_CACHE_DIR") \
    else DATA / "pointcloud_cache"
VOL_ROOT = DATA / "volumes"
SPLIT_JSON = DATA / "split_revision.json"
LABELS_CSV = DATA / "dataset" / "multi_abnormality_labels" / "train_predicted_labels.csv"


def load_labels() -> tuple[dict[str, np.ndarray], list[str]]:
    with LABELS_CSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = [c for c in (reader.fieldnames or []) if c != "VolumeName"]
        out: dict[str, np.ndarray] = {}
        for row in reader:
            out[row["VolumeName"]] = np.array([float(row[c]) for c in cols], dtype=np.float32)
    return out, cols


def volume_path(vol: str) -> Path:
    return VOL_ROOT / volume_repo_path(vol)


def cache_pointcloud(vol: str, n_points: int, seed: int) -> Path:
    out = CACHE / f"{vol}.npz"
    if out.is_file():
        return out
    from ..preprocessing.config import PreprocConfig
    from ..preprocessing.ct_pointcloud import preprocess
    cfg = PreprocConfig(n_points=n_points, seed=seed)
    pc = preprocess(volume_path(vol), cfg)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    with tmp.open("wb") as fh:  # explicit handle: numpy won't append its own .npz
        np.savez_compressed(fh, points=pc.points)
    tmp.replace(out)
    return out


def select_subset(config: TrainConfig) -> dict[str, list[str]]:
    split = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    return {
        "train": split["volumes"]["train"][: config.n_train],
        "val": split["volumes"]["val"][: config.n_val],
        "test": split["volumes"]["test"][: config.n_test],
    }


def prepare_cache(config: TrainConfig, subset: dict[str, list[str]]) -> None:
    """Preprocess every subset volume to the point-cloud cache (idempotent)."""
    done = 0
    total = sum(len(v) for v in subset.values())
    for vols in subset.values():
        for vol in vols:
            cache_pointcloud(vol, config.n_points, config.seed)
            done += 1
            if done % 10 == 0:
                _log_prep(done, total)
    _log_prep(total, total)


def _log_prep(done: int, total: int) -> None:
    (CACHE / "_progress.json").parent.mkdir(parents=True, exist_ok=True)
    (DATA / "prepare_progress.json").write_text(
        json.dumps({"cached": done, "total": total}), encoding="utf-8"
    )


class CtReportDataset:
    """Minimal indexable dataset (usable with torch DataLoader)."""

    def __init__(self, vols: list[str], reports, labels, tokenizer, seq_len: int, n_labels: int):
        self.vols = vols
        self.reports = reports
        self.labels = labels
        self.tokenizer = tokenizer
        self.seq_len = seq_len
        self.n_labels = n_labels

    def __len__(self) -> int:
        return len(self.vols)

    def __getitem__(self, i: int):
        vol = self.vols[i]
        points = np.load(CACHE / f"{vol}.npz")["points"].astype(np.float32)
        rep = self.reports.get(vol)
        text = rep.retrieval_text if rep else ""
        enc = self.tokenizer(text, truncation=True, max_length=self.seq_len,
                             padding="max_length", return_tensors=None)
        label = self.labels.get(vol, np.zeros(self.n_labels, dtype=np.float32))
        return (points, np.asarray(enc["input_ids"], dtype=np.int64),
                np.asarray(enc["attention_mask"], dtype=np.int64), label)


def build_datasets(config: TrainConfig):
    from ..text.report import load_reports
    from ..text.tokenizer import get_tokenizer
    subset = select_subset(config)
    reports = load_reports()
    labels, _cols = load_labels()
    tok = get_tokenizer()
    ds = {k: CtReportDataset(v, reports, labels, tok, config.seq_len, config.n_labels)
          for k, v in subset.items()}
    return ds, subset
