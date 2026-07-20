"""P12a pretraining smoke test.

Exercises `pretrain.pretrain` end to end on tiny synthetic data (CPU, no GPU, no
dataset) and confirms it exports a CT-encoder state_dict that the P12 retrieval
trainer can load via `train(init_ct_encoder=...)`. torch/transformers required so
it auto-skips in the CI ml lane (verified locally).
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


class _SynthClsDataset:
    def __init__(self, n, n_points, n_labels, seed):
        rng = np.random.default_rng(seed)
        self.items = [(rng.standard_normal((n_points, 4)).astype(np.float32),
                       (rng.random(n_labels) > 0.5).astype(np.float32)) for _ in range(n)]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


@_TORCH
def test_pretrain_exports_encoder(tmp_path, monkeypatch):
    from ml.models import pretrain as P
    from ml.models.train_config import DEFAULT, TrainConfig

    cfg = TrainConfig(**{**DEFAULT.to_dict(), "n_points": 128, "n_labels": 18,
                         "batch_size": 2, "epochs": 2, "embed_dim": 64,
                         "device": "cpu", "amp": False, "num_workers": 0})

    def fake_build(config):
        ds_tr = _SynthClsDataset(6, config.n_points, config.n_labels, 1)
        ds_va = _SynthClsDataset(4, config.n_points, config.n_labels, 2)
        return ds_tr, ds_va, {"pretrain_train": 6, "pretrain_val": 4}

    monkeypatch.setattr(P, "build_pretrain_datasets", fake_build)
    out = tmp_path / "p12a"
    manifest = P.pretrain(cfg, out, allow_cpu=True)

    enc = out / "encoder.pt"
    assert enc.is_file()
    assert (out / "last.pt").is_file()
    saved = json.loads((out / "pretrain_metrics.json").read_text())
    assert saved["counts"] == {"pretrain_train": 6, "pretrain_val": 4}
    assert manifest["best_epoch"] >= 0
    rows = (out / "pretrain_log.jsonl").read_text().strip().splitlines()
    assert len(rows) == cfg.epochs

    # The exported encoder loads into a fresh PointNet++ of the same shape.
    import torch

    from ml.models.pointnet2 import PointNet2Encoder
    fresh = PointNet2Encoder(out_dim=cfg.embed_dim)
    fresh.load_state_dict(torch.load(enc, map_location="cpu"))


@_TORCH
def test_retrieval_accepts_pretrained_encoder(tmp_path, monkeypatch):
    """train(init_ct_encoder=...) loads P12a weights without shape errors."""
    import torch

    from ml.models import train as T
    from ml.models.pointnet2 import PointNet2Encoder
    from ml.models.train_config import DEFAULT, TrainConfig
    from tests.ml.test_train import _fake_build, _tiny_builder

    cfg = TrainConfig(**{**DEFAULT.to_dict(), "n_train": 6, "n_val": 4, "n_test": 4,
                         "n_points": 128, "seq_len": 12, "n_labels": 18, "batch_size": 2,
                         "epochs": 1, "embed_dim": 64, "device": "cpu", "amp": False,
                         "num_workers": 0})
    enc_path = tmp_path / "encoder.pt"
    torch.save(PointNet2Encoder(out_dim=cfg.embed_dim).state_dict(), enc_path)

    monkeypatch.setattr(T, "build_datasets", _fake_build)
    monkeypatch.setattr(T, "build_model", _tiny_builder)
    manifest = T.train(cfg, tmp_path / "run", allow_cpu=True, init_ct_encoder=enc_path)
    assert manifest["ct_encoder_init"] == str(enc_path)
