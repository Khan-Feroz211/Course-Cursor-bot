import logging
import os
from typing import Any, Optional

import bcrypt
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer

from api.db import get_db

logger = logging.getLogger(__name__)

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-to-a-long-random-string")
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_AGE_SECONDS = 7 * 24 * 60 * 60


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": int(user_id)})


def verify_session_token(token: str) -> Optional[int]:
    try:
        payload = serializer.loads(token, max_age=SESSION_AGE_SECONDS)
        uid = payload.get("uid")
        return int(uid) if uid is not None else None
    except Exception:
        return None


def get_current_user(request: Request) -> Optional[dict[str, Any]]:
    token = request.cookies.get("session")
    if not token:
        return None
    user_id = verify_session_token(token)
    if user_id is None:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, role, created_at, last_login, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row or int(row["is_active"]) != 1:
            return None
        return dict(row)
    finally:
        conn.close()


def require_login(request: Request) -> dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = require_login(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
