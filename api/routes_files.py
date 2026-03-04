import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

import app_state
from api.auth import require_login
from api.db import get_db
from core.file_processor import chunk_pages, extract_text
from core.indexer import build_index, delete_user_data

logger = logging.getLogger(__name__)
router = APIRouter()


def _rebuild_user_index(user_id: int) -> int:
    conn = get_db()
    rows = conn.execute(
        "SELECT filename, file_type FROM documents WHERE user_id=? AND status='indexed' ORDER BY upload_date",
        (user_id,),
    ).fetchall()
    conn.close()
    all_chunks = []
    for r in rows:
        p = Path(f"data/users/{user_id}/uploads/{r['filename']}")
        if not p.exists():
            continue
        try:
            pages = extract_text(p, (r["file_type"] or "").lower())
            all_chunks.extend(chunk_pages(pages))
        except Exception:
            logger.exception("Failed rebuilding chunk from file=%s", r["filename"])
    if all_chunks:
        build_index(user_id, all_chunks, app_state.embedding_model)
    else:
        delete_user_data(user_id)
    return len(all_chunks)


@router.get("/files")
def list_files(request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT id, filename, file_type, size_kb, word_count, chunk_count, upload_date, status
            FROM documents
            WHERE user_id=?
            ORDER BY upload_date DESC
            """,
            (user["id"],),
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows]}
    except Exception as exc:
        logger.exception("Files list failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load files", "detail": str(exc)})


@router.delete("/files/{doc_id}")
def delete_file(doc_id: int, request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT id, filename FROM documents WHERE id=? AND user_id=?",
            (doc_id, user["id"]),
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail={"error": "File not found", "detail": "invalid_doc_id"})
        file_path = Path(f"data/users/{user['id']}/uploads/{row['filename']}")
        if file_path.exists():
            file_path.unlink()
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        _rebuild_user_index(int(user["id"]))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("File delete failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to delete file", "detail": str(exc)})


@router.post("/rebuild-index")
def rebuild_index(request: Request):
    user = require_login(request)
    try:
        chunks = _rebuild_user_index(int(user["id"]))
        logger.info("Index rebuild user=%s chunks=%s", user["username"], chunks)
        return {"success": True, "chunks": chunks}
    except Exception as exc:
        logger.exception("Index rebuild failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to rebuild index", "detail": str(exc)})
