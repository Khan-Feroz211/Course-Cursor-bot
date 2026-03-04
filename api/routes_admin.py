import json
import logging
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from api.auth import hash_password, require_admin
from api.db import DB_PATH, get_db
from core.indexer import delete_user_data

logger = logging.getLogger(__name__)
router = APIRouter()
APP_START_TIME = datetime.utcnow()


class NewUserPayload(BaseModel):
    username: str
    password: str


class ResetPayload(BaseModel):
    password: str


def _uploads_size_kb() -> float:
    root = Path("data/users")
    total = 0
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return round(total / 1024.0, 2)


@router.get("/admin/health")
async def admin_health(request: Request):
    require_admin(request)
    try:
        ollama_running = False
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags")
                if r.status_code == 200:
                    ollama_running = True
                    tags = r.json().get("models", [])
                    if tags:
                        ollama_model = tags[0].get("name", ollama_model)
        except Exception:
            logger.warning("Ollama connection issue")

        conn = get_db()
        total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        active_today = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE DATE(last_login)=DATE('now')"
        ).fetchone()["c"]
        conn.close()
        uptime = str(datetime.utcnow() - APP_START_TIME).split(".")[0]
        return {
            "uptime": uptime,
            "ollama_running": ollama_running,
            "ollama_model": ollama_model,
            "db_size_kb": round(DB_PATH.stat().st_size / 1024.0, 2) if DB_PATH.exists() else 0,
            "uploads_size_kb": _uploads_size_kb(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "total_users": total_users,
            "active_today": active_today,
        }
    except Exception as exc:
        logger.exception("Admin health failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load health", "detail": str(exc)})


@router.get("/admin/users")
def admin_users(request: Request):
    require_admin(request)
    try:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.created_at, u.last_login, u.is_active,
                   COALESCE(d.doc_count,0) AS doc_count,
                   COALESCE(q.query_count,0) AS query_count
            FROM users u
            LEFT JOIN (
                SELECT user_id, COUNT(*) AS doc_count FROM documents GROUP BY user_id
            ) d ON d.user_id = u.id
            LEFT JOIN (
                SELECT user_id, COUNT(*) AS query_count FROM queries GROUP BY user_id
            ) q ON q.user_id = u.id
            ORDER BY u.id
            """
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows]}
    except Exception as exc:
        logger.exception("Admin users failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load users", "detail": str(exc)})


@router.post("/admin/users")
def create_user(request: Request, payload: NewUserPayload):
    require_admin(request)
    try:
        username = payload.username.strip()
        if not username:
            return {"error": "Username is required"}
        if len(payload.password or "") < 8:
            return {"error": "Password must be at least 8 characters"}
        conn = get_db()
        exists = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            conn.close()
            return {"error": "Username already exists"}
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, 'user', 1)",
            (username, hash_password(payload.password)),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as exc:
        logger.exception("Create user failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to create user", "detail": str(exc)})


@router.post("/admin/users/{uid}/reset-password")
def reset_user_password(uid: int, request: Request, payload: ResetPayload):
    require_admin(request)
    try:
        if len(payload.password or "") < 8:
            return {"error": "Password must be at least 8 characters"}
        conn = get_db()
        row = conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail={"error": "User not found", "detail": str(uid)})
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.password), uid))
        conn.commit()
        conn.close()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Reset password failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to reset password", "detail": str(exc)})


@router.post("/admin/users/{uid}/toggle")
def toggle_user(uid: int, request: Request):
    require_admin(request)
    try:
        conn = get_db()
        row = conn.execute("SELECT is_active FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail={"error": "User not found", "detail": str(uid)})
        new_state = 0 if int(row["is_active"]) == 1 else 1
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (new_state, uid))
        conn.commit()
        conn.close()
        return {"success": True, "is_active": new_state}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Toggle user failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to toggle user", "detail": str(exc)})


@router.delete("/admin/users/{uid}")
def delete_user(uid: int, request: Request):
    require_admin(request)
    try:
        conn = get_db()
        row = conn.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail={"error": "User not found", "detail": str(uid)})
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        conn.close()
        delete_user_data(uid)
        user_dir = Path(f"data/users/{uid}")
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Delete user failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to delete user", "detail": str(exc)})


@router.get("/admin/queries")
def admin_queries(
    request: Request,
    username: str = "",
    keyword: str = "",
    page: int = Query(default=1, ge=1),
):
    require_admin(request)
    try:
        page_size = 50
        offset = (page - 1) * page_size
        conn = get_db()
        sql = """
            SELECT q.id, q.query_text, q.response_text, q.response_time_ms, q.created_at, u.username
            FROM queries q
            JOIN users u ON u.id = q.user_id
            WHERE 1=1
        """
        params: list = []
        if username.strip():
            sql += " AND u.username LIKE ?"
            params.append(f"%{username.strip()}%")
        if keyword.strip():
            sql += " AND (q.query_text LIKE ? OR q.response_text LIKE ?)"
            params.extend([f"%{keyword.strip()}%", f"%{keyword.strip()}%"])
        sql += " ORDER BY q.created_at DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows], "page": page}
    except Exception as exc:
        logger.exception("Admin queries failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load queries", "detail": str(exc)})


@router.get("/admin/files")
def admin_files(request: Request):
    require_admin(request)
    try:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT u.username, d.filename, d.file_type, d.size_kb, d.upload_date, d.status
            FROM documents d
            JOIN users u ON u.id = d.user_id
            ORDER BY d.upload_date DESC
            """
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows]}
    except Exception as exc:
        logger.exception("Admin files failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load files", "detail": str(exc)})


@router.get("/admin/logs")
def admin_logs(request: Request):
    require_admin(request)
    try:
        path = Path("data/logs/app.log")
        if not path.exists():
            return {"logs": ""}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = "\n".join(lines[-500:])
        return {"logs": tail}
    except Exception as exc:
        logger.exception("Admin logs failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load logs", "detail": str(exc)})
