#!/bin/sh
set -eu

MODE="${APP_MODE:-api}"
PORT="${PORT:-8000}"

case "$MODE" in
  streamlit)
    STREAMLIT_PORT="${PORT:-8501}"
    exec streamlit run streamlit_app.py \
      --server.address 0.0.0.0 \
      --server.port "$STREAMLIT_PORT" \
      --browser.gatherUsageStats false
    ;;
  chainlit)
    case "${DEBUG:-false}" in
      ""|0|1|false|true|no|yes|off|on) ;;
      *) export DEBUG=false ;;
    esac
    exec chainlit run app.py --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  api|*)
    # Default: RAG /ask API used by Streamlit (src.api.main).
    # Override with API_MODULE=api.app:app for Cognito-protected /api routes.
    export PYTHONPATH="/app:/app/src${PYTHONPATH:+:$PYTHONPATH}"
    exec python -m uvicorn "${API_MODULE:-api.main:app}" \
      --host "${HOST:-0.0.0.0}" \
      --port "${PORT:-8000}"
    ;;
esac
