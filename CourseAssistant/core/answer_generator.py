import json
import logging
import os

import httpx
from dotenv import load_dotenv

from core.search_engine import search

logger = logging.getLogger(__name__)

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_answer(user_id: int, query: str, model):
    try:
        # Guard: embedding model not loaded yet
        if model is None:
            yield _sse({"type": "model_error", "content": "⏳ Search engine is still initializing. Please wait 20 seconds and try again."})
            yield _sse({"type": "done"})
            return

        matches = search(user_id, query, model, top_k=6)
        if not matches:
            yield _sse({"type": "no_context", "content": "📂 No matching content found in your uploaded documents. Please upload relevant course files first."})
            yield _sse({"type": "done"})
            return

        sources = []
        context_lines: list[str] = []
        for idx, c in enumerate(matches, start=1):
            src = c.get("source_filename", "unknown")
            page = c.get("page", 1)
            context_lines.append(f"[Source {idx} - {src}, Page {page}]\n{c.get('text', '')}")
            sources.append({"filename": src, "page": page, "score": c.get("score", 0.0)})

        system_prompt = (
            "You are a personal academic assistant for a civil engineering professor. "
            "Answer questions based ONLY on the course material in the context below. "
            "Be precise, formal, and academic. Cite the document name and page number. "
            "If not found in context say: \"I could not find this in your uploaded documents.\" "
            "Never invent information."
        )
        prompt = f"CONTEXT:\n\n{chr(10).join(context_lines)}\n\nQUESTION: {query}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "stream": True,
                        "options": {"num_predict": 1024},
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                    },
                ) as response:
                    if response.status_code != 200:
                        yield _sse({"type": "error", "content": "AI model is unavailable. Please restart launcher."})
                        yield _sse({"type": "done"})
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue
                        token = data.get("message", {}).get("content")
                        if token:
                            yield _sse({"type": "token", "content": token})
                        if data.get("done"):
                            yield _sse({"type": "sources", "content": sources})
                            yield _sse({"type": "done"})
                            break
            except httpx.ConnectError:
                logger.warning("Ollama connection issue")
                yield _sse({"type": "error", "content": "Could not connect to Ollama. Please ensure it is running."})
                yield _sse({"type": "done"})
            except (httpx.ReadTimeout, httpx.TimeoutException):
                logger.warning("Ollama response timed out — model is still loading or too slow")
                yield _sse({"type": "error", "content": "AI is taking too long to respond. The model may still be warming up — please try again in 30 seconds."})
                yield _sse({"type": "done"})
            except Exception:
                logger.exception("Ollama streaming error")
                yield _sse({"type": "error", "content": "AI streaming error occurred."})
                yield _sse({"type": "done"})
    except Exception:
        logger.exception("Answer generation failed")
        yield _sse({"type": "error", "content": "Failed to generate answer."})
        yield _sse({"type": "done"})
