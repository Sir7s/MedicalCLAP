"""BioClinicalBERT tokenizer pipeline (P10, SPEC-07 §8.3).

Wraps the public `emilyalsentzer/Bio_ClinicalBERT` tokenizer to produce padded
`input_ids` / `attention_mask`. Tokenization needs no PyTorch. The tokenizer is
loaded lazily and cached.
"""
from __future__ import annotations

MODEL_ID = "emilyalsentzer/Bio_ClinicalBERT"
MAX_LENGTH = 256

_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    return _tokenizer


def tokenize(text: str, max_length: int = MAX_LENGTH) -> dict:
    tok = get_tokenizer()
    enc = tok(
        text, truncation=True, max_length=max_length,
        padding="max_length", return_tensors=None,
    )
    return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"]}
