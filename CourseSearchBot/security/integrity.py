"""
security/integrity.py
SHA-256 manifest verification for FAISS index tamper detection.
"""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime


class IntegrityError(RuntimeError):
    pass


class IndexIntegrityChecker:

    @staticmethod
    def compute_hash(file_path: str) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha.update(block)
        return sha.hexdigest()

    @classmethod
    def save_manifest(cls, index_path: str, manifest_path: str):
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        manifest = {
            "index_hash": cls.compute_hash(index_path),
            "created_at": datetime.utcnow().isoformat(),
            "index_path": os.path.basename(index_path),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    @classmethod
    def verify(cls, index_path: str, manifest_path: str) -> bool:
        if not os.path.exists(manifest_path):
            return False
        if not os.path.exists(index_path):
            return False
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return cls.compute_hash(index_path) == manifest.get("index_hash", "")
