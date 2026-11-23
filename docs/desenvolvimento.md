# Desenvolvimento local

## Pré-requisitos

- Docker (Postgres 16 + Redis 7)
- [uv](https://docs.astral.sh/uv/) (Python 3.13)
- Node 20+

## Subir tudo

```bash
docker compose up -d
```

```bash
cd backend && cp .env.example .env   # preencha DJANGO_SECRET_KEY e VAULT_MASTER_KEY
```

```bash
cd backend && uv run python -c "from vault.crypto import generate_master_key as g; print(g())"
```

```bash
cd backend && uv run python manage.py migrate && uv run python manage.py seed_products
```

```bash
cd backend && uv run python manage.py runserver 8010
```

```bash
cd backend && uv run celery -A config worker -B -l info
```

```bash
cd frontend && npm install && npm run dev
```

App: http://localhost:5180 (o Vite repassa `/api` para a API em 8010).
Admin interno: http://localhost:8010/painel-interno/ (crie com `uv run python manage.py createsuperuser`).
Documentação da API (só em DEBUG): http://localhost:8010/api/docs/

Painel administrativo: http://localhost:5180/admin (conta local de equipe: `equipe@renavedigital.test` / `Admin-Renave-2026`).

Conta de teste criada no ambiente local: `demo@renavedigital.test` / `Demo-Renave-2026` (CNPJ 11.222.333/0001-81). Use só em desenvolvimento.

## Credenciais dos provedores

Preencha em `backend/.env`:

| Variável | Onde obter |
|---|---|
| `BUSCARS_API_KEY`, `BUSCARS_WEBHOOK_SECRET` | Painel BusCars → Chaves |
| `CARVEN_CLIENT_ID`, `CARVEN_CLIENT_SECRET` | Homologação: página "Ambientes e Autenticação" da documentação Carven. Produção: Minha Conta → Configurações → Chave da API |
| `GERANET_API_KEY` | Painel Geranet NFe (`GERANET_AMBIENTE=2` = homologação, sem cobrança) |

Sem essas chaves a plataforma funciona, mas as operações nos provedores retornam "serviço indisponível" e estornam o valor reservado.

## Recargas

Até o gateway Pix ser contratado, as recargas ficam pendentes e o financeiro confirma no admin em **Carteira → Top ups → "Confirmar pagamento e creditar"** (fica registrado na auditoria).

## Testes e qualidade

```bash
cd backend && uv run pytest && uv run ruff check .
```

```bash
cd frontend && npm run typecheck && npm run build
```

## Produção (checklist)

- `DJANGO_SETTINGS_MODULE=config.settings.prod`, HTTPS no proxy (`X-Forwarded-Proto`).
- `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` e `VAULT_MASTER_KEY` próprios, guardados em secret manager. **Perder a `VAULT_MASTER_KEY` torna os certificados ilegíveis.**
- Postgres e Redis gerenciados, com backup e criptografia em repouso.
- API: `gunicorn config.wsgi -w 4 --timeout 60` atrás de Nginx/ALB; workers Celery separados (fila de NF-e e RENAVE).
- Frontend: `npm run build` e servir `frontend/dist` por CDN com cache imutável em `/assets` e fallback SPA para `index.html`.
- Webhook BusCars: `https://<api>/api/hooks/consultas`. Comunicação de venda: `PUBLIC_API_URL` com https ativa a `url_notificacao` da Carven.
- `SENTRY_DSN` configurado; monitorar `/api/health/ready`.

## Domínios

- Site: https://renavedigital.kaibez.com.br (`dist/`)
- Plataforma: https://app.revendadigital.kaibez.com.br (`frontend/` + API em `/api`)

Em produção, defina no backend: `DJANGO_ALLOWED_HOSTS=app.revendadigital.kaibez.com.br`, `CORS_ALLOWED_ORIGINS=https://app.revendadigital.kaibez.com.br` e `PUBLIC_API_URL=https://app.revendadigital.kaibez.com.br`.

## E-mails

Enviados pela API HTTPS do Resend (`https://api.resend.com/emails`), em segundo plano pelo Celery, com novas tentativas automáticas.

| Uso | Endereço |
|---|---|
| Remetente (recuperação de senha, convites) | `nao-responda@kaibez.com.br` |
| Respostas dos usuários (reply-to) | `contato@kaibez.com.br` |
| Encarregado de dados (LGPD) | `privacidade@kaibez.com.br` |

No Resend: verifique o domínio `kaibez.com.br` (registros SPF/DKIM no DNS) e crie a API key em `RESEND_API_KEY`. Os endereços `contato@` e `privacidade@` precisam ser caixas que recebam mensagens.

## Antes de publicar (preencher)

| O quê | Onde |
|---|---|
| Razão social, CNPJ, endereço e nome do Encarregado (DPO) | `frontend/src/lib/legal.ts` |
| Versão dos documentos legais (ao alterar o texto, mude nos dois lugares; usuários verão o pedido de novo aceite) | `frontend/src/lib/legal.ts` e `LEGAL_VERSION` no `.env` |

Os textos de Termos de Uso e Política de Privacidade são uma base sólida para a LGPD, mas devem ser revisados por um advogado antes da publicação.

Depois de publicar o site, cadastre o domínio no Google Search Console e envie o `sitemap.xml`.

## Preenchimento automático

CNPJ e CEP são consultados no servidor em fontes públicas e gratuitas (`backend/integrations/lookups.py`), com cache. O nome das fontes não aparece para o usuário.
