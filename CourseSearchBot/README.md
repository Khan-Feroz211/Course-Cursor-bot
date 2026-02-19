# Course Search Bot

AI-powered semantic search for university course PDFs.

---

## What It Does

Drop your lecture PDFs in, type a question in plain English, and instantly find every relevant paragraph across all your documents.

---

## How To Run

### Desktop App (Windows)
```
1. Run Setup_Windows.bat  (first time only)
2. Run Launch_Windows.bat (every time after)
```

### Always-Alive Server (Docker)
```
docker-compose up -d
Then open: http://localhost:8000
```

---

## Add Your PDFs

Put all your PDF files inside the `course_docs` folder, then click **Build Index** in the app.

---

## Requirements

- Python 3.11 or newer
- Docker Desktop (only if using server mode)

---

*Version 2.0*
