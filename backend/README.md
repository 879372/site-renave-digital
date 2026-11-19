# api-renave-digital

API da plataforma RENAVE DIGITAL: consultas veiculares, estoque RENAVE, comunicação de venda, emissão de NF-e, carteira pré-paga e painel administrativo.

Django 5.2 + Django REST Framework + PostgreSQL + Redis + Celery, gerenciado com [uv](https://docs.astral.sh/uv/).

## Rodar localmente

```bash
docker compose up -d
```

```bash
cp .env.example .env
```

Preencha `DJANGO_SECRET_KEY` e `VAULT_MASTER_KEY` no `.env`. Para gerar a chave do cofre:

```bash
uv run python -c "from vault.crypto import generate_master_key as g; print(g())"
```

```bash
uv run python manage.py migrate && uv run python manage.py seed_products
```

```bash
uv run python manage.py runserver 8010
```

```bash
uv run celery -A config worker -B -l info
```

Crie um acesso de administrador (entra no painel `/admin` do app):

```bash
uv run python manage.py createsuperuser
```

## Testes e qualidade

```bash
uv run pytest && uv run ruff check .
```

## Estrutura

| App | Responsabilidade |
|---|---|
| `config/` | Settings (base, dev, prod, test), URLs, Celery |
| `accounts` | Usuários, JWT com refresh em cookie, 2FA, LGPD (exportar/excluir dados) |
| `organizations` | Empresas, membros e papéis, clientes atendidos |
| `vault` | Certificados A1 cifrados (AES-256-GCM em envelope) |
| `wallet` | Carteira pré-paga, razão imutável, recargas, tabela de preços |
| `audit` | Trilha de auditoria |
| `integrations` | Clientes dos provedores, webhooks, consultas públicas de CNPJ/CEP |
| `consultas`, `renave`, `comunicacao`, `fiscal` | Módulos de negócio |
| `backoffice` | API do painel administrativo (`/api/admin/*`) |

Arquitetura e decisões: [docs/arquitetura.md](docs/arquitetura.md). Provedores: [docs/integracoes.md](docs/integracoes.md).

## Produção

- `DJANGO_SETTINGS_MODULE=config.settings.prod`, HTTPS no proxy.
- Variáveis: `DJANGO_SECRET_KEY`, `VAULT_MASTER_KEY` (guarde com cuidado: sem ela os certificados ficam ilegíveis), `DATABASE_*`, `REDIS_URL`, `RESEND_API_KEY`, chaves dos provedores e `SENTRY_DSN`.
- `DJANGO_ALLOWED_HOSTS=app.renavedigital.kaibez.com.br`, `CORS_ALLOWED_ORIGINS=https://app.renavedigital.kaibez.com.br`, `PUBLIC_API_URL=https://app.renavedigital.kaibez.com.br`.
- `gunicorn config.wsgi -w 4 --timeout 60` + workers Celery.
