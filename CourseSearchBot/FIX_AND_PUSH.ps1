# ================================================================
#  MASTER SETUP SCRIPT — Course Search Bot
#  Run this from inside:
#  C:\Users\Feroz Khan\universitydeleiverprojectcivil\CourseSearchBot
# ================================================================

# ---------------------------------------------------------------
# STEP 1 — Fix the README (move it to the right place)
# The README must live at the ROOT of the repo, not inside
# the CourseSearchBot subfolder
# ---------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Course Search Bot — Master Fix Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Go to the project root (the folder that contains CourseSearchBot/)
cd "C:\Users\Feroz Khan\universitydeleiverprojectcivil"

Write-Host "[1/6] Fixing folder structure..." -ForegroundColor Yellow

# Delete the broken curly-brace folder if it exists
if (Test-Path ".\CourseSearchBot\{core,security,config,ui,data,tests}") {
    Remove-Item -Recurse -Force ".\CourseSearchBot\{core,security,config,ui,data,tests}"
    Write-Host "  Deleted bad folder" -ForegroundColor Green
}

# Create data folder if missing
New-Item -ItemType Directory -Force -Path ".\CourseSearchBot\data" | Out-Null
Write-Host "  data/ folder ready" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 2 — Write README at the repo ROOT (outside CourseSearchBot)
# This is where GitHub shows it
# ---------------------------------------------------------------

Write-Host "[2/6] Writing README to repo root..." -ForegroundColor Yellow

@'
# Course Search Bot

AI-powered semantic search for university course PDFs.

---

## What It Does

Drop your lecture PDFs in, type a question in plain English,
and instantly find every relevant paragraph across all your documents.

---

## How To Run

### Desktop App (Windows)
```
1. Open the CourseSearchBot folder
2. Run Setup_Windows.bat  (first time only)
3. Run Launch_Windows.bat (every time after)
```

### Always-Alive Server (Docker)
```
cd CourseSearchBot
docker-compose up -d
Then open: http://localhost:8000
```

---

## Add Your PDFs

Put all your PDF files inside `CourseSearchBot/course_docs/`
then click Build Index in the app.

---

## Requirements

- Python 3.11 or newer
- Docker Desktop (only for server mode)

---

*Version 2.0*
'@ | Out-File -FilePath ".\README.md" -Encoding utf8

Write-Host "  README written at repo root" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 3 — Write .gitignore at repo root
# ---------------------------------------------------------------

Write-Host "[3/6] Writing .gitignore..." -ForegroundColor Yellow

@'
# Python
__pycache__/
*.py[cod]
*.pyo
venv/
env/
.venv/

# App data — never commit these
CourseSearchBot/data/
*.db
*.faiss
*.pkl
index_manifest.json

