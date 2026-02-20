"""
security/storage.py
SQLite-backed metadata store. Zero pickle — no arbitrary code execution risk.
"""
from __future__ import annotations
import sqlite3
import os
from typing import List, Dict, Any


class MetadataStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                file     TEXT    NOT NULL,
                page     INTEGER NOT NULL,
                chunk_start INTEGER NOT NULL,
                chunk_text  TEXT NOT NULL,
                file_hash   TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_hashes (
                filename TEXT PRIMARY KEY,
                md5      TEXT NOT NULL
            )
        """)
        self._conn.commit()

    # ── Chunks ────────────────────────────────────────────────────────────────

    def clear_chunks(self):
        self._conn.execute("DELETE FROM chunks")
        self._conn.commit()

    def insert_chunks(self, rows: List[Dict[str, Any]]):
        self._conn.executemany(
            "INSERT INTO chunks (file, page, chunk_start, chunk_text, file_hash) "
            "VALUES (:file, :page, :chunk_start, :chunk_text, :file_hash)",
            rows,
        )
        self._conn.commit()

    def fetch_chunk(self, chunk_id: int) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT file, page, chunk_text FROM chunks WHERE id = ?", (chunk_id + 1,)
        ).fetchone()
        if row:
            return {"file": row[0], "page": row[1], "context": row[2]}
        return {}

    def count_chunks(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # ── File hashes ───────────────────────────────────────────────────────────

    def save_hashes(self, hashes: Dict[str, str]):
        self._conn.execute("DELETE FROM file_hashes")
        self._conn.executemany(
            "INSERT INTO file_hashes (filename, md5) VALUES (?, ?)",
            hashes.items(),
        )
        self._conn.commit()

    def load_hashes(self) -> Dict[str, str]:
        rows = self._conn.execute("SELECT filename, md5 FROM file_hashes").fetchall()
        return dict(rows)

    def close(self):
        self._conn.close()
