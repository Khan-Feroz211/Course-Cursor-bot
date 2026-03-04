import logging
import os
import sqlite3
from pathlib import Path

import bcrypt
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

DB_PATH = Path("data/app.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                file_type TEXT,
                size_kb REAL,
                word_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'processing'
            );

            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                query_text TEXT NOT NULL,
                response_text TEXT,
                sources TEXT,
                response_time_ms INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        _create_default_accounts()
    finally:
        conn.close()


def _create_default_accounts() -> None:
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@2024")
    default_user_password = os.getenv("DEFAULT_USER_PASSWORD", "Prof@2024")
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count > 0:
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, 'admin', 1)",
            ("admin", bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")),
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, 'user', 1)",
            (
                "professor",
                bcrypt.hashpw(default_user_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            ),
        )
        conn.commit()
        logger.info("Default accounts created")
        print("✅ Default accounts created. Change passwords after first login.")
    finally:
        conn.close()