# User PDFs — private
CourseSearchBot/course_docs/*
!CourseSearchBot/course_docs/.gitkeep

# Build output
dist/
build/

# OS
.DS_Store
Thumbs.db
desktop.ini

# IDE
.vscode/
.idea/

# Secrets
.env
.env.*
*.log
'@ | Out-File -FilePath ".\.gitignore" -Encoding utf8

Write-Host "  .gitignore written" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 4 — Write server.py (Docker web server)
# ---------------------------------------------------------------

Write-Host "[4/6] Writing server.py..." -ForegroundColor Yellow

@'
"""
server.py - Web server mode for Docker deployment.
Access at http://localhost:8000
"""
import logging, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.makedirs("course_docs", exist_ok=True)
os.makedirs("data", exist_ok=True)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from config.config import AppConfig
from core.indexer import Indexer
from core.search_engine import SearchEngine
from security.storage import MetadataStore

logging.basicConfig(level=logging.INFO)
cfg = AppConfig.from_yaml("config/settings.yaml")
cfg.ensure_dirs()
store   = MetadataStore(cfg.storage.db_path)
indexer = Indexer(cfg, store)
engine  = SearchEngine(cfg, indexer, store)
app     = FastAPI(title="Course Search Bot", version="2.0.0")

class IndexRequest(BaseModel):
    folder: str = "course_docs"

class SearchRequest(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "ok", "index_ready": engine.is_ready}

@app.post("/index")
def build_index(req: IndexRequest):
    try:
        engine.load_or_build(req.folder)
        return {"status": "success", "chunks_indexed": store.count_chunks()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
def search(req: SearchRequest):
    if not engine.is_ready:
        raise HTTPException(status_code=400, detail="Build index first.")
    try:
        results = engine.search(req.query)
        return [r.to_dict() for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def root():
    return """
<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Course Search Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1117;color:#e8eaf0;font-family:Segoe UI,sans-serif;display:flex;flex-direction:column;align-items:center;padding:40px 20px}
h1{font-size:2rem;color:#4f8ef7;margin-bottom:8px}
.sub{color:#8890a8;margin-bottom:32px}
.card{background:#1a1d27;border:1px solid #2a2d3e;border-radius:12px;padding:24px;width:100%;max-width:700px;margin-bottom:20px}
input,button{width:100%;padding:12px 16px;border-radius:8px;border:none;font-size:1rem;margin-top:10px}
input{background:#0f1117;color:#e8eaf0;border:1px solid #2a2d3e}
button{background:#4f8ef7;color:#fff;cursor:pointer;font-weight:600}
button:hover{background:#7c5cbf}
#results{white-space:pre-wrap;font-family:monospace;font-size:.85rem;max-height:400px;overflow-y:auto;margin-top:12px}
label{color:#8890a8;font-size:.85rem}
.ok{color:#3ecf8e;margin-top:8px}
</style></head>
<body>
<h1>Course Search Bot</h1>
<p class="sub">AI-powered search for your course documents</p>
<div class="card">
  <label>Step 1 - Build Index</label>
  <button onclick="buildIndex()">Build / Reload Index</button>
  <div id="idx" class="ok"></div>
</div>
<div class="card">
  <label>Step 2 - Search</label>
  <input id="q" placeholder="e.g. what is photosynthesis?" onkeydown="if(event.key==='Enter')doSearch()"/>
  <button onclick="doSearch()">Search</button>
</div>
<div class="card">
  <label>Results</label>
  <div id="results" style="color:#8890a8;margin-top:12px">Run a search above...</div>
</div>
<script>
async function buildIndex(){
  document.getElementById("idx").textContent="Building... please wait.";
  const r=await fetch("/index",{method:"POST",headers:{"Content-Type":"application/json"},body:'{"folder":"course_docs"}'});
  const d=await r.json();
  document.getElementById("idx").textContent=r.ok?"Ready - "+d.chunks_indexed+" chunks indexed":"Error: "+d.detail;
}
async function doSearch(){
  const q=document.getElementById("q").value.trim();
  if(!q)return;
  document.getElementById("results").textContent="Searching...";
  const r=await fetch("/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:q})});
  const d=await r.json();
  if(!r.ok){document.getElementById("results").textContent="Error: "+d.detail;return;}
  if(!d.length){document.getElementById("results").textContent="No results found.";return;}
  document.getElementById("results").textContent=d.map((x,i)=>`[${i+1}] ${x.file} - Page ${x.page}  (${(x.score*100).toFixed(0)}%)\n${x.context}\n${"─".repeat(60)}`).join("\n\n");
}
</script></body></html>"""

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
'@ | Out-File -FilePath ".\CourseSearchBot\server.py" -Encoding utf8

Write-Host "  server.py written" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 5 — Write requirements_server.txt
# ---------------------------------------------------------------

@'
fastapi==0.115.6
uvicorn==0.32.1
pydantic==2.10.4
'@ | Out-File -FilePath ".\CourseSearchBot\requirements_server.txt" -Encoding utf8

Write-Host "  requirements_server.txt written" -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 6 — Git: initialize, add remote, commit, push
# ---------------------------------------------------------------

Write-Host "[5/6] Setting up Git and pushing to GitHub..." -ForegroundColor Yellow

# Make sure we're at the repo root
cd "C:\Users\Feroz Khan\universitydeleiverprojectcivil"

# Init git if not already done
git init

# Set identity (change email to yours)
git config user.name "Khan-Feroz211"
git config user.email "your@email.com"

# Remove old remote if exists, re-add clean
git remote remove origin 2>$null
git remote add origin https://github.com/Khan-Feroz211/Course-Cursor-bot.git

# Stage everything
git add .

# Commit
git commit -m "v2.0 - Course Search Bot: fixed structure, added Docker, server, security"

# Push
git branch -M main
git push -u origin main --force

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ALL DONE!" -ForegroundColor Green
Write-Host "  Your code is now live on GitHub." -ForegroundColor Green
Write-Host "  README is at the repo root." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
