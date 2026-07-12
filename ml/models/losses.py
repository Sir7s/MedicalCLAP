"""Training objectives (P11, SPEC-07 §8.4).

Bidirectional CLIP-style contrastive loss (CT<->report) + a CT-RATE
multi-label abnormality classification auxiliary loss.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor


def clip_contrastive_loss(ct_emb: Tensor, txt_emb: Tensor, logit_scale: Tensor) -> Tensor:
    """Symmetric InfoNCE over an in-batch similarity matrix. Embeddings are
    assumed L2-normalized; positives are the matching diagonal."""
    logits = logit_scale * ct_emb @ txt_emb.t()   # (B, B)
    labels = torch.arange(logits.shape[0], device=logits.device)
    loss_ct = F.cross_entropy(logits, labels)     # CT -> report
    loss_txt = F.cross_entropy(logits.t(), labels)  # report -> CT
    return (loss_ct + loss_txt) / 2


def multilabel_aux_loss(logits: Tensor, targets: Tensor) -> Tensor:
    """Binary cross-entropy over the abnormality label set."""
    return F.binary_cross_entropy_with_logits(logits, targets.float())
