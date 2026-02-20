"""
core/search_engine.py
Semantic search engine — query embedding + FAISS ANN retrieval.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any

import numpy as np
import faiss

from config.config import AppConfig
from core.indexer import Indexer
from security.sanitizer import InputSanitizer, SanitizationError
from security.storage import MetadataStore

logger = logging.getLogger(__name__)


class SearchResult:
    __slots__ = ("file", "page", "context", "score")

    def __init__(self, file: str, page: int, context: str, score: float):
        self.file = file
        self.page = page
        self.context = context
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "page": self.page,
            "context": self.context,
            "score": round(self.score, 4),
        }


class SearchEngine:
    """
    Wraps the Indexer and MetadataStore to provide clean search().
    Handles threading-safe index loading and query validation.
    """

    def __init__(self, cfg: AppConfig, indexer: Indexer, store: MetadataStore):
        self.cfg = cfg
        self.indexer = indexer
        self.store = store
        self._index: faiss.Index | None = None

    @property
    def is_ready(self) -> bool:
        return self._index is not None

    def load_or_build(
        self, folder: str, progress_cb=None
    ) -> None:
        if self.indexer.needs_reindex(folder):
            self._index = self.indexer.build(folder, progress_cb=progress_cb)
        else:
            self._index = self.indexer.load()

    def search(self, raw_query: str) -> List[SearchResult]:
        if not self.is_ready:
            raise RuntimeError("Index not loaded. Please build the index first.")

        try:
            query = InputSanitizer.sanitize_query(raw_query)
        except SanitizationError as e:
            raise ValueError(str(e)) from e

        query_emb = self.indexer.model.encode([query])
        query_arr = np.array(query_emb).astype("float32")

        top_k = self.cfg.search.top_k
        distances, indices = self._index.search(query_arr, top_k)

        results: List[SearchResult] = []
        threshold = self.cfg.search.threshold

        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or dist > threshold:
                continue
            meta = self.store.fetch_chunk(int(idx))
            if not meta:
                continue
            score = max(0.0, 1.0 - (dist / threshold))
            results.append(
                SearchResult(
                    file=meta["file"],
                    page=meta["page"],
                    context=meta["context"],
                    score=score,
                )
            )

        logger.info(f"Query '{query[:60]}' → {len(results)} results.")
        return results
