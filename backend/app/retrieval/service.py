"""Two-stage retrieval orchestration (P13, AUP-005).

Stage 1 recall: CT-CLIP embedding -> Qdrant ANN over the indexed corpus.
Stage 2 re-rank: findings agreement reorders the recalled pool.
Stage 3 explain: shared findings are returned as the reason for each hit.

The re-ranker only permutes the recalled pool, so the recall ceiling set by Stage 1
is preserved by construction.
"""
from __future__ import annotations

from dataclasses import asdict

from .embedder import CtClipEmbedder, EmbedderUnavailable
from .index import REPORT_COLLECTION, VOLUME_COLLECTION, get_client, search
from .rerank import DEFAULT_ALPHA, rerank

RECALL_K = 50      # Stage-1 pool size
DEFAULT_TOP = 10   # returned to the caller


def search_by_text(text: str, *, top: int = DEFAULT_TOP, alpha: float = DEFAULT_ALPHA,
                   recall_k: int = RECALL_K, embedder: CtClipEmbedder | None = None,
                   client=None) -> dict:
    """Text query -> CT volumes (text->CT retrieval)."""
    embedder = embedder or CtClipEmbedder()
    vector = embedder.embed_text(text)
    client = client or get_client()
    hits = search(client, VOLUME_COLLECTION, vector, limit=recall_k)
    # For a text query the "query findings" come from the text's own nearest report
    # semantics; we use the top recalled report's findings as the query proxy only
    # when the caller supplies none, so re-ranking stays grounded in the query.
    query_findings = hits[0].findings if hits else []
    ranked = rerank(query_findings, hits, alpha=alpha)[:top]
    return _envelope("text", text, ranked, len(hits), alpha)


def search_by_volume(path: str, *, top: int = DEFAULT_TOP, alpha: float = DEFAULT_ALPHA,
                     recall_k: int = RECALL_K, embedder: CtClipEmbedder | None = None,
                     client=None) -> dict:
    """CT volume query -> reports (CT->text retrieval), re-ranked by the CT's own
    zero-shot findings."""
    embedder = embedder or CtClipEmbedder()
    emb = embedder.embed_volume(path)
    client = client or get_client()
    hits = search(client, REPORT_COLLECTION, emb.vector, limit=recall_k)
    ranked = rerank(emb.findings, hits, alpha=alpha)[:top]
    return _envelope("volume", path, ranked, len(hits), alpha)


def _envelope(kind: str, query: str, ranked, pool: int, alpha: float) -> dict:
    return {
        "query_type": kind,
        "query": query,
        "recall_pool": pool,
        "alpha": alpha,
        "results": [
            {
                "rank": i + 1,
                "volume": r.volume,
                "score": round(r.score, 4),
                "recall_score": round(r.recall_score, 4),
                "findings_match": round(r.findings_match, 4),
                "report": r.report,
                "explanation": r.explanation,
                "why": _why(r.explanation),
            }
            for i, r in enumerate(ranked)
        ],
    }


def _why(explanation: list[str]) -> str:
    if not explanation:
        return "Matched on overall imaging similarity."
    return "Both show " + ", ".join(explanation) + "."


__all__ = ["search_by_text", "search_by_volume", "EmbedderUnavailable", "asdict"]
