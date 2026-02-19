"""
security/audit.py
Audit logging, rate limiting, and access control for security.
Critical for university/sensitive data environments.
"""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from collections import defaultdict
from functools import wraps
import sqlite3
import os

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs all sensitive operations to persistent storage for compliance."""
    
    def __init__(self, db_path: str = "data/audit.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_schema()
    
    def _init_schema(self):
        """Create audit log tables."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                action          TEXT NOT NULL,
                resource        TEXT,
                user_agent      TEXT,
                ip_address      TEXT,
                status          TEXT NOT NULL,
                details         TEXT,
                risk_level      TEXT DEFAULT 'INFO'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_action ON audit_logs(action)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_risk ON audit_logs(risk_level)
        """)
        conn.commit()
        conn.close()
    
    def log(
        self,
        action: str,
        status: str,
        resource: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict] = None,
        risk_level: str = "INFO",
    ):
        """Log a security-relevant action."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO audit_logs 
            (timestamp, action, resource, user_agent, ip_address, status, details, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                action,
                resource,
                user_agent,
                ip_address,
                status,
                json.dumps(details) if details else None,
                risk_level,
            ),
        )
        conn.commit()
        conn.close()
        
        # Log to application logger as well
        msg = f"[{risk_level}] {action} - {resource or 'N/A'}: {status}"
        if risk_level == "CRITICAL":
            logger.critical(msg)
        elif risk_level == "WARNING":
            logger.warning(msg)
        else:
            logger.info(msg)
    
    def get_logs(
        self,
        action_filter: Optional[str] = None,
        risk_filter: Optional[str] = None,
        hours: int = 24,
    ) -> list:
        """Retrieve audit logs."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM audit_logs WHERE timestamp > datetime('now', '-' || ? || ' hours')"
        params = [hours]
        
        if action_filter:
            query += " AND action = ?"
            params.append(action_filter)
        
        if risk_filter:
            query += " AND risk_level = ?"
            params.append(risk_filter)
        
        query += " ORDER BY timestamp DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        
        return [dict(row) for row in rows]


class RateLimiter:
    """Rate limiting to prevent abuse (DoS attacks, brute force, etc.)."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed for this identifier (IP, user, etc.)."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Remove old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier] 
            if req_time > cutoff
        ]
        
        # Check limit
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        self.requests[identifier].append(now)
        return True
    
    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for this identifier."""
        now = time.time()
        cutoff = now - self.window_seconds
        valid = [r for r in self.requests[identifier] if r > cutoff]
        return max(0, self.max_requests - len(valid))


class FileUploadValidator:
    """Validates uploaded files for security."""
    
    ALLOWED_EXTENSIONS = {".pdf"}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    DANGEROUS_SIGNATURES = {
        b"PK\x03\x04": "zip/exe",  # ZIP/executable header
        b"%PDF": "pdf",  # PDF is OK
    }
    
    @staticmethod
    def validate_upload(filename: str, content: bytes) -> tuple[bool, str]:
        """Validate uploaded file. Returns (is_valid, message)."""
        
        # Check extension
        if not any(filename.lower().endswith(ext) for ext in FileUploadValidator.ALLOWED_EXTENSIONS):
            return False, f"Only PDF files allowed. Got: {filename}"
        
        # Check file size
        if len(content) > FileUploadValidator.MAX_FILE_SIZE:
            return False, f"File too large. Max: {FileUploadValidator.MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        
        # Check file signature
        if not content.startswith(b"%PDF"):
            return False, "Invalid PDF file. File signature mismatch."
        
        # Check for embedded executables (advanced)
        if b"EmbeddedFile" in content:
            return False, "File contains embedded executable. Upload rejected for security."
        
        return True, "File valid"
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent directory traversal."""
        import re
        # Remove path separators and dangerous characters
        filename = re.sub(r"[/\\:\*\?\"<>|]", "_", filename)
        # Remove leading dots
        filename = re.sub(r"^\.+", "", filename)
        return filename[:255]  # Limit length


def rate_limit_route(max_requests: int = 100, window_seconds: int = 60):
    """Decorator to apply rate limiting to FastAPI routes."""
    limiter = RateLimiter(max_requests, window_seconds)
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request=None, **kwargs):
            if request:
                client_ip = request.client.host
                if not limiter.is_allowed(client_ip):
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded. Please try again later.",
                    )
            return await func(*args, request=request, **kwargs) if hasattr(func, '__await__') else func(*args, request=request, **kwargs)
        return wrapper
    return decorator


def require_user_agent(func):
    """Decorator to require a valid user agent."""
    @wraps(func)
    async def wrapper(*args, request=None, **kwargs):
        if request and not request.headers.get("user-agent"):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail="User-Agent header required",
            )
        return await func(*args, request=request, **kwargs) if hasattr(func, '__await__') else func(*args, request=request, **kwargs)
    return wrapper
