import logging

import faiss
import numpy as np

from core.indexer import load_index

logger = logging.getLogger(__name__)


def _keyword_fallback(chunks: list, query: str, top_k: int) -> list[dict]:
    """Simple keyword overlap fallback when vector search returns nothing."""
    q_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text = (chunk.get("text") or "").lower()
        overlap = sum(1 for w in q_words if w in text)
        if overlap > 0:
            scored.append((overlap, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, chunk in scored[:top_k]:
        item = dict(chunk)
        item["score"] = float(score) / max(len(q_words), 1)
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
                item = dict(chunks[i])
                item["score"] = float(s)
                out.append(item)
            if out:
                return out
            # Vector search returned nothing despite index existing — use keyword fallback
            logger.warning("Vector search returned no results for user=%s, trying keyword fallback", user_id)
            return _keyword_fallback(chunks, query, top_k)
        except Exception:
            logger.exception("Vector search failed for user=%s, falling back to keyword search", user_id)
            return _keyword_fallback(chunks, query, top_k)

    except Exception:
        logger.exception("Search failure for user=%s", user_id)
        return []
