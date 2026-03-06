import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import app_state
from api.auth import require_login
from api.db import get_db
from core.answer_generator import stream_answer

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatPayload(BaseModel):
    query: str


@router.post("/chat")
def chat(request: Request, payload: ChatPayload):
    user = require_login(request)
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail={"error": "Query is required", "detail": "empty_query"})

    # Load last 3 conversation turns for multi-turn context
    history: list[dict] = []
    try:
        conn = get_db()
        hist_rows = conn.execute(
            """
            SELECT query_text, response_text FROM queries
            WHERE user_id=? AND response_text IS NOT NULL AND response_text != ''
            ORDER BY created_at DESC LIMIT 3
            """,
            (user["id"],),
        ).fetchall()
        conn.close()
        history = [{"query": r["query_text"], "response": r["response_text"]} for r in reversed(hist_rows)]
    except Exception:
        logger.warning("Could not load conversation history for user=%s", user["username"])

    async def event_stream():
        # Ensure embedding model is loaded (auto-retry at request time)
        if not app_state.ensure_model():
            yield 'data: {"type":"model_error","content":"\u23f3 AI search engine is still loading. Please wait 30 seconds and try again."}\n\n'
            yield 'data: {"type":"done"}\n\n'
            return

        started = time.perf_counter()
        answer_parts: list[str] = []
        sources = []
        try:
            logger.info("Query received user=%s text=%s", user["username"], query[:60])
            async for event in stream_answer(int(user["id"]), query, app_state.embedding_model, history=history):
                try:
                    if event.startswith("data: "):
                        event_obj = json.loads(event[6:].strip())  # renamed from payload_obj to avoid shadowing
                        etype = event_obj.get("type")
                        if etype == "token":
                            answer_parts.append(event_obj.get("content", ""))
                        elif etype == "sources":
                            sources = event_obj.get("content", []) or []
                except Exception:
                    logger.debug("Could not parse stream payload line")
                yield event
        except Exception:
            logger.exception("Chat stream wrapper failed")
            yield 'data: {"type":"error","content":"Unable to stream response"}\n\n'
            yield 'data: {"type":"done"}\n\n'
        finally:
            response_text = "".join(answer_parts).strip()
            duration_ms = int((time.perf_counter() - started) * 1000)
            try:
                conn = get_db()
                conn.execute(
                    """
                    INSERT INTO queries (user_id, query_text, response_text, sources, response_time_ms)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user["id"], query, response_text, json.dumps(sources), duration_ms),
                )
                conn.commit()
                conn.close()
            except Exception:
                logger.exception("Failed storing query history")
            logger.info("Query answered user=%s text=%s ms=%s", user["username"], query[:60], duration_ms)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/history")
def chat_history(request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT id, query_text, response_text, sources, response_time_ms, created_at
            FROM queries
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user["id"],),
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows]}
    except Exception as exc:
        logger.exception("History retrieval failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to load history", "detail": str(exc)})


@router.delete("/chat/history")
def clear_history(request: Request):
    user = require_login(request)
    try:
        conn = get_db()
        conn.execute("DELETE FROM queries WHERE user_id = ?", (user["id"],))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as exc:
        logger.exception("History clear failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to clear history", "detail": str(exc)})
