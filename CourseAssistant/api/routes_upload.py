import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

import app_state
from api.auth import require_login
from api.db import get_db
from core.file_processor import chunk_pages, extract_text
from core.indexer import build_index, load_index

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTS = {"pdf", "docx", "pptx", "xlsx", "xls", "csv", "txt", "jpg", "jpeg", "png"}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB — protects RAM and disk on low-storage machine


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    user = require_login(request)
    # Guard: embedding model must be ready before we can index anything
    if not app_state.ensure_model():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Search engine is still initialising. Please wait 30 seconds and try again.",
                "detail": "model_not_ready",
            },
        )
    filename = file.filename or "uploaded_file"
    doc_id = None
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTS:
        logger.warning("File type not supported: %s", ext)
        raise HTTPException(status_code=400, detail={"error": "Unsupported file type", "detail": ext})
    try:
        content = await file.read()  # async read — does not block event loop

        # --- Storage guard ---
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"error": f"File too large. Maximum allowed size is 50 MB.", "detail": "file_too_large"},
            )

        safe_name = Path(filename).name
        size_kb = round(len(content) / 1024.0, 2)

        # --- Duplicate detection ---
        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM documents WHERE user_id=? AND filename=? AND status='indexed'",
                (user["id"], safe_name),
            ).fetchone()
        finally:
            conn.close()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"error": f"'{safe_name}' is already indexed. Delete it first if you want to re-upload.", "detail": "duplicate_file"},
            )

        user_dir = Path(f"data/users/{user['id']}")
        uploads_dir = user_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        path = uploads_dir / safe_name
        path.write_bytes(content)

        conn = get_db()
        try:
            cur = conn.execute(
                """
                INSERT INTO documents (user_id, filename, file_type, size_kb, status)
                VALUES (?, ?, ?, ?, 'processing')
                """,
                (user["id"], safe_name, ext, size_kb),
            )
            doc_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        logger.info("File upload start user=%s filename=%s", user["username"], safe_name)

        # Run CPU-heavy processing in thread pool — keeps event loop responsive
        # so chat and other requests are not blocked during OCR / embedding
        pages = await asyncio.to_thread(extract_text, path, ext)
        chunks = await asyncio.to_thread(chunk_pages, pages)
        word_count = sum(len((p.get("text") or "").split()) for p in pages)
        _, existing_chunks = load_index(int(user["id"]))
        merged_chunks = (existing_chunks or []) + chunks
        await asyncio.to_thread(build_index, int(user["id"]), merged_chunks, app_state.embedding_model)

        conn = get_db()
        try:
            conn.execute(
                "UPDATE documents SET status='indexed', word_count=?, chunk_count=? WHERE id=?",
                (word_count, len(chunks), doc_id),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            "File upload complete user=%s filename=%s chunks=%s",
            user["username"],
            safe_name,
            len(chunks),
        )
        return {"success": True, "filename": safe_name, "chunks": len(chunks), "words": word_count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("File processing failure filename=%s", filename)
        try:
            conn = get_db()
            if doc_id is not None:
                conn.execute("UPDATE documents SET status='error' WHERE id=?", (doc_id,))
                conn.commit()
            conn.close()
        except Exception:
            logger.exception("Could not update document status to error")
        raise HTTPException(status_code=500, detail={"error": "Failed to process file", "detail": str(exc)})
