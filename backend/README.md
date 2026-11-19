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

## Deploy no Railway

O projeto já vem com `Dockerfile`, `railway.json` (API) e `railway.worker.json` (Celery).

1. **Novo projeto** no Railway → *Deploy from GitHub repo* → `api-renave-digital`. Esse primeiro serviço é a API (usa `railway.json`).
2. **Adicione os bancos:** *New* → *Database* → **PostgreSQL** e **Redis**.
3. **Variáveis da API** (aba *Variables*):

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |
   | `DJANGO_SECRET_KEY` | valor aleatório longo |
   | `VAULT_MASTER_KEY` | gere com o comando da seção "Rodar localmente" e **guarde uma cópia em local seguro** |
   | `DJANGO_ALLOWED_HOSTS` | domínio público do serviço no Railway (ex.: `api-renave-digital-production.up.railway.app`) |
   | `CORS_ALLOWED_ORIGINS` | `https://app.renavedigital.kaibez.com.br` |
   | `PUBLIC_API_URL` | `https://app.renavedigital.kaibez.com.br` |
   | `DJANGO_ADMIN_URL` | caminho secreto para o admin técnico do Django (ex.: `interno-8f3k2/`) |
   | `RESEND_API_KEY` | chave do Resend |
   | `BUSCARS_API_KEY`, `BUSCARS_WEBHOOK_SECRET` | painel BusCars |
   | `CARVEN_BASE_URL`, `CARVEN_CLIENT_ID`, `CARVEN_CLIENT_SECRET` | Carven (produção: `https://www.carven.com.br`) |
   | `GERANET_API_KEY`, `GERANET_AMBIENTE` | Geranet (`1` produção, `2` homologação) |
   | `SENTRY_DSN` | opcional |

4. Em *Settings → Networking*, gere o domínio público da API.
5. **Worker:** *New* → *GitHub repo* → o mesmo repositório. Em *Settings → Config-as-code*, aponte para `railway.worker.json`. Copie as mesmas variáveis (no Railway dá para referenciar as da API) — o worker não precisa de domínio.
6. Cada deploy da API roda `scripts/release.sh` (migrações + catálogo inicial) antes de subir. O healthcheck é `/api/health/live`; `/api/health/ready` também verifica banco e Redis.
7. Crie o primeiro administrador: no serviço da API, *⋯ → Shell* (ou `railway run`) e `python manage.py createsuperuser`.

O app (Vercel) encaminha `https://app.renavedigital.kaibez.com.br/api/*` para o domínio da API no Railway, então o navegador fala só com o domínio do app.

Webhook de consultas para cadastrar no provedor: `https://app.renavedigital.kaibez.com.br/api/hooks/consultas`.
