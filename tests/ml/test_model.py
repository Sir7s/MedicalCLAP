"""P11 critical tests — retrieval model forward/backward, tiny-batch overfit,
loss stability, checkpoint reload, metrics vs random.

Requires torch + transformers (tiny random BERT, no download). Auto-skips where
those are absent (e.g. the CI ml lane); verified locally. The metrics module is
numpy-only and its tests always run.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.models import metrics as M  # noqa: E402  (numpy only)

_have_torch = importlib.util.find_spec("torch") is not None
_have_tf = importlib.util.find_spec("transformers") is not None
_MODEL = pytest.mark.skipif(not (_have_torch and _have_tf), reason="torch/transformers absent")


# --- metrics (numpy-only, always run) ----------------------------------------

def test_metrics_perfect_and_random():
    perfect = np.eye(5) * 10.0
    r = M.recall_at_k(perfect)
    assert r["recall@1"] == 1.0
    assert M.mean_average_precision(perfect) == 1.0
    assert M.ndcg(perfect) == 1.0
    # worst case: true match always ranked last
    worst = np.eye(4)[::-1] * 10.0  # diagonal is anti-diagonal -> rank varies
    assert M.mean_average_precision(worst) < 1.0


def test_bidirectional_shape():
    rng = np.random.default_rng(0)
    a = rng.random((6, 512))
    b = rng.random((6, 512))
    out = M.evaluate_bidirectional(a, b)
    assert "ct2txt_recall@1" in out and "txt2ct_map" in out


# --- model (torch) -----------------------------------------------------------

def _tiny_model(n_labels=18):
    from ml.models.pointnet2 import PointNet2Encoder
    from ml.models.retrieval import RetrievalModel
    from ml.models.text_encoder import build_tiny_text_encoder
    return RetrievalModel(PointNet2Encoder(out_dim=128),
                          build_tiny_text_encoder(out_dim=128), n_labels=n_labels,
                          out_dim=128)


@_MODEL
def test_forward_backward_shapes():
    import torch

    from ml.models.retrieval import make_random_batch
    model = _tiny_model()
    batch = make_random_batch(b=4, n_points=256, seq_len=16)
    ct, txt = model.encode(batch)
    assert ct.shape == (4, 128) and txt.shape == (4, 128)
    assert torch.allclose(ct.norm(dim=-1), torch.ones(4), atol=1e-4)  # L2-normalized
    loss, stats = model(batch)
    loss.backward()
    assert torch.isfinite(loss)
    assert any(p.grad is not None and torch.isfinite(p.grad).all()
               for p in model.parameters())


@_MODEL
def test_overfit_tiny_batch():
    """Exit gate: a fixed tiny batch is memorized — contrastive loss collapses
    and in-batch Recall@1 reaches 1.0 (>> random)."""
    import torch

    from ml.models.retrieval import fit_overfit, make_random_batch
    model = _tiny_model()
    batch = make_random_batch(b=4, n_points=256, seq_len=16, seed=1)
    hist = fit_overfit(model, batch, steps=200, lr=2e-3, seed=0)
    assert all(np.isfinite(h["loss"]) for h in hist)   # no NaN/Inf
    assert hist[-1]["contrastive"] < hist[0]["contrastive"] * 0.2  # collapsed
    # In-batch retrieval in train mode (consistent with training BN stats).
    model.train()
    with torch.no_grad():
        ct, txt = model.encode(batch)
    m = M.evaluate_bidirectional(ct.numpy(), txt.numpy())
    assert m["ct2txt_recall@1"] == 1.0
    assert m["txt2ct_recall@1"] == 1.0


@_MODEL
def test_checkpoint_reload_consistency():
    import torch

    from ml.models.retrieval import make_random_batch
    model = _tiny_model()
    batch = make_random_batch(b=3, n_points=256, seq_len=12, seed=2)
    model.eval()
    with torch.no_grad():
        ct0, txt0 = model.encode(batch)
    state = {k: v.clone() for k, v in model.state_dict().items()}

    reloaded = _tiny_model()
    reloaded.load_state_dict(state)
    reloaded.eval()
    with torch.no_grad():
        ct1, txt1 = reloaded.encode(batch)
    assert torch.allclose(ct0, ct1, atol=1e-5)
    assert torch.allclose(txt0, txt1, atol=1e-5)
