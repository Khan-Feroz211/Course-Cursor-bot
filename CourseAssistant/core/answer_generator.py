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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
AI_BACKEND = os.getenv("AI_BACKEND", "ollama").lower()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _use_groq() -> bool:
    return AI_BACKEND == "groq" and bool(GROQ_API_KEY)


async def _stream_groq(messages: list, sources: list):
    """Stream answer from Groq cloud API — fast, free, no local GPU needed."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    ) as client:
        try:
            async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": GROQ_MODEL,
                    "stream": True,
                    "max_tokens": 2048,
                    "messages": messages,
                },
            ) as response:
                if response.status_code == 401:
                    yield _sse({"type": "error", "content": "❌ Invalid Groq API key. Open your .env file and check GROQ_API_KEY."})
                    yield _sse({"type": "done"})
                    return
                if response.status_code == 429:
                    yield _sse({"type": "error", "content": "⏳ Groq rate limit reached. Please wait a moment and try again."})
                    yield _sse({"type": "done"})
                    return
                if response.status_code != 200:
                    yield _sse({"type": "error", "content": f"Groq API error ({response.status_code}). Please try again."})
                    yield _sse({"type": "done"})
                    return
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        token = data["choices"][0]["delta"].get("content", "")
                        if token:
                            yield _sse({"type": "token", "content": token})
                    except Exception:
                        continue
            yield _sse({"type": "sources", "content": sources})
            yield _sse({"type": "done"})
        except httpx.ConnectError:
            yield _sse({"type": "error", "content": "Cannot reach Groq API. Check your internet connection."})
            yield _sse({"type": "done"})
        except (httpx.ReadTimeout, httpx.TimeoutException):
            yield _sse({"type": "error", "content": "Groq API timed out. Please try again."})
            yield _sse({"type": "done"})
        except Exception:
            logger.exception("Groq streaming error")
            yield _sse({"type": "error", "content": "AI streaming error occurred."})
            yield _sse({"type": "done"})


async def _stream_ollama(messages: list, sources: list):
    """Stream answer from local Ollama instance."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
    ) as client:
        try:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "stream": True,
                    "options": {"num_predict": 1024, "num_ctx": 4096},
                    "messages": messages,
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
            logger.warning("Ollama timed out")
            yield _sse({"type": "error", "content": "AI is taking too long. The model may still be warming up — please try again in 30 seconds."})
            yield _sse({"type": "done"})
        except Exception:
            logger.exception("Ollama streaming error")
            yield _sse({"type": "error", "content": "AI streaming error occurred."})
            yield _sse({"type": "done"})


async def stream_answer(user_id: int, query: str, model, history: list[dict] | None = None):
    """
    history: list of {"query": str, "response": str} in chronological order.
    The last 3 exchanges are injected into the conversation so the LLM
    understands follow-up questions like "explain that further".
    """
    try:
        if model is None:
            yield _sse({"type": "model_error", "content": "⏳ Search engine is still initializing. Please wait 20 seconds and try again."})
            yield _sse({"type": "done"})
            return

        matches = search(user_id, query, model, top_k=8)
        if not matches:
            yield _sse({"type": "no_context", "content": "📂 No matching content found in your uploaded documents. Please upload relevant course files first."})
            yield _sse({"type": "done"})
            return

        sources = []
        context_lines: list[str] = []
        for idx, c in enumerate(matches, start=1):
            src = c.get("source_filename", "unknown")
            page = c.get("page", 1)
            text = c.get("text", "").strip()
            context_lines.append(f"[Source {idx} - {src}, Page {page}]\n{text}")
            sources.append({"filename": src, "page": page, "score": c.get("score", 0.0)})

        system_prompt = (
            "You are an academic assistant for a civil engineering professor. "
            "Answer using ONLY the context provided below. "
            "Give a thorough and complete answer — include all relevant details, definitions, steps, and explanations found in the context. "
            "Do not shorten or summarize unless the context itself is brief. "
            "Cite the source filename and page number for every key point. "
            "If the answer is not found in the context, say: 'Not found in uploaded documents.'"
        )
        prompt = f"CONTEXT:\n\n{chr(10).join(context_lines)}\n\nQUESTION: {query}"
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        # Inject last 3 conversation turns so the model understands follow-ups
        if history:
            for turn in history[-3:]:
                messages.append({"role": "user", "content": turn["query"]})
                messages.append({"role": "assistant", "content": turn["response"]})
        messages.append({"role": "user", "content": prompt})

        backend = "groq" if _use_groq() else "ollama"
        logger.info("AI backend: %s  user=%s", backend, user_id)
        if backend == "groq":
            async for event in _stream_groq(messages, sources):
                yield event
        else:
            async for event in _stream_ollama(messages, sources):
                yield event

    except Exception:
        logger.exception("Answer generation failed")
        yield _sse({"type": "error", "content": "Failed to generate answer."})
        yield _sse({"type": "done"})
