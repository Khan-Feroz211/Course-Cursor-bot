"""
security/sanitizer.py
Input validation and path safety — first line of defense.
"""
from __future__ import annotations
import re
from pathlib import Path


class SanitizationError(ValueError):
    pass


class InputSanitizer:
    MAX_QUERY_LENGTH = 500
    ALLOWED_EXTENSIONS = {".pdf"}

    @staticmethod
    def sanitize_query(query: str) -> str:
        if not isinstance(query, str):
            raise SanitizationError("Query must be a string.")
        query = re.sub(r"[\x00-\x1f\x7f]", "", query)
        query = re.sub(r"\s+", " ", query).strip()
        if not query:
            raise SanitizationError("Query is empty.")
        if len(query) > InputSanitizer.MAX_QUERY_LENGTH:
            raise SanitizationError(f"Query too long (max {InputSanitizer.MAX_QUERY_LENGTH} chars).")
        return query

    @staticmethod
    def validate_folder(path: str) -> Path:
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Folder not found: {resolved}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {resolved}")
        return resolved

    @staticmethod
    def is_safe_file(file_path: Path, base_dir: Path) -> bool:
        try:
            file_path.resolve().relative_to(base_dir.resolve())
            return file_path.suffix.lower() in InputSanitizer.ALLOWED_EXTENSIONS
        except ValueError:
            return False
