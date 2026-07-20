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


def augment_points(points: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Stochastic point-cloud view (train only): resample-with-replacement drop,
    small z-rotation, coordinate jitter, mild scale, density jitter. Coords stay
    in [-1, 1], density in [0, 1]. Orientation-preserving (CT is standardized)."""
    n = points.shape[0]
    pts = points.copy()
    # point "dropout" that keeps N: resample ~15% of rows from the cloud.
    k = n // 7
    dst = rng.integers(0, n, size=k)
    src = rng.integers(0, n, size=k)
    pts[dst] = pts[src]
    xyz = pts[:, :3]
    theta = rng.uniform(-0.26, 0.26)  # ±15° about vertical (z) axis
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, -s], [s, c]], dtype=np.float32)
    xyz[:, :2] = xyz[:, :2] @ rot.T
    xyz += rng.normal(0.0, 0.01, size=xyz.shape).astype(np.float32)  # jitter
    xyz *= rng.uniform(0.95, 1.05)                                   # scale
    pts[:, :3] = np.clip(xyz, -1.0, 1.0)
    dnoise = np.asarray(rng.normal(0.0, 0.02, size=n), dtype=np.float32)
    pts[:, 3] = np.clip(pts[:, 3] + dnoise, 0.0, 1.0)
    return pts


class CtReportDataset:
    """Minimal indexable dataset (usable with torch DataLoader)."""

    def __init__(self, vols: list[str], reports, labels, tokenizer, seq_len: int,
                 n_labels: int, augment: bool = False):
        self.vols = vols
        self.reports = reports
        self.labels = labels
        self.tokenizer = tokenizer
        self.seq_len = seq_len
        self.n_labels = n_labels
        self.augment = augment
        self._rng = np.random.default_rng()

    def __len__(self) -> int:
        return len(self.vols)

    def __getitem__(self, i: int):
        vol = self.vols[i]
        points = np.load(CACHE / f"{vol}.npz")["points"].astype(np.float32)
        if self.augment:
            points = augment_points(points, self._rng)
        rep = self.reports.get(vol)
        text = rep.retrieval_text if rep else ""
        enc = self.tokenizer(text, truncation=True, max_length=self.seq_len,
                             padding="max_length", return_tensors=None)
        label = self.labels.get(vol, np.zeros(self.n_labels, dtype=np.float32))
        return (points, np.asarray(enc["input_ids"], dtype=np.int64),
                np.asarray(enc["attention_mask"], dtype=np.int64), label)


def build_datasets(config: TrainConfig, augment_train: bool = False):
    from ..text.report import load_reports
    from ..text.tokenizer import get_tokenizer
    subset = select_subset(config)
    reports = load_reports()
    labels, _cols = load_labels()
    tok = get_tokenizer()
    ds = {k: CtReportDataset(v, reports, labels, tok, config.seq_len, config.n_labels,
                             augment=(augment_train and k == "train"))
          for k, v in subset.items()}
    return ds, subset
