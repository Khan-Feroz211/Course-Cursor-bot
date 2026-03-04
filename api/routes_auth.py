import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.auth import check_password, create_session_token, get_current_user
from api.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _read_html(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


@router.get("/")
def root(request: Request):
    try:
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        return RedirectResponse("/admin" if user["role"] == "admin" else "/app", status_code=302)
    except Exception:
        logger.exception("Root route failed")
        return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page():
    try:
        return HTMLResponse(_read_html("ui/login.html"))
    except Exception:
        logger.exception("Failed to load login page")
        return HTMLResponse("<h1>Login page unavailable</h1>", status_code=500)


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    try:
        conn = get_db()
        try:
            user = conn.execute(
                "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
            if not user or int(user["is_active"]) != 1 or not check_password(password, user["password_hash"]):
                logger.warning("Failed login attempt: %s", username)
                return RedirectResponse("/login?error=1", status_code=302)
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            conn.commit()
        finally:
            conn.close()
        token = create_session_token(int(user["id"]))
        target = "/admin" if user["role"] == "admin" else "/app"
        response = RedirectResponse(target, status_code=302)
        response.set_cookie(
            "session",
            token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        logger.info("User login: %s", username)
        return response
    except Exception:
        logger.exception("Login route failed")
        return RedirectResponse("/login?error=1", status_code=302)


@router.get("/logout")
def logout(request: Request):
    try:
        user = get_current_user(request)
        if user:
            logger.info("User logout: %s", user["username"])
    except Exception:
        logger.exception("Failed to load user for logout")
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


@router.get("/app", response_class=HTMLResponse)
def app_page(request: Request):
    try:
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        if user["role"] != "user":
            return RedirectResponse("/admin", status_code=302)
        return HTMLResponse(_read_html("ui/app.html"))
    except Exception:
        logger.exception("Failed to load app page")
        return RedirectResponse("/login", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    try:
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        if user["role"] != "admin":
            return RedirectResponse("/app", status_code=302)
        return HTMLResponse(_read_html("ui/admin.html"))
    except Exception:
        logger.exception("Failed to load admin page")
        return RedirectResponse("/login", status_code=302)
