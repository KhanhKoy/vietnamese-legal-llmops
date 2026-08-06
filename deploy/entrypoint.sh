#!/bin/sh
set -eu

if [ "${APP_MODE:-api}" = "chainlit" ]; then
  case "${DEBUG:-false}" in
    ""|0|1|false|true|no|yes|off|on) ;;
    *) export DEBUG=false ;;
  esac
  exec chainlit run app.py --host 0.0.0.0 --port "${PORT:-8000}"
fi

exec python scripts/run_api.py
