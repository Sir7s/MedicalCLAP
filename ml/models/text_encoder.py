"""BioClinicalBERT text encoder + projection (P11, SPEC-07 §8.3).

Produces a 512-d L2-normalized embedding from tokenized report text. The
transformer is injected so tests can use a tiny randomly-initialized BERT (no
440 MB download); real training uses `build_bioclinicalbert`.
"""
from __future__ import annotations

import torch.nn.functional as F
from torch import Tensor, nn


class TextEncoder(nn.Module):
    def __init__(self, bert: nn.Module, hidden_size: int, out_dim: int = 512):
        super().__init__()
        self.bert = bert
        self.proj = nn.Linear(hidden_size, out_dim)

    def forward(self, input_ids: Tensor, attention_mask: Tensor) -> Tensor:
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0]  # [CLS]
        return F.normalize(self.proj(cls), dim=-1)


def build_bioclinicalbert(out_dim: int = 512) -> TextEncoder:
    from transformers import AutoModel

    bert = AutoModel.from_pretrained("emilyalsentzer/Bio_ClinicalBERT")
    return TextEncoder(bert, bert.config.hidden_size, out_dim)


def build_tiny_text_encoder(out_dim: int = 512, vocab_size: int = 1000) -> TextEncoder:
    """Small random BERT for tests / overfit — no model download."""
    from transformers import BertConfig, BertModel

    cfg = BertConfig(
        vocab_size=vocab_size, hidden_size=64, num_hidden_layers=2,
        num_attention_heads=2, intermediate_size=128, max_position_embeddings=64,
    )
    return TextEncoder(BertModel(cfg), 64, out_dim)
