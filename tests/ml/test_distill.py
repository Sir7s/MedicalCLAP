"""P12b distillation smoke test.

Runs `distill.distill` on tiny synthetic data (CPU, no GPU, no CT-FM download —
`skip_extract=True` + monkeypatched datasets) and confirms it exports a
CT-encoder state_dict loadable by a fresh PointNet++. torch/transformers required
so it auto-skips in the CI ml lane.
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


class _SynthDistill:
    def __init__(self, n, n_points, embed_dim, n_labels, seed):
        rng = np.random.default_rng(seed)
        self.items = [(rng.standard_normal((n_points, 4)).astype(np.float32),
                       rng.standard_normal(embed_dim).astype(np.float32),
                       (rng.random(n_labels) > 0.5).astype(np.float32)) for _ in range(n)]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


@_TORCH
def test_distill_exports_encoder(tmp_path, monkeypatch):
    import torch

    from ml.models import distill as D
    from ml.models.pointnet2 import PointNet2Encoder
    from ml.models.train_config import DEFAULT, TrainConfig

    cfg = TrainConfig(**{**DEFAULT.to_dict(), "n_points": 128, "n_labels": 18,
                         "batch_size": 2, "epochs": 2, "embed_dim": 64,
                         "device": "cpu", "amp": False, "num_workers": 0})

    def fake_ds(config):
        def mk(n, s):
            return _SynthDistill(n, config.n_points, config.embed_dim, config.n_labels, s)
        return mk(6, 1), mk(4, 2), {"distill_train": 6, "distill_val": 4}

    monkeypatch.setattr(D, "build_distill_datasets", fake_ds)
    out = tmp_path / "p12b"
    manifest = D.distill(cfg, out, allow_cpu=True, skip_extract=True)

    enc = out / "encoder.pt"
    assert enc.is_file()
    assert manifest["counts"] == {"distill_train": 6, "distill_val": 4}
    saved = json.loads((out / "distill_metrics.json").read_text())
    assert "CT-FM" in saved["teacher"]
    rows = (out / "distill_log.jsonl").read_text().strip().splitlines()
    assert len(rows) == cfg.epochs

    fresh = PointNet2Encoder(out_dim=cfg.embed_dim)
    fresh.load_state_dict(torch.load(enc, map_location="cpu"))
