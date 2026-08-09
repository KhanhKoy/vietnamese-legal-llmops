FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    APP_MODE=api \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/deploy/entrypoint.sh

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD-SHELL \
  if [ "$APP_MODE" = "streamlit" ]; then \
    curl --fail "http://127.0.0.1:${PORT:-8501}/_stcore/health"; \
  elif [ "$APP_MODE" = "chainlit" ]; then \
    curl --fail "http://127.0.0.1:${PORT:-8000}/"; \
  else \
    curl --fail "http://127.0.0.1:${PORT:-8000}/"; \
  fi

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
