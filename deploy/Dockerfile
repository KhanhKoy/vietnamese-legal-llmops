FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    APP_MODE=api \
    PORT=8000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first — default PyPI torch pulls multi-GB NVIDIA CUDA wheels.
COPY deploy/requirements-deploy.txt /tmp/requirements-deploy.txt
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch \
    && pip install --no-cache-dir -r /tmp/requirements-deploy.txt \
    && rm -f /tmp/requirements-deploy.txt

COPY . .
RUN chmod +x /app/deploy/entrypoint.sh

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl --fail "http://127.0.0.1:${PORT:-8000}/" || exit 1

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
