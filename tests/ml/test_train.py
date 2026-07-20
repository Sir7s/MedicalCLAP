"""P12 training-loop smoke test.

Exercises the real `train.train` end to end on tiny synthetic datasets (CPU,
no GPU, no dataset download): collate -> AMP-disabled loop -> best-checkpoint
selection -> held-out test eval -> metrics.json + model_card.md. Requires
torch + transformers so it auto-skips in the CI ml lane (verified locally).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

_have = (importlib.util.find_spec("torch") is not None
         and importlib.util.find_spec("transformers") is not None)
_TORCH = pytest.mark.skipif(not _have, reason="torch/transformers absent")


class _SynthDataset:
    """Mimics CtReportDataset.__getitem__ output with random tensors."""

    def __init__(self, n: int, n_points: int, seq_len: int, n_labels: int, seed: int):
        rng = np.random.default_rng(seed)
        self.items = [
            (rng.standard_normal((n_points, 4)).astype(np.float32),
             rng.integers(1, 500, size=seq_len).astype(np.int64),
             np.ones(seq_len, dtype=np.int64),
             (rng.random(n_labels) > 0.5).astype(np.float32))
            for _ in range(n)
        ]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def _fake_build(config):
    def make(n, seed):
        return _SynthDataset(n, config.n_points, config.seq_len, config.n_labels, seed)
    ds = {"train": make(config.n_train, 1), "val": make(config.n_val, 2),
          "test": make(config.n_test, 3)}
    subset = {"train": [f"t{i}" for i in range(config.n_train)],
              "val": [f"v{i}" for i in range(config.n_val)],
              "test": [f"e{i}" for i in range(config.n_test)]}
    return ds, subset


def _tiny_builder(config):
    """Tiny random BERT so no network download is needed."""
    from ml.models.pointnet2 import PointNet2Encoder
    from ml.models.retrieval import RetrievalModel
    from ml.models.text_encoder import build_tiny_text_encoder
    return RetrievalModel(PointNet2Encoder(out_dim=config.embed_dim),
                          build_tiny_text_encoder(out_dim=config.embed_dim),
                          n_labels=config.n_labels, out_dim=config.embed_dim,
                          aux_weight=config.aux_weight)


@_TORCH
def test_train_loop_smoke(tmp_path, monkeypatch):
    from ml.models import train as T
    from ml.models.train_config import TrainConfig

    cfg = TrainConfig(n_train=6, n_val=4, n_test=4, n_points=128, seq_len=12,
                      n_labels=18, batch_size=2, epochs=2, embed_dim=64,
                      device="cpu", amp=False, num_workers=0)
    monkeypatch.setattr(T, "build_datasets", _fake_build)
    monkeypatch.setattr(T, "build_model", _tiny_builder)

    out = tmp_path / "run"
    manifest = T.train(cfg, out, allow_cpu=True)

    assert (out / "best.pt").is_file()
    assert (out / "model_card.md").is_file()
    saved = json.loads((out / "metrics.json").read_text())
    assert saved["counts"] == {"train": 6, "val": 4, "test": 4}
    for key in ("ct2txt_recall@1", "txt2ct_recall@1", "ct2txt_map"):
        assert key in manifest["test"]
    # train log has one row per epoch
    rows = (out / "train_log.jsonl").read_text().strip().splitlines()
    assert len(rows) == cfg.epochs
    assert (out / "last.pt").is_file()  # resumable checkpoint written


@_TORCH
def test_train_resume(tmp_path, monkeypatch):
    """A 1-epoch run then a resumed run to 3 epochs continues from last.pt
    (start_epoch advances; the log accumulates rather than restarting)."""
    from ml.models import train as T
    from ml.models.train_config import DEFAULT, TrainConfig

    base = dict(n_train=6, n_val=4, n_test=4, n_points=128, seq_len=12, n_labels=18,
                batch_size=2, embed_dim=64, device="cpu", amp=False, num_workers=0)
    monkeypatch.setattr(T, "build_datasets", _fake_build)
    monkeypatch.setattr(T, "build_model", _tiny_builder)
    out = tmp_path / "run"

    T.train(TrainConfig(**{**DEFAULT.to_dict(), **base, "epochs": 1}), out, allow_cpu=True)
    import torch
    assert torch.load(out / "last.pt", map_location="cpu")["epoch"] == 0

    T.train(TrainConfig(**{**DEFAULT.to_dict(), **base, "epochs": 3}), out,
            allow_cpu=True, resume=True)
    assert torch.load(out / "last.pt", map_location="cpu")["epoch"] == 2
    rows = (out / "train_log.jsonl").read_text().strip().splitlines()
    assert len(rows) == 3  # 1 + 2 appended, not restarted
