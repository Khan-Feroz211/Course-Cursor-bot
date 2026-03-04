import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.auth import check_password, hash_password, require_login
from api.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class PasswordPayload(BaseModel):
    current_password: str
    new_password: str


@router.get("/settings/me")
def settings_me(request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        doc_count = conn.execute("SELECT COUNT(*) c FROM documents WHERE user_id=?", (user["id"],)).fetchone()["c"]
        conn.close()
        uploads_dir = Path(f"data/users/{user['id']}/uploads")
        storage_kb = 0.0
        if uploads_dir.exists():
            storage_kb = sum(p.stat().st_size for p in uploads_dir.glob("*") if p.is_file()) / 1024.0
        return {
            "username": user["username"],
            "role": user["role"],
            "created_at": user["created_at"],
            "doc_count": doc_count,
            "storage_kb": round(storage_kb, 2),
        }
    except Exception as exc:
        logger.exception("Settings/me failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load settings", "detail": str(exc)})


@router.post("/settings/password")
def change_password(request: Request, payload: PasswordPayload):
    user = require_login(request)
    try:
        if len(payload.new_password or "") < 8:
            return {"error": "New password must be at least 8 characters."}
        conn = get_db()
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not check_password(payload.current_password, row["password_hash"]):
            conn.close()
            return {"error": "Current password is incorrect."}
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.new_password), user["id"]))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as exc:
        logger.exception("Password change failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to change password", "detail": str(exc)})
