"""
config/config.py
Centralized configuration — single source of truth for all settings.
"""
from __future__ import annotations
import os
import yaml
import logging
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    name: str = "all-MiniLM-L6-v2"
    batch_size: int = 64


@dataclass
class IndexingConfig:
    chunk_size: int = 200
    ivf_threshold: int = 1000
    nlist: int = 100


@dataclass
class SearchConfig:
    top_k: int = 10
    max_results: int = 10  # Maximum PDF/document results to display (support up to 10)
    threshold: float = 1.5


@dataclass
class StorageConfig:
    db_path: str = "data/index_store.db"
    faiss_index: str = "data/doc_index.faiss"
    manifest: str = "data/index_manifest.json"


@dataclass
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path: str = "config/settings.yaml") -> "AppConfig":
        if not os.path.exists(path):
            logging.warning(f"Config not found at '{path}'. Using defaults.")
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls(
            model=ModelConfig(**raw.get("model", {})),
            indexing=IndexingConfig(**raw.get("indexing", {})),
            search=SearchConfig(**raw.get("search", {})),
            storage=StorageConfig(**raw.get("storage", {})),
            log_level=raw.get("logging", {}).get("level", "INFO"),
        )

    def ensure_dirs(self):
        for p in [self.storage.db_path, self.storage.faiss_index, self.storage.manifest]:
            os.makedirs(os.path.dirname(p), exist_ok=True)
