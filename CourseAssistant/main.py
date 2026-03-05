import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

from api.db import init_db
from api.routes_admin import router as admin_router
from api.routes_analytics import router as analytics_router
from api.routes_auth import router as auth_router
from api.routes_chat import router as chat_router
from api.routes_files import router as files_router
from api.routes_graph import router as graph_router
from api.routes_settings import router as settings_router
from api.routes_upload import router as upload_router
from app_state import load_model


def configure_logging() -> None:
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s")
    file_handler = RotatingFileHandler("data/logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(console)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("App start")
    try:
        Path("data/logs").mkdir(parents=True, exist_ok=True)
        init_db()
        load_model()
        # Warmup runs in the background — server accepts connections immediately
        asyncio.create_task(_warmup_ollama())
        yield
    except Exception:
        logger.exception("Startup failed")
        raise
    finally:
        logger.info("App stop")


load_dotenv()


async def _warmup_ollama() -> None:
    """Pre-loads the llama3 model into Ollama memory so the first user request is fast."""
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    log = logging.getLogger(__name__)
    try:
        log.info("Warming up Ollama model '%s' — this may take 30-60 seconds...", model)
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)) as client:
            await client.post(
                f"{url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [{"role": "user", "content": "hi"}],
                    "options": {"num_predict": 1},
                },
            )
        log.info("Ollama warmup complete — AI is ready.")
    except Exception:
        log.warning("Ollama warmup skipped (Ollama may not be running yet).")


app = FastAPI(title="Prof. AI Assistant", version="1.0.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(analytics_router)
app.include_router(files_router)
app.include_router(graph_router)
app.include_router(settings_router)
app.include_router(admin_router)
