# syntax=docker/dockerfile:1.6
# ─── base stage ────────────────────────────────────────────
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libsndfile1 \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── deps stage ────────────────────────────────────────────
FROM base AS deps
COPY apps/ai/pyproject.toml ./
RUN pip install --upgrade pip wheel \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir "gunicorn>=22.0.0"

# ─── runtime stage ─────────────────────────────────────────
FROM base AS runtime

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

RUN groupadd --system app && useradd --system --gid app --no-create-home app \
    && mkdir -p /app/storage \
    && chown -R app:app /app

COPY --chown=app:app apps/ai/pyproject.toml ./
COPY --chown=app:app apps/ai/app ./app

USER app
EXPOSE 8100

ENV GUNICORN_WORKERS=2 \
    GUNICORN_TIMEOUT=300 \
    GUNICORN_GRACEFUL_TIMEOUT=30

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=60s \
    CMD curl -fsS http://localhost:8100/health || exit 1

CMD ["sh", "-c", "exec gunicorn app.main:app \
        --workers ${GUNICORN_WORKERS} \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8100 \
        --timeout ${GUNICORN_TIMEOUT} \
        --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT} \
        --keep-alive 5 \
        --access-logfile - \
        --error-logfile - \
        --log-level info"]
