import json
import logging
import re
from collections import Counter

from fastapi import APIRouter, HTTPException, Request

from api.auth import require_login
from api.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

STOP_WORDS = {
    "what",
    "where",
    "when",
    "which",
    "that",
    "this",
    "from",
    "with",
    "have",
    "does",
    "your",
    "about",
    "some",
    "more",
    "than",
    "into",
    "over",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z]{3,}", text.lower()) if w not in STOP_WORDS]


@router.get("/analytics")
def get_analytics(request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        total_docs = conn.execute("SELECT COUNT(*) c FROM documents WHERE user_id=?", (user["id"],)).fetchone()["c"]
        total_queries = conn.execute("SELECT COUNT(*) c FROM queries WHERE user_id=?", (user["id"],)).fetchone()["c"]
        avg_response_ms = conn.execute(
            "SELECT COALESCE(AVG(response_time_ms),0) a FROM queries WHERE user_id=?", (user["id"],)
        ).fetchone()["a"]

        q_rows = conn.execute(
            "SELECT query_text, created_at, response_time_ms, sources FROM queries WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        d_rows = conn.execute(
            "SELECT filename, file_type FROM documents WHERE user_id=? ORDER BY upload_date DESC", (user["id"],)
        ).fetchall()

        kw_counter: Counter = Counter()
        for r in q_rows:
            kw_counter.update(_tokenize(r["query_text"] or ""))
        most_searched = kw_counter.most_common(1)[0][0] if kw_counter else "N/A"
        top_keywords = [{"word": w, "count": c} for w, c in kw_counter.most_common(10)]

        type_counter = Counter((r["file_type"] or "unknown").lower() for r in d_rows)
        file_type_dist = [{"type": k, "count": v} for k, v in type_counter.items()]

        qpd = conn.execute(
            """
            SELECT DATE(created_at) date, COUNT(*) count
            FROM queries
            WHERE user_id=? AND created_at >= datetime('now','-30 day')
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
            """,
            (user["id"],),
        ).fetchall()
        queries_per_day = [{"date": r["date"], "count": r["count"]} for r in qpd]

        cited = Counter()
        recent_queries = []
        for r in q_rows[:20]:
            srcs = []
            try:
                srcs = json.loads(r["sources"] or "[]")
            except Exception:
                srcs = []
            for s in srcs:
                fn = s.get("filename")
                if fn:
                    cited[fn] += 1
            recent_queries.append(
                {
                    "time": r["created_at"],
                    "question": r["query_text"],
                    "response_time": r["response_time_ms"] or 0,
                    "sources": len(srcs),
                }
            )
        top_docs = [{"filename": f, "count": c} for f, c in cited.most_common(5)]
        conn.close()

        return {
            "total_docs": total_docs,
            "total_queries": total_queries,
            "avg_response_ms": int(avg_response_ms or 0),
            "most_searched": most_searched,
            "top_keywords": top_keywords,
            "file_type_dist": file_type_dist,
            "queries_per_day": queries_per_day,
            "top_docs": top_docs,
            "recent_queries": recent_queries,
        }
    except Exception as exc:
        logger.exception("Analytics route failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load analytics", "detail": str(exc)})
