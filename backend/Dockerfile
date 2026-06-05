# Donna backend — multi-stage Docker build.
#
# Stage 1 (builder): installs Python deps into a venv so we can copy just the
# resolved site-packages into the runtime image (no pip, no build chain, no
# wheel cache).
# Stage 2 (runtime): minimal Python slim, non-root user, HEALTHCHECK wired to
# the FastAPI /health endpoint.

# ----- Stage 1: deps -------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Build deps (some wheels — e.g. bcrypt — need a compiler).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# ----- Stage 2: runtime ----------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Non-root user — anything we ship runs as `donna`, not as root.
RUN groupadd --system donna && useradd --system --gid donna --create-home donna

WORKDIR /app

# Only the resolved venv comes from the builder.
COPY --from=builder /opt/venv /opt/venv

# Source code (everything from `backend/` not excluded by .dockerignore).
COPY --chown=donna:donna . .

# Chroma writes its file-based index here. On Render we point CHROMA_DB_PATH
# at /tmp/chroma instead (ephemeral), but locally /app/data is convenient.
RUN mkdir -p /app/data && chown donna:donna /app/data

USER donna

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', int(os.environ.get('PORT','8000')))); s.close()"

# Render injects $PORT — shell form so the env var is expanded at start time.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
