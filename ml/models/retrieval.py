"""Combined retrieval model + tiny training loop (P11).

Wraps the PointNet++ CT encoder and the BioClinicalBERT text encoder with a
learnable temperature and an auxiliary multi-label classifier on the CT
embedding. `fit_overfit` trains on a fixed tiny batch to prove the objective
optimizes (the P11 exit gate).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor, nn

from .losses import clip_contrastive_loss, multilabel_aux_loss
from .metrics import evaluate_bidirectional


@dataclass
class Batch:
    points: Tensor          # (B, N, 4)
    input_ids: Tensor       # (B, L)
    attention_mask: Tensor  # (B, L)
    labels: Tensor          # (B, n_labels)


class RetrievalModel(nn.Module):
    def __init__(self, ct_encoder: nn.Module, text_encoder: nn.Module,
                 n_labels: int, out_dim: int = 512, aux_weight: float = 1.0):
        super().__init__()
        self.ct_encoder = ct_encoder
        self.text_encoder = text_encoder
        self.classifier = nn.Linear(out_dim, n_labels)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))
        self.aux_weight = aux_weight

    def encode(self, batch: Batch) -> tuple[Tensor, Tensor]:
        ct = self.ct_encoder(batch.points)
        txt = self.text_encoder(batch.input_ids, batch.attention_mask)
        return ct, txt

    def forward(self, batch: Batch) -> tuple[Tensor, dict[str, float]]:
        ct, txt = self.encode(batch)
        scale = self.logit_scale.exp().clamp(max=100.0)
        contrastive = clip_contrastive_loss(ct, txt, scale)
        aux = multilabel_aux_loss(self.classifier(ct), batch.labels)
        loss = contrastive + self.aux_weight * aux
        return loss, {"loss": float(loss.detach()),
                      "contrastive": float(contrastive.detach()),
                      "aux": float(aux.detach())}

    @torch.no_grad()
    def eval_metrics(self, batch: Batch) -> dict[str, float]:
        self.eval()
        ct, txt = self.encode(batch)
        return evaluate_bidirectional(ct.cpu().numpy(), txt.cpu().numpy())


def fit_overfit(model: RetrievalModel, batch: Batch, *, steps: int = 200,
                lr: float = 1e-3, seed: int = 0) -> list[dict[str, float]]:
    """Overfit a single fixed batch; returns per-step loss history."""
    torch.manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    history: list[dict[str, float]] = []
    model.train()
    for _ in range(steps):
        opt.zero_grad()
        loss, stats = model(batch)
        if not torch.isfinite(loss):
            raise ValueError(f"non-finite loss: {stats}")
        loss.backward()
        opt.step()
        history.append(stats)
    return history


def make_random_batch(b: int = 4, n_points: int = 512, n_labels: int = 18,
                      vocab_size: int = 1000, seq_len: int = 16, seed: int = 0) -> Batch:
    g = torch.Generator().manual_seed(seed)
    points = torch.rand(b, n_points, 4, generator=g) * 2 - 1
    points[..., 3] = (points[..., 3] + 1) / 2  # density in [0,1]
    input_ids = torch.randint(1, vocab_size, (b, seq_len), generator=g)
    attention_mask = torch.ones(b, seq_len, dtype=torch.long)
    labels = (torch.rand(b, n_labels, generator=g) > 0.5).long()
    return Batch(points, input_ids, attention_mask, labels)


def numpy_seed(seed: int) -> None:
    np.random.seed(seed)
