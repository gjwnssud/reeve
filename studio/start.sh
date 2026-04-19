#!/bin/bash
set -e

SSL_ARGS=()
if [ -n "$SSL_KEYFILE" ] && [ -n "$SSL_CERTFILE" ]; then
  SSL_ARGS=(--ssl-keyfile "$SSL_KEYFILE" --ssl-certfile "$SSL_CERTFILE")
fi

exec uvicorn studio.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir /app/studio \
  "${SSL_ARGS[@]}"
