import logging

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from core.indexer import load_index

logger = logging.getLogger(__name__)

# Minimum cosine similarity score to include a chunk in the answer context.
# Chunks below this are likely irrelevant noise.
SCORE_THRESHOLD = 0.25


def _bm25_fallback(chunks: list, query: str, top_k: int) -> list[dict]:
    """BM25 fallback — far better relevance ranking than raw keyword overlap."""
    tokenized_corpus = [(chunk.get("text") or "").lower().split() for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    q_tokens = query.lower().split()
    scores = bm25.get_scores(q_tokens)
    top_indices = scores.argsort()[::-1][:top_k]
    results = []
    for i in top_indices:
        if scores[i] > 0:
            item = dict(chunks[int(i)])
            item["score"] = float(scores[i])
            results.append(item)
    return results


def search(user_id: int, query: str, model, top_k: int = 5) -> list[dict]:
    if model is None:
        logger.error("Embedding model is None — cannot perform vector search for user=%s", user_id)
        return []  # caller will detect model unavailability separately
    try:
        index, chunks = load_index(user_id)
        if index is None or chunks is None:
            logger.info("No index found for user=%s", user_id)
            return []
        if index.ntotal == 0 or len(chunks) == 0:
            logger.info("Empty index for user=%s", user_id)
            return []

        try:
            q = model.encode([query])
            q_np = np.array(q, dtype=np.float32)
            faiss.normalize_L2(q_np)
            k = min(max(1, top_k), index.ntotal)
            scores, indices = index.search(q_np, k)
            out: list[dict] = []
            for i, s in zip(indices[0], scores[0]):
                if i < 0 or i >= len(chunks):
                    continue
                if float(s) < SCORE_THRESHOLD:
                    continue  # skip low-relevance chunks
                item = dict(chunks[i])
                item["score"] = float(s)
                out.append(item)
            if out:
                return out
            # All results below threshold — fall back to BM25
            logger.warning("Vector scores below threshold for user=%s, trying BM25 fallback", user_id)
            return _bm25_fallback(chunks, query, top_k)
        except Exception:
            logger.exception("Vector search failed for user=%s, falling back to BM25", user_id)
            return _bm25_fallback(chunks, query, top_k)

    except Exception:
        logger.exception("Search failure for user=%s", user_id)
        return []
