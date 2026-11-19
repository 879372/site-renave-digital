#!/bin/sh
# Worker Celery + agendador (beat) num processo só. Para escalar, separe o beat em outro serviço.
exec celery -A config worker -B -l info --concurrency "${CELERY_CONCURRENCY:-2}"
