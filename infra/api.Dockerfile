# syntax=docker/dockerfile:1
# ---------- builder ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY apps/api/yatraai/__init__.py apps/api/yatraai/__init__.py

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip setuptools wheel && pip install .

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/apps/api"

RUN useradd --create-home --uid 10001 yatra
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
COPY data/seed ./data/seed
COPY pipelines ./pipelines
COPY ml ./ml
COPY evaluation ./evaluation
COPY infra/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh && chown -R yatra:yatra /app
USER yatra

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "yatraai.main:app", "--host", "0.0.0.0", "--port", "8000"]
