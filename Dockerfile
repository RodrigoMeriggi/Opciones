FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRADING_MODE=paper \
    LIVE_TRADING_ENABLED=false \
    EMERGENCY_STOP=false \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY config ./config
COPY scripts ./scripts

RUN pip install --upgrade pip && pip install -e . \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/health\")" || exit 1

# Render/Railway inyectan $PORT
CMD ["sh", "-c", "uvicorn opciones.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
