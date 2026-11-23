# API REVENDA DIGITAL — imagem de produção (web e worker usam a mesma imagem)
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /usr/local/bin/uv

WORKDIR /app

# Dependências primeiro (camada em cache enquanto pyproject/uv.lock não mudam)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# collectstatic precisa de settings válidos; valores descartáveis só para o build
RUN DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=build VAULT_MASTER_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA \
    RESEND_API_KEY=build python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

ENV DJANGO_SETTINGS_MODULE=config.settings.prod PORT=8000
EXPOSE 8000

CMD ["sh", "scripts/start-web.sh"]
