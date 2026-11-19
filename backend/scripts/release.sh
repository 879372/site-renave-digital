#!/bin/sh
# Roda antes de cada deploy do serviço web: migrações e catálogo inicial (não sobrescreve o que o admin editou).
set -e
python manage.py migrate --noinput
python manage.py seed_products
