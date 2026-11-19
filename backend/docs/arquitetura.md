# Arquitetura da Plataforma RENAVE DIGITAL

Plataforma B2B para revendas, concessionárias e despachantes com três módulos integrados:

| Módulo | Provedor | Documentação |
|---|---|---|
| Consultas veiculares | BusCars | https://buscars.com.br/docs |
| Estoque RENAVE + Comunicação de venda | Carven | https://hml.carven.com.br/docs |
| Emissão de NF-e | Geranet | https://nfe.geranet.net/documentacao/introducao |

Detalhes de cada API em [integracoes.md](integracoes.md).

## Visão geral

```
                 ┌──────────────────────────┐
  Navegador ───► │ CDN / Nginx (TLS, HSTS)  │
                 │  frontend React (estático)│
                 └────────────┬─────────────┘
                              │ /api (HTTPS, JWT)
                 ┌────────────▼─────────────┐
                 │ Django + DRF (gunicorn)   │  N réplicas, stateless
                 │  auth · orgs · wallet ·   │
                 │  consultas · renave ·     │
                 │  fiscal · audit           │
                 └──┬──────────┬─────────┬──┘
                    │          │         │
             ┌──────▼──┐  ┌────▼───┐ ┌───▼──────────┐
             │Postgres │  │ Redis  │ │ Celery workers│──► BusCars / Carven / Geranet
             │(dados)  │  │cache,  │ │ + beat        │
             └─────────┘  │filas,  │ └───────────────┘
                          │throttle│
                          └────────┘
```

- **Backend stateless**: escala horizontal atrás do balanceador. Sessão = JWT; estado compartilhado só em Postgres/Redis.
- **Chamadas a provedores** que podem demorar (NF-e, CRLV-e, sincronização de estoque, envio de comunicação) rodam em **Celery**; o front acompanha por polling do status.
- **Webhooks** (BusCars, Carven) entram por endpoints públicos com verificação de assinatura e só enfileiram trabalho.

## Repositório

```
renave-digital/
├── dist/            site institucional (Vercel) — inalterado
├── backend/         Django + DRF (uv)
├── frontend/        React + Vite + TypeScript
├── docs/            arquitetura e integrações
└── docker-compose.yml   Postgres + Redis para desenvolvimento
```

### Apps Django (`backend/`)

| App | Responsabilidade |
|---|---|
| `config/` | settings (base/dev/prod/test), urls, celery, wsgi/asgi |
| `core` | middleware de request-id, criptografia de campos, exceções, paginação, health |
| `accounts` | usuário (login por e-mail), JWT com refresh em cookie httpOnly, 2FA TOTP, bloqueio por tentativas |
| `organizations` | empresa (CNPJ), membros e papéis, clientes atendidos (despachante), contexto do tenant |
| `vault` | certificados digitais A1 cifrados (envelope AES-GCM), validação de titular e validade |
| `wallet` | carteira pré-paga, razão (ledger) imutável, reservas → captura/estorno |
| `audit` | trilha de auditoria de ações sensíveis (quem, empresa, IP, o quê) |
| `integrations` | clientes HTTP de BusCars, Carven e Geranet; log de chamadas com dados mascarados |
| `consultas` | catálogo e preço de venda por SKU, execução, laudo, histórico, webhook BusCars |
| `renave` | estoque RENAVE: aptidão, entrada, saída, documentos, sincronização (Carven) |
| `comunicacao` | comunicação de venda (Carven SCVV) |
| `fiscal` | dados fiscais do emitente, emissão/cancelamento/CC-e de NF-e (Geranet) |

## Multiempresa (tenancy)

- `Organization` = um CNPJ cliente da plataforma. `Membership` liga usuário ↔ empresa com papel: `owner`, `admin`, `operator`, `finance`, `viewer`.
- O front envia `X-Organization` em toda requisição; o backend valida que o usuário é membro ativo e aplica as permissões do papel. **Todo queryset é filtrado pela empresa do contexto** (mixin único `OrganizationScopedViewSet`), nunca por parâmetro livre.
- `ClientCompany`: despachantes/contadores operam RENAVE em nome de clientes (campo `cpf_cnpj` da Carven). Cada cliente tem o próprio certificado no vault.

## Autenticação e sessão

