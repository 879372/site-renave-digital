# Integrações — resumo técnico

Lido das documentações oficiais em 2026-11-18. Em caso de divergência, vale a documentação do provedor.

## BusCars — consultas veiculares

- Base: `https://api.buscars.com.br` · Auth: header `x-api-key: bk_live_...` (só no servidor).
- `POST /v1/consulta` `{ sku, valor }` → `{ success, data: { consultaId, valorCobradoCentavos, resultado: { familia, encontrado, dados, situacao?, mensagem? } } }`
- `POST /v1/consultas` (assíncrono, `Idempotency-Key` obrigatório) → `202 { consultaId, status: PENDENTE }`; `GET /v1/consultas/{id}/status` → `PENDENTE | PROCESSANDO | SUCESSO | FALHA`.
- `GET /v1/catalogo` (grátis): SKUs, campos de entrada, preço da conta, `fallback.status`.
- `GET /v1/saldo`: `saldoDisponivelCentavos` (pré-pago).
- SKUs `-sf` (sem fallback, mais barato) e `-cf` (com fallback).
- Cobrança: sucesso cobra; falha/não encontrado só cobra se `cobrado: true`. Repetir a mesma consulta cobra de novo — só a mesma `idempotency-key` evita.
- Webhook: eventos `consulta.sucesso | consulta.sem_resultado | consulta.falha`; cabeçalhos `x-buscars-event`, `x-buscars-delivery`, `x-buscars-timestamp`, `x-buscars-signature` (lista `sha256=<hmac(timestamp + "." + corpo_cru)>`). Responder 2xx em < 10 s; o corpo só traz `statusUrl` — buscar o resultado por lá.
- Erros: 400/422 input, 401 chave, 402 sem saldo, 404 SKU, 429 (`Retry-After`), 503 (retry com mesma idempotency-key).
- Opcional: `x-resposta-cifrada: 1` → AES-256-GCM.

## Carven — comunicação de venda e RENAVE

- Homologação `https://homologacao.carven.com.br` · Produção `https://www.carven.com.br`. Prefixo `/api`.
- `POST /api/auth/login` `{ client_id, client_secret }` → `access_token` (validade `expires_after` = 3600 s). `POST /api/auth/refresh`.
- Headers: `Authorization: Bearer`, `Cache-Control: no-cache`, `Content-Type: application/json`.

### Comunicação de venda (SCVV)
- `POST /api/comunicacao-venda/inserir` → `protocolo` (não transmite sozinho).
- `POST /api/comunicacao-venda/transmitir/enviar/{protocolo}` · `.../transmitir/cancelar/{protocolo}`
- `GET /api/comunicacao-venda/{protocolo}` (situação 1 Cadastrada · 2 Comunicada · 3 Certidão gerada · 4 Cancelada · 5 Erro · 6 Excluída · 7 Bloqueada · 8 Não desbloqueada), `PUT` para alterar, `/historico`, `/comprovante` (PDF), `/gerar-certidao`.
- Corpo: `vendedor`, `comprador{endereco}`, `venda{cidade,data DD/MM/AAAA,valor}`, `veiculo{placa,renavam,anos,crv{...}}`, `arquivos[]` (DUT, máx. 2), `url_notificacao`.

### RENAVE (usados) — prefixo `/api/renave`
- Todas exigem `cpf_cnpj` (define qual certificado é usado). Certificado do cliente via `POST /salvar-certificado-renave` (multipart: `cpf_cnpj`, `nome_cliente`, `certificado`, `chave-certificado`).
- Fluxo: aptidão → entrada → atualizar/listar estoque (resposta da entrada não traz id) → termos/CRLV-e/NF → saída → termo de saída/ATPV-e → ATPV-e assinada.
- Tarifadas: entrada, saída, cancelamento de entrada, cancelamento de saída.
- `POST /usado/estoque/atualizar` tem intervalo mínimo (429 com `minutos_para_proxima_atualizacao`).
- Erros: 422 validação, 403 sem tabela de preço, 4xx/5xx repassados do RENAVE, 502 RENAVE indisponível.

## Geranet — NF-e

- Base `https://nfe.geranet.net/api/v1` · Auth `Authorization: Bearer gn_...`.
- `POST /nfe/emitir` com `certificadoDigital` (A1 em **hexadecimal**), `senhaCertificadoDigital`, `ambiente` (1 produção, 2 homologação), `modelo` 55, `ufEmitente`, `nfe{empresa, cliente, itens, pagamento, ...}`.
- Resposta: `{ situacao, mensagem, xml(hex), pdf(hex), cstat, numero, chave, protocolo }`; erro 422 com `cstat` da SEFAZ.
- Também: `/nfe/consultar`, `/nfe/cancelar`, `/nfe/carta-correcao`, `/nfe/inutilizar-numeracao`, `/nfe/gerar-pdf`, `/cnpj/consultar`, `/uso`.
- Homologação (`ambiente=2`) não é cobrada.
- **Atenção**: grupo de veículo (`veicProd`) não aparece na documentação — confirmar com o suporte.
