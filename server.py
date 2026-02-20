"""
server.py
Course Search Bot — Enhanced Web Server Mode (for Docker / always-alive deployment)
Features:
  ✓ Audit logging for compliance
  ✓ Rate limiting against abuse
  ✓ File upload with validation
  ✓ Search history & pagination
  ✓ File management
  ✓ Advanced filtering
  ✓ Enhanced error handling
Access the UI at: http://localhost:8000
"""
from __future__ import annotations
import logging
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

os.makedirs("course_docs", exist_ok=True)
os.makedirs("data", exist_ok=True)

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

from config.config import AppConfig
from core.indexer import Indexer
from core.search_engine import SearchEngine
from security.storage import MetadataStore
from security.audit import AuditLogger, RateLimiter, FileUploadValidator

# Lazy load AnswerGenerator to avoid import issues
AnswerGenerator = None
try:
    from core.answer_generator import AnswerGenerator
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not import AnswerGenerator: {e}. Answer endpoint will be disabled.")

# ── Setup ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cfg = AppConfig.from_yaml("config/settings.yaml")
cfg.ensure_dirs()

store        = MetadataStore(cfg.storage.db_path)
indexer      = Indexer(cfg, store)
engine       = SearchEngine(cfg, indexer, store)
audit        = AuditLogger("data/audit.db")
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

# Initialize search analytics database
import sqlite3
ANALYTICS_DB = "data/analytics.db"
os.makedirs("data", exist_ok=True)

def init_analytics_db():
    """Initialize analytics database."""
    conn = sqlite3.connect(ANALYTICS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_queries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            query           TEXT NOT NULL,
            results_count   INTEGER DEFAULT 0,
            execution_time  REAL DEFAULT 0,
            user_ip         TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_uploads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            filename        TEXT NOT NULL,
            file_type       TEXT,
            file_size       INTEGER,
            status          TEXT DEFAULT 'success'
        )
    """)
    conn.commit()
    conn.close()

init_analytics_db()

# Initialize answer generator if available
answer_gen = None
if AnswerGenerator:
    try:
        answer_gen = AnswerGenerator(indexer.model)
    except Exception as e:
        logger.warning(f"Failed to initialize AnswerGenerator: {e}")

app = FastAPI(
    title="Course Search Bot — Enterprise Edition",
    description="AI-powered semantic search for university course PDFs with audit logging, security & answer generation",
    version="2.2.0",
)

# ── CORS Configuration ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request/Response models ───────────────────────────────────────────────────

class IndexRequest(BaseModel):
    folder: str = "course_docs"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    offset: int = 0
    file_filter: Optional[str] = None
    score_threshold: float = 0.2

class SearchResultItem(BaseModel):
    file: str
    page: int
    context: str
    score: float
    timestamp: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    detail: str
    timestamp: str
    request_id: Optional[str] = None

class FileInfo(BaseModel):
    filename: str
    size: int
    chunks_indexed: int
    last_indexed: str

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all requests."""
    client_ip = request.client.host if request.client else "unknown"
    
    if not rate_limiter.is_allowed(client_ip):
        audit.log(
            action="RATE_LIMIT_EXCEEDED",
            status="BLOCKED",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            risk_level="WARNING",
        )
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limited", "detail": "Too many requests. Please try again later."},
        )
    
    response = await call_next(request)
    return response


@app.get("/health")
def health():
    """Docker health check endpoint — keeps the container alive."""
    return {"status": "ok", "index_ready": engine.is_ready}


