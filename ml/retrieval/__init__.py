"""Retrieval index, content digest, and evaluation (P13, SPEC-07 §7.4/§7.5/§8.2-8.7).

P13 = Qdrant Index & Real Retrieval Integration. This package is built now
against PLACEHOLDER embeddings (see `embeddings.load_embeddings`) so the index,
digest, search, and evaluation code can be developed and tested before the real
CT/Text encoders (P11-P12) land. Swapping in the real model is a one-line change
in `embeddings.py`.

WIP: P13 depends on P12 (Master Plan P13 前置条件 "P12 生效"). The repo is at P9,
so this stays a work-in-progress branch and is NOT an official phase exit until
P12 is merged and coordinated with the project owner.
"""

EMBED_DIM = 512
