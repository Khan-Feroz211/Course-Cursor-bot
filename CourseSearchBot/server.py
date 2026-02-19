"""
server.py
Course Search Bot — Web Server Mode (for Docker / always-alive deployment)
Runs a FastAPI REST API so the app stays alive as a background service.
Access the UI at: http://localhost:8000
"""
from __future__ import annotations
import logging
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

os.makedirs("course_docs", exist_ok=True)
os.makedirs("data", exist_ok=True)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from config.config import AppConfig
from core.indexer import Indexer
from core.search_engine import SearchEngine
from security.storage import MetadataStore

# ── Setup ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cfg = AppConfig.from_yaml("config/settings.yaml")
cfg.ensure_dirs()

store   = MetadataStore(cfg.storage.db_path)
indexer = Indexer(cfg, store)
engine  = SearchEngine(cfg, indexer, store)

app = FastAPI(
    title="Course Search Bot",
    description="AI-powered semantic search for university course PDFs",
    version="2.0.0",
)

# ── Request/Response models ───────────────────────────────────────────────────

class IndexRequest(BaseModel):
    folder: str = "course_docs"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10

class SearchResultItem(BaseModel):
    file: str
    page: int
    context: str
    score: float

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Docker health check endpoint — keeps the container alive."""
    return {"status": "ok", "index_ready": engine.is_ready}


@app.post("/index")
def build_index(req: IndexRequest):
    """Build or reload the document index."""
    try:
        engine.load_or_build(req.folder)
        count = store.count_chunks()
        return {"status": "success", "chunks_indexed": count}
    except Exception as e:
        logger.error(f"Index error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=list[SearchResultItem])
def search(req: SearchRequest):
    """Run a semantic search query."""
    if not engine.is_ready:
        raise HTTPException(status_code=400, detail="Index not loaded. Call /index first.")
    try:
        results = engine.search(req.query)
        return [r.to_dict() for r in results]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
def status():
    """Get current system status."""
    return {
        "index_ready": engine.is_ready,
        "chunks_count": store.count_chunks(),
        "model": cfg.model.name,
        "version": "2.0.0",
    }


@app.get("/", response_class=HTMLResponse)
def root():
    """Simple web UI — accessible from any browser."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Course Search Bot</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e8eaf0; font-family: 'Segoe UI', sans-serif; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 40px 20px; }
  h1 { font-size: 2rem; margin-bottom: 8px; color: #4f8ef7; }
  p.sub { color: #8890a8; margin-bottom: 32px; }
  .card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px; padding: 24px; width: 100%; max-width: 700px; margin-bottom: 20px; }
  input, button { width: 100%; padding: 12px 16px; border-radius: 8px; border: none; font-size: 1rem; margin-top: 10px; }
  input { background: #0f1117; color: #e8eaf0; border: 1px solid #2a2d3e; }
  button { background: #4f8ef7; color: white; cursor: pointer; font-weight: 600; transition: background .2s; }
  button:hover { background: #7c5cbf; }
  #results { white-space: pre-wrap; font-family: monospace; font-size: 0.85rem; color: #e8eaf0; max-height: 400px; overflow-y: auto; }
  .badge { display: inline-block; background: #7c5cbf; color: white; padding: 3px 10px; border-radius: 20px; font-size: 0.8rem; margin-top: 8px; }
  label { color: #8890a8; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>🎓 Course Search Bot</h1>
<p class="sub">AI-powered semantic search for your course documents</p>

<div class="card">
  <label>Step 1 — Build Index</label>
  <button onclick="buildIndex()">⚙ Build / Reload Index</button>
  <div id="index_status" style="margin-top:10px;color:#3ecf8e;"></div>
</div>

<div class="card">
  <label>Step 2 — Search</label>
  <input id="query" type="text" placeholder="e.g. what is photosynthesis?" onkeydown="if(event.key==='Enter')search()"/>
  <button onclick="search()">🔍 Search</button>
</div>

<div class="card">
  <label>Results</label>
  <div id="results" style="margin-top:12px;color:#8890a8;">Run a search above…</div>
</div>

<script>
async function buildIndex() {
  document.getElementById('index_status').textContent = 'Building… please wait.';
  const r = await fetch('/index', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({folder:'course_docs'})});
  const d = await r.json();
  document.getElementById('index_status').textContent = r.ok
    ? '✅ Ready — ' + d.chunks_indexed + ' chunks indexed'
    : '❌ Error: ' + d.detail;
}

async function search() {
  const q = document.getElementById('query').value.trim();
  if (!q) return;
  document.getElementById('results').textContent = 'Searching…';
  const r = await fetch('/search', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query:q})});
  const data = await r.json();
  if (!r.ok) { document.getElementById('results').textContent = 'Error: ' + data.detail; return; }
  if (!data.length) { document.getElementById('results').textContent = 'No results found.'; return; }
  document.getElementById('results').textContent = data.map((x,i) =>
    `[${i+1}] ${x.file} — Page ${x.page}  (Score: ${(x.score*100).toFixed(0)}%)\n${x.context}\n${'─'.repeat(60)}`
  ).join('\n\n');
}
</script>
</body>
</html>
"""

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
