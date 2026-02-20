"""
core/indexer.py
ML document indexer — extraction, chunking, embedding, FAISS index building.
"""
from __future__ import annotations
import os
import hashlib
import logging
import re
from typing import List, Dict, Tuple, Callable, Optional

import numpy as np
import faiss
import pdfplumber
from sentence_transformers import SentenceTransformer

from config.config import AppConfig
from security.storage import MetadataStore
from security.integrity import IndexIntegrityChecker
from security.sanitizer import InputSanitizer

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.info("pytesseract not available — OCR disabled.")


class Indexer:
    """
    Responsible for:
      1. Detecting file changes (MD5 hashing)
      2. Extracting & chunking PDF text
      3. Embedding chunks (SentenceTransformer)
      4. Building / persisting FAISS index
      5. Verifying index integrity on load
    """

    def __init__(self, cfg: AppConfig, store: MetadataStore):
        self.cfg = cfg
        self.store = store
        self.model = SentenceTransformer(cfg.model.name)

    # ── Hashing ───────────────────────────────────────────────────────────────

    def _hash_file(self, path: str) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    def _current_hashes(self, folder: str) -> Dict[str, str]:
        base = InputSanitizer.validate_folder(folder)
        return {
            fn: self._hash_file(str(base / fn))
            for fn in os.listdir(base)
            if fn.lower().endswith(".pdf")
        }

    def needs_reindex(self, folder: str) -> bool:
        current = self._current_hashes(folder)
        stored = self.store.load_hashes()
        if current != stored:
            logger.info("File changes detected — re-index required.")
            return True
        index_ok = os.path.exists(self.cfg.storage.faiss_index)
        integrity_ok = IndexIntegrityChecker.verify(
            self.cfg.storage.faiss_index, self.cfg.storage.manifest
        )
        if not index_ok or not integrity_ok:
            logger.warning("FAISS index missing or integrity check failed — re-index required.")
            return True
        logger.info("No changes detected — loading existing index.")
        return False

    # ── Extraction ────────────────────────────────────────────────────────────

    def _extract_page_text(self, page) -> str:
        text = page.extract_text() or ""
        if not text.strip() and OCR_AVAILABLE:
            logger.debug("OCR fallback triggered.")
            img = page.to_image().original
            text = pytesseract.image_to_string(img)
        return re.sub(r"\s+", " ", text).strip()

    def extract_chunks(self, folder: str) -> Tuple[List[str], List[Dict]]:
        base = InputSanitizer.validate_folder(folder)
        chunks, meta = [], []
        pdf_files = [f for f in os.listdir(base) if f.lower().endswith(".pdf")]

        if not pdf_files:
            raise ValueError("No PDF files found in the selected folder.")

        for filename in pdf_files:
            fp = base / filename
            if not InputSanitizer.is_safe_file(fp, base):
                logger.warning(f"Skipping unsafe file: {filename}")
                continue
            try:
                with pdfplumber.open(str(fp)) as pdf:
                    for page_num, page in enumerate(pdf.pages, start=1):
                        text = self._extract_page_text(page)
                        if not text:
                            continue
                        words = text.split()
                        size = self.cfg.indexing.chunk_size
                        for i in range(0, len(words), size):
                            chunk = " ".join(words[i : i + size])
                            chunks.append(chunk)
                            meta.append({
                                "file": filename,
                                "page": page_num,
                                "chunk_start": i,
                                "chunk_text": chunk,
                                "file_hash": self._hash_file(str(fp)),
                            })
            except Exception as e:
                logger.error(f"Failed to process '{filename}': {e}")

        return chunks, meta

    # ── Index building ────────────────────────────────────────────────────────

    def build(
        self,
        folder: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> faiss.Index:
        chunks, meta = self.extract_chunks(folder)
        if not chunks:
            raise ValueError("No text could be extracted from the documents.")

        total = len(chunks)
        logger.info(f"Embedding {total} chunks…")

        embeddings = self.model.encode(
            chunks,
            batch_size=self.cfg.model.batch_size,
            show_progress_bar=False,
        )

        if progress_cb:
            progress_cb(total // 2, total)

        emb_arr = np.array(embeddings).astype("float32")
        dim = emb_arr.shape[1]

        if total > self.cfg.indexing.ivf_threshold:
            logger.info(f"Large dataset ({total} chunks) — using IVF index.")
            nlist = self.cfg.indexing.nlist
            quantizer = faiss.IndexFlatL2(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, nlist)
            index.train(emb_arr)
        else:
            index = faiss.IndexFlatL2(dim)

        index.add(emb_arr)

        # Persist
        os.makedirs(os.path.dirname(self.cfg.storage.faiss_index), exist_ok=True)
        faiss.write_index(index, self.cfg.storage.faiss_index)
        IndexIntegrityChecker.save_manifest(
            self.cfg.storage.faiss_index, self.cfg.storage.manifest
        )

        # Store metadata safely in SQLite
        self.store.clear_chunks()
        self.store.insert_chunks(meta)
        self.store.save_hashes(self._current_hashes(folder))

        if progress_cb:
            progress_cb(total, total)

        logger.info("Index built and saved successfully.")
        return index

    def load(self) -> faiss.Index:
        if not IndexIntegrityChecker.verify(
            self.cfg.storage.faiss_index, self.cfg.storage.manifest
        ):
            raise IntegrityError("Index integrity check failed. Please rebuild the index.")
        return faiss.read_index(self.cfg.storage.faiss_index)


class IntegrityError(RuntimeError):
    pass
