# ----------------------------------------------------------------
# Backend image — FastAPI + LangGraph agent (api.main:app)
# Built from the repo root so the `api` and `database` packages are
# importable. Connects to a remote Postgres via PG_* env vars.
# ----------------------------------------------------------------
FROM python:3.12-slim

# Faster, cleaner Python in containers + a writable matplotlib cache
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Install dependencies first so this layer is cached across code changes
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code (frontend / node_modules / logs excluded via .dockerignore)
COPY . .

EXPOSE 8000

# Container-level health check hits the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8009"]