| Item | Decisão |
|---|---|
| Hash de senha | Argon2id |
| Access token | JWT de 10 min, guardado **só em memória** no front |
| Refresh token | 7 dias, cookie `httpOnly; Secure; SameSite=Strict; Path=/api/auth`, rotação a cada uso + blacklist |
| 2FA | TOTP (Google Authenticator etc.) com códigos de recuperação; obrigatório para `owner`/`admin` em produção |
| Força bruta | throttle por IP e por e-mail + bloqueio temporário após falhas (Redis) |
| Logout | revoga o refresh (blacklist) e limpa o cookie |
| CSRF | refresh em cookie SameSite=Strict + verificação de origem; API usa Bearer |

## Segurança

- **Segredos** só por variáveis de ambiente / secret manager; nada no repositório.
- **Certificados A1** e senhas: cifrados com AES-256-GCM por chave de dados, que por sua vez é cifrada pela chave mestra (`VAULT_MASTER_KEY`, rotacionável). Nunca voltam para o front; só o servidor decifra no momento da chamada ao provedor.
- **PII** (CPF/CNPJ de compradores, endereço): campos cifrados quando não precisam de busca; logs sempre mascarados (`***.456.789-**`).
- **Cabeçalhos**: HSTS, CSP restritiva, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
- **CORS** só para o domínio do app. Admin Django em caminho não óbvio, restrito a staff com 2FA.
- **Webhooks**: HMAC SHA-256 com comparação em tempo constante + janela de 5 min + deduplicação por `delivery id`.
- **Idempotência**: toda chamada cobrada envia `Idempotency-Key` derivada do id interno; reenvios não cobram duas vezes.
- **Auditoria**: toda ação que cobra, emite documento fiscal, mexe no RENAVE ou altera certificado/membros gera `AuditEvent`.
- **LGPD**: finalidade declarada por consulta, retenção configurável dos laudos, exportação/exclusão de dados do titular.

## Carteira e cobrança

Modelo de razão (ledger) imutável — saldo é a soma dos lançamentos, com saldo materializado atualizado na mesma transação (`SELECT … FOR UPDATE`).

```
recarga  (+)  ──►  saldo
consulta:  reserva (−preço)  ──►  captura  (provedor cobrou)
                               └─►  estorno  (+preço, provedor não cobrou)
```

Isso espelha exatamente o modelo da BusCars (`cobrado`, `valorCobradoCentavos`). Operações tarifadas da Carven (entrada, saída, cancelamentos) e NF-e autorizadas em produção usam o mesmo mecanismo.

Recarga via Pix: interface `PaymentProvider` (gateway a definir). Até lá, crédito manual pelo admin com auditoria.

## Desempenho e escala

- Postgres com índices nas chaves de consulta (empresa + data, placa, status) e pool de conexões.
- Redis: cache (catálogo BusCars, token Carven), throttling, broker do Celery.
- Paginação por cursor nas listagens grandes (histórico, estoque).
- Gunicorn com workers sync + timeouts curtos; trabalho lento sempre no Celery.
- Front: build estático com code-splitting por rota, cache imutável de assets, TanStack Query para cache no cliente.

## Observabilidade

- Logs JSON estruturados com `request_id`, `organization_id`, `user_id` (sem PII).
- Sentry no back e no front.
- `/api/health/live` e `/api/health/ready` (checa Postgres e Redis) para o orquestrador.
- `IntegrationCall`: cada chamada a provedor registra endpoint, status, latência, custo e erro (corpo mascarado) — base para painel de saúde dos provedores e conciliação de custos.

## Ambientes

| Ambiente | Provedores |
|---|---|
| local | homologação (BusCars: chave de teste; Carven: `homologacao.carven.com.br`; Geranet: `ambiente=2`) |
| staging | homologação |
| produção | produção |

## Pontos em aberto

1. **Gateway de pagamento** para recarga Pix.
2. **NF-e de veículo**: a documentação da Geranet não mostra o grupo `veicProd` (chassi, cor, RENAVAM…). Confirmar com o suporte como enviar os dados do veículo ou se vão em `informacaoAdicional` do item.
3. **Carven produção**: `client_id`/`client_secret` são por usuário/informante — definir se a plataforma usa um par único (com clientes cadastrados via `salvar-certificado`) ou um par por empresa.
4. **Tabela de municípios** Carven (XLSX) a importar como dado de referência.
