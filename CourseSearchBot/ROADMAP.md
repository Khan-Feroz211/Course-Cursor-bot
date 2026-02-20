# Course Search Bot — Full Roadmap & Backend Plan

---

## Do You Need a Backend?

### RIGHT NOW — No backend needed
Everything runs locally on the client's computer:
- PDFs stored in course_docs/ on their PC
- AI index stored in data/ on their PC
- No internet required after first setup

This is perfect for a single client who owns the software.

### When you WILL need a backend:

| Situation | Need Backend? |
|---|---|
| One client, runs on their PC | No |
| Client wants browser/phone access | Yes |
| Multiple students share documents | Yes |
| Monthly subscription model | Yes |
| Cloud backup of PDFs | Yes |
| Selling to 10+ clients | Yes |

For now: sell as a desktop tool. Add backend in Stage 4.

---

## Stage 1 — Foundation (DONE)
Version 2.0 | Sell for $50–$150 one-time

- Semantic AI search (FAISS + SentenceTransformers)
- PDF extraction with OCR fallback
- Smart re-indexing on file changes
- Security: SQLite, SHA-256 integrity, input sanitizer
- Threaded GUI, never freezes
- Dark professional UI
- Export to CSV and PDF
- Docker always-alive server mode
- FastAPI browser UI
- Windows + Mac scripts

---

## Stage 2 — Smart Features (Next)
Version 2.1 | 1–2 weeks effort | Sell for $150–$300

2A — Chat Q&A Mode
  The app answers your question directly, then shows sources.
  Uses Ollama (free, offline) or OpenAI API.

2B — Search History
  Every search saved, shown in a sidebar.
  One click to re-run any past search.

2C — Multi-Folder Support
  Add Year 1, Year 2, Thesis as separate labeled folders.
  Filter search results by folder.

2D — Jump To Page
  Double-click any result, PDF opens at that exact page.

---

## Stage 3 — Polish (2–3 weeks after Stage 2)
Version 2.2 | Sell for $300–$600

3A — Splash screen with loading animation
3B — Settings panel (no YAML editing needed)
3C — Windows code signing (fixes the blue warning permanently)
3D — Auto-updater (checks GitHub, notifies user of new version)
3E — Proper installer (.msi for Windows, .dmg for Mac)

---

## Stage 4 — Backend + Web App (3–4 weeks)
Version 3.0 | Charge $20–$50/month per user

Tech Stack:
  Frontend:  Browser (React or HTML)
  Backend:   FastAPI — already started in server.py
  Database:  PostgreSQL (users, history, settings)
  Storage:   AWS S3 or Cloudflare R2 (PDFs in cloud)
  Auth:      JWT login tokens
  Hosting:   Railway.app or Render.com

Features:
4A — User login (email + password, any device)
4B — Cloud PDF storage (upload from browser)
4C — Team mode (professor uploads, students all search)
4D — Usage dashboard (for you to monitor the service)

---

## Stage 5 — AI Superpowers (2–3 weeks)
Version 3.5 | University license $500–$2000/year

5A — Study tools (quiz generator, flashcards, chapter summaries)
5B — Citation generator (APA, MLA, Harvard, one click)
5C — Multilingual search (Arabic, Urdu, French)
5D — Analytics dashboard (most searched topics, usage reports)

---

## Money Map

Stage 1 (now)  →  $50–$150  one-time
Stage 2        →  $150–$300 one-time
Stage 3        →  $300–$600 packaged product
Stage 4        →  $20–50/month subscription (recurring!)
Stage 5        →  $500–$2000/year university license

Stage 4 is where you stop selling once and start earning monthly.
