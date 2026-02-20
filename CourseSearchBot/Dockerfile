# ============================================================
#  Course Search Bot — Dockerfile
#  Runs the app as a persistent background service (API mode)
#  Access via browser at: http://localhost:8000
# ============================================================

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────
RUN apt-get update && apt-get install -y \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────
COPY requirements.txt .
COPY requirements_server.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements_server.txt

# ── Copy application code ─────────────────────────────────────
COPY . .

# ── Create necessary directories ──────────────────────────────
RUN mkdir -p data course_docs

# ── Expose API port ───────────────────────────────────────────
EXPOSE 8000

# ── Health check — keeps container alive & monitored ─────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Start the web server (stays alive forever) ────────────────
CMD ["python", "server.py"]
