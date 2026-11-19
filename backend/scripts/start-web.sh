#!/bin/sh
# Servidor da API. Workers sync: o trabalho lento (NF-e, sincronizações) fica no Celery.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-3}" \
  --timeout 90 \
  --graceful-timeout 30 \
  --forwarded-allow-ips "*" \
  --access-logfile - \
  --error-logfile -
