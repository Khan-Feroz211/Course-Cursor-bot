import logging

import faiss
import numpy as np

from core.indexer import load_index

logger = logging.getLogger(__name__)


def search(user_id: int, query: str, model, top_k: int = 5) -> list[dict]:
    try:
        index, chunks = load_index(user_id)
        if index is None or chunks is None:
            return []
        if index.ntotal == 0:
            return []
        q = model.encode([query])
        q_np = np.array(q, dtype=np.float32)
        faiss.normalize_L2(q_np)
        k = min(max(1, top_k), index.ntotal)
        scores, indices = index.search(q_np, k)
        out: list[dict] = []
        for i, s in zip(indices[0], scores[0]):
            if i < 0:
                continue
            item = dict(chunks[i])
            item["score"] = float(s)
            out.append(item)
        return out
    except Exception:
        logger.exception("Search failure for user=%s", user_id)
        return []