@app.post("/index")
def build_index(req: IndexRequest, request: Request):
    """Build or reload the document index with audit logging."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        engine.load_or_build(req.folder)
        count = store.count_chunks()
        
        audit.log(
            action="INDEX_REBUILT",
            status="SUCCESS",
            resource=req.folder,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"chunks_indexed": count},
        )
        
        return {"status": "success", "chunks_indexed": count, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error(f"Index error: {e}")
        audit.log(
            action="INDEX_FAILED",
            status="ERROR",
            resource=req.folder,
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="WARNING",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
def search(req: SearchRequest, request: Request):
    """Run a semantic search query with pagination and filtering."""
    client_ip = request.client.host if request.client else "unknown"
    
    if not engine.is_ready:
        audit.log(
            action="SEARCH_FAILED",
            status="INDEX_NOT_READY",
            ip_address=client_ip,
            risk_level="INFO",
        )
        raise HTTPException(status_code=400, detail="Index not loaded. Call /index first.")
    
    try:
        results = engine.search(req.query, top_k=req.top_k)
        
        # Apply file filter if specified
        if req.file_filter:
            results = [r for r in results if req.file_filter.lower() in r.file.lower()]
        
        # Apply score threshold filter
        results = [r for r in results if r.score >= req.score_threshold]
        
        # Pagination
        total = len(results)
        start = req.offset
        end = start + req.top_k
        paginated = results[start:end]
        
        # Log to analytics
        try:
            conn = sqlite3.connect(ANALYTICS_DB)
            conn.execute(
                "INSERT INTO search_queries (timestamp, query, results_count, user_ip) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), req.query, total, client_ip)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log search analytics: {e}")
        
        audit.log(
            action="SEARCH_EXECUTED",
            status="SUCCESS",
            resource=req.query[:100],
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"results_found": len(paginated), "total": total},
        )
        
        return {
            "results": [r.to_dict() for r in paginated],
            "total": total,
            "offset": start,
            "limit": req.top_k,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except ValueError as e:
        audit.log(
            action="SEARCH_VALIDATION_ERROR",
            status="ERROR",
            resource=req.query[:100],
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="INFO",
        )
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {e}")
        audit.log(
            action="SEARCH_ERROR",
            status="ERROR",
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="WARNING",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/answer")
def generate_answer(req: SearchRequest, request: Request):
    """Generate a natural language answer from search results."""
    if not answer_gen:
        raise HTTPException(status_code=503, detail="Answer generation feature is not available. Please try the search endpoint instead.")
    
    client_ip = request.client.host if request.client else "unknown"
    
    if not engine.is_ready:
        raise HTTPException(status_code=400, detail="Index not loaded. Call /index first.")
    
    try:
        # Get search results
        results = engine.search(req.query, top_k=req.top_k)
        
        # Apply filters
        if req.file_filter:
            results = [r for r in results if req.file_filter.lower() in r.file.lower()]
        results = [r for r in results if r.score >= req.score_threshold]
        
        # Generate answer
        answer_data = answer_gen.generate_answer(
            query=req.query,
            search_results=[r.to_dict() for r in results],
            max_answer_length=500,
        )
        
        audit.log(
            action="ANSWER_GENERATED",
            status="SUCCESS",
            resource=req.query[:100],
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"confidence": answer_data["confidence"], "sources_count": len(answer_data["sources"])},
        )
        
        return {
            **answer_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Answer generation error: {e}")
        audit.log(
            action="ANSWER_ERROR",
            status="ERROR",
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="WARNING",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), request: Request = None):
    """Upload and validate a PDF, DOC, or DOCX file for indexing."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Read file content
        content = await file.read()
        
        # Validate file
        is_valid, message = FileUploadValidator.validate_upload(file.filename, content)
        
        if not is_valid:
            audit.log(
                action="FILE_UPLOAD_REJECTED",
                status="REJECTED",
                resource=file.filename,
                ip_address=client_ip,
                details={"reason": message},
                risk_level="WARNING",
            )
            raise HTTPException(status_code=400, detail=message)
        
        # Sanitize and save
        safe_name = FileUploadValidator.sanitize_filename(file.filename)
        dest_path = Path("course_docs") / safe_name
        
        with open(dest_path, "wb") as f:
            f.write(content)
        
        audit.log(
            action="FILE_UPLOADED",
            status="SUCCESS",
            resource=safe_name,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"size_bytes": len(content)},
        )
        
        return {
            "status": "success",
            "filename": safe_name,
            "size_bytes": len(content),
            "message": "File uploaded successfully. Run /index to add to search index.",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        audit.log(
            action="FILE_UPLOAD_ERROR",
            status="ERROR",
            resource=file.filename or "unknown",
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="WARNING",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files")
def list_files(request: Request):
    """List all indexed PDF, DOC, and DOCX files."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        files = []
        course_docs = Path("course_docs")
        if course_docs.exists():
            # List all PDF, DOC, and DOCX files
            for pattern in ["*.pdf", "*.doc", "*.docx"]:
                for f in course_docs.glob(pattern):
                    files.append({
                        "filename": f.name,
                        "size_bytes": f.stat().st_size,
                        "last_modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
        
        # Sort by filename
        files.sort(key=lambda x: x["filename"])
        
        audit.log(
            action="FILES_LISTED",
            status="SUCCESS",
            ip_address=client_ip,
            details={"count": len(files)},
        )
        
        return {
            "files": files,
            "total": len(files),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"List files error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/files/{filename}")
def delete_file(filename: str, request: Request):
    """Delete a file from the course documents folder."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Sanitize filename to prevent directory traversal
        safe_name = FileUploadValidator.sanitize_filename(filename)
        file_path = Path("course_docs") / safe_name
        
        # Verify file is in safe directory
        file_path.resolve().relative_to(Path("course_docs").resolve())
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path.unlink()
        
        audit.log(
            action="FILE_DELETED",
            status="SUCCESS",
            resource=safe_name,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"message": "File deleted. Run /index to update search index"},
        )
        
        return {
            "status": "success",
            "message": "File deleted. Run /index to update search index.",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Delete file error: {e}")
        audit.log(
            action="FILE_DELETE_ERROR",
            status="ERROR",
            resource=filename,
            ip_address=client_ip,
            details={"error": str(e)},
            risk_level="WARNING",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics")
def get_analytics(request: Request):
    """Get search analytics and statistics."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        
        # Total searches
        total_searches = conn.execute("SELECT COUNT(*) FROM search_queries").fetchone()[0]
        
        # Top queries
        top_queries = conn.execute("""
            SELECT query, COUNT(*) as count, AVG(results_count) as avg_results
            FROM search_queries
            GROUP BY query
            ORDER BY count DESC
            LIMIT 10
        """).fetchall()
        
        # Searches by hour (last 24 hours)
        hourly_data = conn.execute("""
            SELECT 
                strftime('%Y-%m-%d %H:00', timestamp) as hour,
                COUNT(*) as count
            FROM search_queries
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY hour
            ORDER BY hour
        """).fetchall()
        
        # File statistics
        file_stats = conn.execute("""
            SELECT file_type, COUNT(*) as count, SUM(file_size) as total_size
            FROM file_uploads
            WHERE status = 'success'
            GROUP BY file_type
        """).fetchall()
        
        conn.close()
        
        return {
            "total_searches": total_searches,
            "top_queries": [
                {"query": q[0], "count": q[1], "avg_results": q[2]}
                for q in top_queries
            ],
            "hourly_searches": [
                {"hour": h[0], "count": h[1]}
                for h in hourly_data
            ],
            "file_statistics": [
                {"type": f[0], "count": f[1], "total_size": f[2]}
                for f in file_stats
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/counselor")
def civil_engineering_counselor(req: SearchRequest, request: Request):
    """Civil Engineering specific counselor - provides guided assistance."""
    client_ip = request.client.host if request.client else "unknown"
    
    if not engine.is_ready:
        raise HTTPException(status_code=400, detail="Index not loaded. Call /index first.")
    
    try:
        # Civil engineering specific context
        ce_context = {
            "subjects": ["Structural Analysis", "Geotechnical", "Environmental", "Transportation", "Water Resources"],
            "keywords": ["design", "analysis", "foundation", "bridge", "soil", "concrete", "steel", "load", "stress"]
        }
        
        # Search with engineering context
        results = engine.search(req.query, top_k=15)
        
        # Filter for civil engineering relevance
        ce_results = []
        for r in results:
            if any(kw in r.text.lower() for kw in ce_context["keywords"]):
                ce_results.append(r)
        
        # If no CE-specific results, fall back to all results
        if not ce_results:
            ce_results = results[:10]
        
        # Log to analytics
        try:
            conn = sqlite3.connect(ANALYTICS_DB)
            conn.execute(
                "INSERT INTO search_queries (timestamp, query, results_count, user_ip) VALUES (?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), f"[CE_COUNSELOR] {req.query}", len(ce_results), client_ip)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log counselor query: {e}")
        
        return {
            "counselor": "Civil Engineering Advisor",
            "query": req.query,
            "results": [r.to_dict() for r in ce_results],
            "total": len(ce_results),
            "guidance": f"Found {len(ce_results)} civil engineering related results for your query.",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Counselor error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit-logs")
def get_audit_logs(
    hours: int = Query(24, ge=1),
    action_filter: Optional[str] = None,
    risk_filter: Optional[str] = None,
    request: Request = None,
):
    """Get audit logs (admin endpoint)."""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        logs = audit.get_logs(action_filter=action_filter, risk_filter=risk_filter, hours=hours)
        return {
            "logs": logs,
            "total": len(logs),
            "filters": {
                "hours": hours,
                "action": action_filter,
                "risk_level": risk_filter,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Audit logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
def status():
    """Get current system status."""
    return {
        "index_ready": engine.is_ready,
        "chunks_count": store.count_chunks(),
        "model": cfg.model.name,
        "version": "2.2.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/")
def root():
    """Enhanced web UI with file management, history, pagination, and filters."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Course Search Bot — Enterprise</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='75' font-size='75'>🎓</text></svg>">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { 
    background: linear-gradient(135deg, #0f1117 0%, #1a1d27 100%); 
    color: #e8eaf0; 
    font-family: 'Segoe UI', sans-serif; 
    min-height: 100vh; 
    padding: 20px;
  }
  .container { max-width: 1200px; margin: 0 auto; }
  header { text-align: center; margin-bottom: 40px; }
  h1 { font-size: 2.5rem; margin-bottom: 8px; color: #4f8ef7; text-shadow: 0 0 20px rgba(79, 142, 247, 0.3); }
  .sub { color: #8890a8; font-size: 1.1rem; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
  .card { 
    background: #1a1d27; 
    border: 1px solid #2a2d3e; 
    border-radius: 12px; 
    padding: 24px; 
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    transition: transform 0.2s, box-shadow 0.2s;
  }
  .card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(79, 142, 247, 0.2); }
  .card h2 { color: #4f8ef7; margin-bottom: 16px; font-size: 1.2rem; }
  input, textarea, select { 
    width: 100%; 
    padding: 12px 16px; 
    border-radius: 8px; 
    border: 1px solid #2a2d3e; 
    background: #0f1117; 
    color: #e8eaf0; 
    font-size: 1rem; 
    margin-top: 10px;
    font-family: inherit;
  }
  input:focus, textarea:focus, select:focus { 
    outline: none; 
    border-color: #4f8ef7; 
    box-shadow: 0 0 0 3px rgba(79, 142, 247, 0.1);
  }
  button { 
    width: 100%; 
    padding: 12px 16px; 
    border-radius: 8px; 
    border: none; 
    font-size: 1rem; 
    margin-top: 10px;
    cursor: pointer; 
    font-weight: 600; 
    transition: all 0.2s;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .btn-primary { background: #4f8ef7; color: white; }
  .btn-primary:hover { background: #6fa5ff; transform: translateY(-2px); }
  .btn-success { background: #3ecf8e; color: #000; }
  .btn-success:hover { background: #5ce5a0; }
  .btn-danger { background: #e05252; color: white; }
  .btn-danger:hover { background: #f07070; }
  .btn-secondary { background: #2a2d3e; color: #e8eaf0; }
  .btn-secondary:hover { background: #3a3d4e; }
  #results { 
    white-space: pre-wrap; 
    font-family: 'Consolas', monospace; 
    font-size: 0.85rem; 
    color: #e8eaf0; 
    max-height: 500px; 
    overflow-y: auto; 
    background: #0f1117;
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #2a2d3e;
    line-height: 1.5;
  }
  #files-list, #history-list { 
    max-height: 300px; 
    overflow-y: auto;
    background: #0f1117;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #2a2d3e;
  }
  .file-item, .history-item { 
    padding: 12px; 
    background: #0f1117; 
    border-bottom: 1px solid #2a2d3e;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .file-item:last-child, .history-item:last-child { border-bottom: none; }
  .badge { 
    display: inline-block; 
    background: #7c5cbf; 
    color: white; 
    padding: 4px 12px; 
    border-radius: 20px; 
    font-size: 0.75rem; 
    margin-left: 10px;
  }
  .badge.success { background: #3ecf8e; color: #000; }
  .badge.warning { background: #f0a500; color: #000; }
  .badge.error { background: #e05252; color: white; }
  label { color: #8890a8; font-size: 0.85rem; display: block; margin-top: 12px; }
  .tabs { 
    display: flex; 
    gap: 10px; 
    margin-bottom: 20px; 
    border-bottom: 2px solid #2a2d3e;
  }
  .tab-btn { 
    background: none; 
    border: none; 
    color: #8890a8; 
    cursor: pointer; 
    padding: 12px 20px; 
    font-weight: 600;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
  }
  .tab-btn.active { color: #4f8ef7; border-bottom-color: #4f8ef7; }
  .tab-btn:hover { color: #4f8ef7; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .filter-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .pagination { 
    display: flex; 
    gap: 5px; 
    margin-top: 15px; 
    justify-content: center;
    flex-wrap: wrap;
  }
  .pagination button { width: auto; padding: 8px 12px; margin: 0; }
  .status-msg { 
    padding: 12px; 
    border-radius: 8px; 
    margin-top: 10px;
    font-size: 0.9rem;
  }
  .status-msg.success { background: #1a3a2a; color: #3ecf8e; border: 1px solid #3ecf8e; }
  .status-msg.error { background: #3a1a1a; color: #e05252; border: 1px solid #e05252; }
  .status-msg.info { background: #1a2a3a; color: #4f8ef7; border: 1px solid #4f8ef7; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🎓 Course Search Bot</h1>
    <p class="sub">AI-powered semantic search for university course documents</p>
    <div id="status-bar" style="color: #3ecf8e; font-size: 0.9rem;"></div>
  </header>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('search')">🔍 Search</button>
    <button class="tab-btn" onclick="switchTab('files')">📁 Files</button>
    <button class="tab-btn" onclick="switchTab('ce-counselor')">🏗️ CE Counselor</button>
    <button class="tab-btn" onclick="switchTab('analytics')">📊 Analytics</button>
    <button class="tab-btn" onclick="switchTab('history')">📋 History</button>
    <button class="tab-btn" onclick="switchTab('settings')">⚙ Settings</button>
  </div>

  <!-- SEARCH TAB -->
  <div id="search" class="tab-content active">
    <div class="grid">
      <div class="card">
        <h2>Build Index</h2>
        <p style="color: #8890a8; font-size: 0.9rem; margin-bottom: 10px;">Index your PDF documents for semantic search</p>
        <button class="btn-primary" onclick="buildIndex()">⚙ Build / Reload Index</button>
        <div id="index_status"></div>
      </div>

      <div class="card">
        <h2>Search Documents</h2>
        <input id="query" type="text" placeholder="e.g., What is photosynthesis?" onkeydown="if(event.key==='Enter')search()"/>
        <div class="filter-row">
          <div>
            <label>Filter by file:</label>
            <input id="file-filter" type="text" placeholder="e.g., biology.pdf" />
          </div>
          <div>
            <label>Min score:</label>
            <input id="score-threshold" type="number" min="0" max="1" step="0.1" value="0.2" />
          </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <button class="btn-primary" onclick="search()">🔍 Search</button>
          <button class="btn-success" onclick="getAnswer()">🤖 Get Answer</button>
        </div>
        <div id="search_status"></div>
      </div>
    </div>

    <div class="card">
      <h2>Results</h2>
      <div id="results" style="margin-top: 12px; color: #8890a8;">Run a search above…</div>
      <div class="pagination" id="pagination"></div>
    </div>

    <div class="card" id="answer-card" style="display: none;">
      <h2>🤖 AI Answer</h2>
      <div id="answer-content" style="margin-top: 12px; background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #4f8ef7; line-height: 1.6;">
        <p id="answer-text" style="color: #e8eaf0; margin-bottom: 12px;"></p>
        <div id="answer-sources" style="color: #8890a8; font-size: 0.9rem;"></div>
        <div id="answer-confidence" style="color: #3ecf8e; font-size: 0.85rem; margin-top: 8px;"></div>
      </div>
    </div>
  </div>

  <!-- FILES TAB -->
  <div id="files" class="tab-content">
    <div class="grid">
      <div class="card">
        <h2>Upload Documents</h2>
        <p style="color: #8890a8; font-size: 0.9rem; margin-bottom: 10px;">Max 50MB. Supports PDF, DOC, DOCX, XLSX, XLS files. Auto-validated.</p>
        <input type="file" id="file-upload" accept=".pdf,.doc,.docx,.xlsx,.xls" />
        <button class="btn-primary" onclick="uploadFile()">📤 Upload</button>
        <div id="upload_status"></div>
      </div>

      <div class="card">
        <h2>Indexed Files</h2>
        <div style="color: #8890a8; font-size: 0.85rem; margin-bottom: 12px;">Total files: <strong id="file-count">0</strong></div>
        <button class="btn-secondary" onclick="listFiles()">📂 Refresh List</button>
        <div id="files-list" style="margin-top: 12px; max-height: 400px; overflow-y: auto;"></div>
      </div>
    </div>

    <div class="card" id="analytics-card">
      <h2>📊 Search Analytics</h2>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #4f8ef7;">
          <div style="color: #8890a8; font-size: 0.85rem;">Total Searches</div>
          <div style="color: #4f8ef7; font-size: 2rem; font-weight: bold; margin-top: 8px;" id="total-searches">0</div>
        </div>
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #3ecf8e;">
          <div style="color: #8890a8; font-size: 0.85rem;">Most Searched</div>
          <div style="color: #3ecf8e; font-size: 1rem; margin-top: 8px;" id="top-query">N/A</div>
        </div>
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #f0a500;">
          <div style="color: #8890a8; font-size: 0.85rem;">Search Queries</div>
          <div style="color: #f0a500; font-size: 2rem; font-weight: bold; margin-top: 8px;" id="unique-searches">0</div>
        </div>
      </div>
      <canvas id="analyticsChart" style="max-height: 300px; margin-top: 20px;"></canvas>
      <button class="btn-secondary" onclick="loadAnalytics()">🔄 Refresh Analytics</button>
    </div>
  </div>

  <!-- CE COUNSELOR TAB -->
  <div id="ce-counselor" class="tab-content">
    <div class="grid">
      <div class="card">
        <h2>🏗️ Civil Engineering Counselor</h2>
        <p style="color: #8890a8; font-size: 0.9rem; margin-bottom: 10px;">Get personalized guidance for civil engineering courses and topics</p>
        <input id="ce-query" type="text" placeholder="e.g., How to design a reinforced concrete beam?" onkeydown="if(event.key==='Enter')solveCEProblem()"/>
        <button class="btn-primary" onclick="solveCEProblem()">📚 Get CE Guidance</button>
        <div id="ce_status"></div>
      </div>

      <div class="card">
        <h2>📋 CE Knowledge Base</h2>
        <p style="color: #8890a8; font-size: 0.85rem; margin-bottom: 10px;">Covers: Structural Analysis, Geotechnical, Transportation, Water Resources, Environmental</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <button class="btn-secondary" onclick="quickSearchCE('Structural Analysis')">Structural</button>
          <button class="btn-secondary" onclick="quickSearchCE('Foundation Design')">Geotechnical</button>
          <button class="btn-secondary" onclick="quickSearchCE('Bridge Design')">Bridges</button>
          <button class="btn-secondary" onclick="quickSearchCE('Water Supply')">Water Resources</button>
        </div>
      </div>
    </div>

    <div class="card" id="ce-results-card" style="display: none;">
      <h2>CE Guidance Results</h2>
      <div id="ce-results" style="margin-top: 12px;"></div>
    </div>
  </div>

  <!-- HISTORY TAB -->
  <div id="history" class="tab-content">
    <div class="card">
      <h2>Search History</h2>
      <p style="color: #8890a8; font-size: 0.9rem; margin-bottom: 10px;">Your recent searches (stored locally)</p>
      <button class="btn-secondary" onclick="clearHistory()">🗑️ Clear History</button>
      <div id="history-list" style="margin-top: 12px; max-height: 500px; overflow-y: auto;"></div>
    </div>
  </div>

  <!-- ANALYTICS TAB -->
  <div id="analytics" class="tab-content">
    <div class="card">
      <h2>📊 Search Analytics Dashboard</h2>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #4f8ef7;">
          <div style="color: #8890a8; font-size: 0.85rem;">Total Searches</div>
          <div style="color: #4f8ef7; font-size: 2rem; font-weight: bold; margin-top: 8px;" id="analytics-total-searches">0</div>
        </div>
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #3ecf8e;">
          <div style="color: #8890a8; font-size: 0.85rem;">Top Search Query</div>
          <div style="color: #3ecf8e; font-size: 0.9rem; margin-top: 8px; word-break: break-word;" id="analytics-top-query">N/A</div>
        </div>
        <div style="background: #0f1117; padding: 16px; border-radius: 8px; border-left: 4px solid #f0a500;">
          <div style="color: #8890a8; font-size: 0.85rem;">Unique Searches</div>
          <div style="color: #f0a500; font-size: 2rem; font-weight: bold; margin-top: 8px;" id="analytics-unique-searches">0</div>
        </div>
      </div>
      
      <div style="background: #0f1117; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #2a2d3e;">
        <h3 style="color: #e8eaf0; margin-bottom: 15px;">Searches Over Time (24h)</h3>
        <canvas id="searchChart" style="max-height: 250px;"></canvas>
      </div>

      <div style="background: #0f1117; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #2a2d3e;">
        <h3 style="color: #e8eaf0; margin-bottom: 15px;">Top Search Queries</h3>
        <div id="top-queries-list" style="max-height: 300px; overflow-y: auto;"></div>
      </div>

      <button class="btn-primary" onclick="loadAnalytics()">🔄 Refresh Analytics</button>
    </div>
  </div>

  <!-- SETTINGS TAB -->
  <div id="settings" class="tab-content">
    <div class="grid">
      <div class="card">
        <h2>System Status</h2>
        <div id="system-status" style="color: #e8eaf0; font-size: 0.9rem; line-height: 1.8;">
          Loading…
        </div>
        <button class="btn-secondary" onclick="getSystemStatus()">🔄 Refresh</button>
      </div>

      <div class="card">
        <h2>Security & Audit</h2>
        <p style="color: #8890a8; font-size: 0.9rem; margin-bottom: 10px;">Advanced features</p>
        <button class="btn-secondary" onclick="viewAuditLogs()">📊 View Audit Logs</button>
        <div id="audit-status"></div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const STORAGE_KEY = 'course_bot_history';
let currentPage = 0;
let lastResults = [];
let lastQuery = '';
let analyticsChart = null;
let searchChartInstance = null;

function switchTab(tab) {
  // Hide all tabs
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  // Show selected tab
  document.getElementById(tab).classList.add('active');
  event.target.classList.add('active');
  
  if (tab === 'history') loadHistory();
  if (tab === 'files') listFiles();
  if (tab === 'analytics') loadAnalytics();
  if (tab === 'settings') getSystemStatus();
}

async function buildIndex() {
  document.getElementById('index_status').innerHTML = '<div class="status-msg info">⏳ Building… please wait…</div>';
  try {
    const r = await fetch('/index', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({folder: 'course_docs'})
    });
    const d = await r.json();
    if (r.ok) {
      document.getElementById('index_status').innerHTML = `<div class="status-msg success">✅ Ready — ${d.chunks_indexed} chunks indexed</div>`;
      addToHistory(`Indexed ${d.chunks_indexed} chunks`);
    } else {
      document.getElementById('index_status').innerHTML = `<div class="status-msg error">❌ Error: ${d.detail}</div>`;
    }
  } catch (e) {
    document.getElementById('index_status').innerHTML = `<div class="status-msg error">❌ Error: ${e.message}</div>`;
  }
}

async function search() {
  const q = document.getElementById('query').value.trim();
  if (!q) { alert('Enter a search query'); return; }
  
  lastQuery = q;
  currentPage = 0;
  document.getElementById('results').textContent = '⏳ Searching…';
  
  try {
    const fileFilter = document.getElementById('file-filter').value.trim();
    const scoreThreshold = parseFloat(document.getElementById('score-threshold').value) || 0.2;
    
    const r = await fetch('/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: q,
        top_k: 10,
        offset: 0,
        file_filter: fileFilter || null,
        score_threshold: scoreThreshold
      })
    });
    
    const data = await r.json();
    if (!r.ok) {
      document.getElementById('results').innerHTML = `<span style="color: #e05252;">❌ ${data.detail}</span>`;
      return;
    }
    
    lastResults = data.results;
    displayResults(data);
    addToHistory(q, data.results.length);
  } catch (e) {
    document.getElementById('results').innerHTML = `<span style="color: #e05252;">❌ Error: ${e.message}</span>`;
  }
}

function displayResults(data) {
  const results = data.results;
  if (!results || results.length === 0) {
    document.getElementById('results').innerHTML = '<span style="color: #8890a8;">No results found.</span>';
    document.getElementById('pagination').innerHTML = '';
    return;
  }
  
  const resultsHTML = results.map((x, i) => {
    const scoreColor = x.score > 0.7 ? '#3ecf8e' : x.score > 0.4 ? '#f0a500' : '#8890a8';
    return `<div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #2a2d3e;">
      <strong style="color: #4f8ef7;">📄 ${x.file}</strong> — Page ${x.page} <span class="badge" style="background: ${scoreColor};">${(x.score * 100).toFixed(0)}%</span>
      <div style="margin-top: 8px; color: #e8eaf0; font-size: 0.9rem; line-height: 1.5;">${x.context}</div>
    </div>`;
  }).join('');
  
  document.getElementById('results').innerHTML = resultsHTML;
  
  // Pagination
  const paginationHTML = `
    <button class="btn-secondary" onclick="previousPage()" ${data.offset === 0 ? 'disabled' : ''}>← Prev</button>
    <span style="padding: 8px 12px; color: #8890a8;">Page ${Math.floor(data.offset / data.limit) + 1}</span>
    <button class="btn-secondary" onclick="nextPage()" ${data.offset + data.limit >= data.total ? 'disabled' : ''}>Next →</button>
    <span style="padding: 8px 12px; color: #8890a8;">(${results.length} of ${data.total})</span>
  `;
  document.getElementById('pagination').innerHTML = paginationHTML;
}

function previousPage() { currentPage = Math.max(0, currentPage - 1); search(); }
function nextPage() { currentPage++; search(); }

async function getAnswer() {
  const q = document.getElementById('query').value.trim();
  if (!q) { alert('Enter a search query'); return; }
  
  document.getElementById('answer-card').style.display = 'block';
  document.getElementById('answer-text').textContent = '⏳ Generating answer…';
  document.getElementById('answer-sources').innerHTML = '';
  document.getElementById('answer-confidence').innerHTML = '';
  
  try {
    const fileFilter = document.getElementById('file-filter').value.trim();
    const scoreThreshold = parseFloat(document.getElementById('score-threshold').value) || 0.2;
    
    const r = await fetch('/answer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: q,
        top_k: 10,
        offset: 0,
        file_filter: fileFilter || null,
        score_threshold: scoreThreshold
      })
    });
    
    const data = await r.json();
    if (!r.ok) {
      document.getElementById('answer-text').innerHTML = `<span style="color: #e05252;">❌ ${data.detail}</span>`;
      return;
    }
    
    // Display answer
    document.getElementById('answer-text').textContent = data.answer || 'No answer could be generated.';
    
    // Display sources
    let sourcesHTML = '<strong>📚 Sources:</strong><br>';
    if (data.sources && data.sources.length > 0) {
      sourcesHTML += data.sources.map(src => 
        `• <strong>${src.file}</strong> (Page ${src.page}) — ${(src.score * 100).toFixed(0)}% match`
      ).join('<br>');
    } else {
      sourcesHTML += 'No specific sources found.';
    }
    document.getElementById('answer-sources').innerHTML = sourcesHTML;
    
    // Display confidence
    const confidence = data.confidence * 100;
    const confidenceColor = confidence > 70 ? '#3ecf8e' : confidence > 40 ? '#f0a500' : '#e05252';
    document.getElementById('answer-confidence').innerHTML = 
      `<strong style="color: ${confidenceColor};">Confidence: ${confidence.toFixed(0)}%</strong> | Method: ${data.method}`;
    
    addToHistory(`Answer: ${q}`);
  } catch (e) {
    document.getElementById('answer-text').innerHTML = `<span style="color: #e05252;">❌ Error: ${e.message}</span>`;
  }
}

async function uploadFile() {
  const file = document.getElementById('file-upload').files[0];
  if (!file) { alert('Select a file'); return; }
  
  const formData = new FormData();
  formData.append('file', file);
  
  document.getElementById('upload_status').innerHTML = '<div class="status-msg info">⏳ Uploading…</div>';
  
  try {
    const r = await fetch('/upload', {method: 'POST', body: formData});
    const d = await r.json();
    if (r.ok) {
      document.getElementById('upload_status').innerHTML = `<div class="status-msg success">✅ ${d.message}</div>`;
      document.getElementById('file-upload').value = '';
      listFiles();
    } else {
      document.getElementById('upload_status').innerHTML = `<div class="status-msg error">❌ ${d.detail}</div>`;
    }
  } catch (e) {
    document.getElementById('upload_status').innerHTML = `<div class="status-msg error">❌ ${e.message}</div>`;
  }
}

async function listFiles() {
  try {
    const r = await fetch('/files');
    const d = await r.json();
    const html = d.files.length > 0
      ? d.files.map(f => `
        <div class="file-item">
          <span>📄 ${f.filename}</span>
          <span style="color: #8890a8; font-size: 0.8rem;">${(f.size_bytes / 1024).toFixed(1)}KB</span>
          <button class="btn-danger" style="width: auto; padding: 4px 8px; font-size: 0.8rem; margin: 0;" onclick="deleteFile('${f.filename}')">Delete</button>
        </div>
      `).join('')
      : '<div style="color: #8890a8; padding: 12px;">No files uploaded yet</div>';
    document.getElementById('files-list').innerHTML = html;
  } catch (e) {
    document.getElementById('files-list').innerHTML = `<div style="color: #e05252;">Error: ${e.message}</div>`;
  }
}

async function deleteFile(filename) {
  if (!confirm(`Delete ${filename}?`)) return;
  try {
    const r = await fetch(`/files/${encodeURIComponent(filename)}`, {method: 'DELETE'});
    const d = await r.json();
    if (r.ok) {
      listFiles();
      addToHistory(`Deleted: ${filename}`);
    } else {
      alert(`Error: ${d.detail}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

function addToHistory(query, resultCount = 0) {
  let history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  history.unshift({query, timestamp: new Date().toLocaleString(), results: resultCount});
  history = history.slice(0, 50); // Keep last 50
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
}

function loadHistory() {
  const history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  const html = history.length > 0
    ? history.map(h => `
      <div class="history-item">
        <div>
          <strong>${h.query}</strong><br>
          <span style="color: #8890a8; font-size: 0.85rem;">${h.timestamp}${h.results ? ' — ' + h.results + ' results' : ''}</span>
        </div>
        <button class="btn-secondary" style="width: auto; padding: 4px 8px; margin: 0;" onclick="document.getElementById('query').value='${h.query.replace(/'/g, "\\'")}';search()">Search</button>
      </div>
    `).join('')
    : '<div style="color: #8890a8; padding: 12px;">No history yet</div>';
  document.getElementById('history-list').innerHTML = html;
}

function clearHistory() {
  if (confirm('Clear all search history?')) {
    localStorage.removeItem(STORAGE_KEY);
    document.getElementById('history-list').innerHTML = '<div style="color: #8890a8; padding: 12px;">History cleared</div>';
  }
}

async function getSystemStatus() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    const html = `
      <strong>Status:</strong> ${d.index_ready ? '✅ Ready' : '⚠️ Index Not Loaded'}<br>
      <strong>Chunks Indexed:</strong> ${d.chunks_count}<br>
      <strong>Model:</strong> ${d.model}<br>
      <strong>Version:</strong> ${d.version}<br>
      <strong>Last Update:</strong> ${new Date(d.timestamp).toLocaleString()}
    `;
    document.getElementById('system-status').innerHTML = html;
  } catch (e) {
    document.getElementById('system-status').innerHTML = `<span style="color: #e05252;">Error: ${e.message}</span>`;
  }
}

async function viewAuditLogs() {
  try {
    const r = await fetch('/audit-logs?hours=24');
    const d = await r.json();
    const logCount = d.logs ? d.logs.length : 0;
    document.getElementById('audit-status').innerHTML = `
      <div class="status-msg success" style="margin-top: 12px;">
        📊 ${logCount} audit events in last 24 hours
      </div>
    `;
  } catch (e) {
    document.getElementById('audit-status').innerHTML = `<div class="status-msg error">Error: ${e.message}</div>`;
  }
}

async function loadAnalytics() {
  try {
    const r = await fetch('/analytics');
    const data = await r.json();
    
    document.getElementById('analytics-total-searches').textContent = data.total_searches;
    document.getElementById('analytics-unique-searches').textContent = data.top_queries.length;
    
    if (data.top_queries.length > 0) {
      document.getElementById('analytics-top-query').textContent = data.top_queries[0].query;
    }
    
    // Render top queries
    const topQueriesHTML = data.top_queries.slice(0, 10).map(q => `
      <div style="padding: 10px; background: #0f1117; border-bottom: 1px solid #2a2d3e; display: flex; justify-content: space-between;">
        <span><strong>${q.query}</strong></span>
        <span style="color: #8890a8;">${q.count} searches</span>
      </div>
    `).join('');
    document.getElementById('top-queries-list').innerHTML = topQueriesHTML || '<div style="padding: 10px; color: #8890a8;">No search data yet</div>';
    
    // Chart.js for hourly searches
    if (data.hourly_searches.length > 0) {
      const ctx = document.getElementById('searchChart').getContext('2d');
      if (searchChartInstance) searchChartInstance.destroy();
      
      searchChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.hourly_searches.map(h => h.hour.substring(11, 16)),
          datasets: [{
            label: 'Searches per Hour',
            data: data.hourly_searches.map(h => h.count),
            borderColor: '#4f8ef7',
            backgroundColor: 'rgba(79, 142, 247, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#4f8ef7',
            pointBorderColor: '#ffffff',
            pointRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#e8eaf0' } }
          },
          scales: {
            y: { 
              grid: { color: '#2a2d3e' },
              ticks: { color: '#8890a8' }
            },
            x: { 
              grid: { color: '#2a2d3e' },
              ticks: { color: '#8890a8' }
            }
          }
        }
      });
    }
  } catch (e) {
    console.error('Analytics error:', e);
  }
}

async function solveCEProblem() {
  const q = document.getElementById('ce-query').value.trim();
  if (!q) { alert('Enter a civil engineering question or topic'); return; }
  
  document.getElementById('ce_status').innerHTML = '<div class="status-msg info">⏳ Consulting CE Knowledge Base…</div>';
  document.getElementById('ce-results-card').style.display = 'none';
  
  try {
    const r = await fetch('/counselor', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: q,
        top_k: 10,
        offset: 0
      })
    });
    
    const data = await r.json();
    if (!r.ok) {
      document.getElementById('ce_status').innerHTML = `<div class="status-msg error">❌ ${data.detail}</div>`;
      return;
    }
    
    // Display results
    const resultsHTML = (data.results || []).slice(0, 5).map(r => `
      <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #2a2d3e;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <strong style="color: #4f8ef7;">📄 ${r.file}</strong>
          <span class="badge" style="background: #3ecf8e;">${(r.score * 100).toFixed(0)}%</span>
        </div>
        <div style="color: #e8eaf0; font-size: 0.9rem; line-height: 1.5;">${r.context}</div>
      </div>
    `).join('');
    
    document.getElementById('ce-results').innerHTML = resultsHTML || '<div style="color: #8890a8;">No relevant CE materials found.</div>';
    document.getElementById('ce_status').innerHTML = `<div class="status-msg success">✅ ${data.guidance}</div>`;
    document.getElementById('ce-results-card').style.display = 'block';
    
    addToHistory(`[CE] ${q}`);
  } catch (e) {
    document.getElementById('ce_status').innerHTML = `<div class="status-msg error">❌ Error: ${e.message}</div>`;
  }
}

function quickSearchCE(topic) {
  document.getElementById('ce-query').value = topic;
  solveCEProblem();
}

// Initialize on load
window.addEventListener('load', () => {
  getSystemStatus();
  loadHistory();
  // Auto-load analytics every 2 minutes
  setInterval(() => {
    if (document.querySelector('.tab-btn.active')?.textContent.includes('Analytics')) {
      loadAnalytics();
    }
  }, 120000);
});
</script>
</body>
</html>
"""
    return Response(content=html_content, media_type="text/html; charset=utf-8")


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("🚀 Course Search Bot — Enterprise Edition v2.2.0")
    logger.info("=" * 80)
    logger.info("✓ Audit logging enabled")
    logger.info("✓ Rate limiting enabled (100 req/60s per IP)")
    logger.info("✓ File upload validation enabled")
    logger.info("✓ AI Answer Generation enabled")
    logger.info("✓ Semantic search with pagination & filters")
    logger.info("")
    logger.info("🌐 Web UI:        http://localhost:8000")
    logger.info("🤖 Answer API:    POST /answer")
    logger.info("🔍 Search API:    POST /search")
    logger.info("📊 Audit logs:    /audit-logs")
    logger.info("📁 File upload:   POST /upload")
    logger.info("=" * 80)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

