# Revenda Digital — plano de implementação

Sistema de gestão para **revendas multimarcas** (não concessionária). A plataforma, que se chamava RENAVE DIGITAL, passou a se chamar **REVENDA DIGITAL** (2026-11-22). Backend Django + React. Domínio: revendadigital.kaibez.com.br.

## 1. Produto e cobrança

Cobrança: plano mensal + RENAVE por uso. O antigo produto RENAVE Digital virou o plano **Grátis**.

O **Despachante Digital é outro sistema**, sem relação com este: não há integração nem carteira compartilhada.

### Planos

| | Grátis | Essencial | Profissional | Premium |
|---|---|---|---|---|
| Preço/mês | R$ 0 | R$ 99,90 | R$ 159,90 | R$ 269,90 |
| Veículos em estoque (não vendidos) | 20 | 40 | 100 | ilimitado |
| Usuários | 1 | 3 | 6 | ilimitado |
| RENAVE (R$ 30,00 por operação) | pré-pago | na fatura | na fatura | na fatura |
| Estoque, venda simples, dashboard básico, FIPE | ✓ | ✓ | ✓ | ✓ |
| Consulta por placa inclusa por mês | 10 | 100 | 300 | 1.000 |
| Nota fiscal (até 3 mil/mês) | — | ✓ | ✓ | ✓ |
| Custos por veículo, financeiro, contratos, avaliação | — | ✓ | ✓ | ✓ |
| CRM, comissões, consignação, site, anúncios | — | — | ✓ | ✓ |
| Financiamento, multi-loja, relatórios avançados, pós-venda | — | — | — | ✓ |
| Loja extra (outro CNPJ) | — | — | — | + R$ 49,90 |

- **Teste reverso:** conta nova ganha 14 dias do Profissional e depois cai para o Grátis se não assinar.
- **Anual:** 12 meses pelo preço de 10.
- **Custos de referência:** Carven R$ 19,90 por operação (já com a taxa do Serpro), nota fiscal R$ 25 por CNPJ/mês, servidor ~R$ 30/mês.

## 2. Arquitetura

### O que já existe e é reaproveitado

| App | Uso no Revenda Digital |
|---|---|
| `accounts`, `organizations` | login, empresa (CNPJ), membros e papéis. Ganha papel **vendedor** |
| `vault` | certificado A1 para RENAVE e NF-e |
| `wallet` | razão imutável e reserva → captura. Ganha **limite de crédito** (pós-pago) |
| `renave`, `comunicacao` | entrada e saída no RENAVE, ATPV-e, disparadas pelo estoque e pela venda |
| `fiscal` | NF-e de entrada (compra) e de saída (venda) |
| `integrations` | ganha clientes FIPE (Parallelum) e placa (API PLACAS) |
| `audit` | trilha de tudo que cobra, emite nota ou mexe em dinheiro |

### Apps novos

| App | Responsabilidade |
|---|---|
| `billing` | planos, assinatura, faturas, direitos por plano (recursos e limites), gateway de pagamento |
| `pessoas` | cadastro único de clientes, fornecedores e proprietários (consignação) |
| `estoque` | veículo comercial: dados, fotos, opcionais, status, preços, custos, documentos, avaliação de compra |
| `vendas` | proposta, negociação, pagamentos combinados, reserva, fechamento, comissões |
| `financeiro` | contas a pagar e a receber, caixa e contas bancárias, categorias, DRE simples |
| `contratos` | modelos e geração de PDF (compra e venda, consignação, procuração, garantia, recibo) |
| `crm` | leads, funil, origens, tarefas de retorno (fase 2) |
| `vitrine` | site público da loja e integrador de anúncios (fase 2) |
| `financiamento` | ficha cadastral, simulação, propostas por banco (fase 3) |

### Decisões técnicas

- **Dois estoques, um vínculo.** `estoque.Vehicle` é o carro comercial (preço, custos, fotos). `renave.StockVehicle` continua como espelho do RENAVE. A ligação é um `OneToOne` opcional: o lojista pode ter carro no estoque sem ter dado entrada no RENAVE.
- **Direitos por plano num só lugar:** `billing.entitlements.has_feature(org, "fiscal")` e `limit(org, "vehicles")`, mais uma permissão DRF `RequiresFeature("fiscal")` nas views. O front recebe os direitos em `/api/billing/me` para mostrar o cadeado e o botão de upgrade.
- **Carteira pós-pago:** `Wallet.credit_limit_cents` (0 no Grátis e no teste). A restrição passa de `balance >= 0` para `balance >= -credit_limit`. No fechamento mensal, o saldo negativo vira item da fatura e um lançamento `INVOICED` zera a carteira. Fatura vencida há mais de 5 dias bloqueia novas operações cobradas.
- **Dinheiro sempre em centavos** (`BigIntegerField`), como no restante do código.
- **Fotos:** armazenamento S3-compatível (Cloudflare R2 ou S3) via `django-storages`, com miniatura gerada no Celery.
- **Multi-loja (fase 3):** cada loja continua sendo uma `Organization`. Um `OrganizationGroup` liga as lojas à assinatura da loja principal, e o usuário troca de loja pelo seletor de empresa que já existe.

## 3. Fases

### Fase 0 — Fundação de cobrança ✅ implementada

**Objetivo:** a plataforma sabe o plano de cada empresa e cobra a mensalidade.

- `billing`: `Plan`, `PlanFeature` (recurso ou limite), `Subscription` (status: trial, active, past_due, canceled; ciclo mensal ou anual), `Invoice` e `InvoiceItem` (mensalidade, RENAVE do mês, loja extra).
- Gateway com assinatura recorrente, Pix, boleto e cartão. **Asaas**. A interface `PaymentProvider` de `wallet/payments.py` passa a cobrir também a assinatura.
- Webhook do gateway: pagamento confirmado, atrasado, cancelado.
- `Wallet.credit_limit_cents` e o fechamento mensal (tarefa no Celery beat).
- Teste reverso de 14 dias no cadastro da empresa revenda.
- Direitos por plano no backend e no front (cadeado e tela de planos).
- Novos papéis e permissões: `vendedor`, `estoque.manage`, `vendas.operate`, `financeiro.manage`.
- Backoffice: planos, assinaturas, faturas, conceder dias de teste.

**Pronto quando:** a loja escolhe um plano, paga pelo gateway em homologação, recebe os recursos do plano, e o RENAVE do mês aparece na fatura seguinte.

**Como ficou:**
- Uma fatura por mês gerada pela plataforma (mensalidade + consumo) e enviada ao Asaas como cobrança avulsa (`billingType=UNDEFINED`): o lojista escolhe Pix, boleto ou cartão no link. Não usamos a assinatura recorrente do Asaas, porque o valor muda com o consumo.
- Sem `ASAAS_API_KEY`, faturas e recargas ficam para confirmação manual no backoffice.
- Lojas que já existiam ganham o teste de 14 dias na primeira vez que o sistema consulta o plano delas.
- NF-e sai sem cobrança por nota para quem tem o recurso no plano. Cancelar e corrigir nota continua liberado mesmo depois de descer de plano.
- Falta: validar no sandbox do Asaas com chave real e cadastrar o webhook no painel (`/api/hooks/asaas`).

### Fase 1 — MVP (lançar Grátis e Essencial)

**Objetivo:** a loja opera o dia a dia: compra, prepara, vende e vê o resultado.

1. **Pessoas:** clientes e fornecedores com CPF/CNPJ, endereço por CEP, documentos sensíveis cifrados.
2. **Estoque:**
   - cadastro pela placa (API PLACAS) com FIPE automática (Parallelum);
   - fotos com ordenação e capa, opcionais;
   - status: em preparação, disponível, reservado, vendido;
   - próprio ou consignado (só o campo nesta fase);
   - preço de venda e preço mínimo, dias em estoque;
   - documentos anexos: CRLV, laudo cautelar;
   - botão "dar entrada no RENAVE", que reaproveita `renave.service`;
   - limite de veículos do plano aplicado.
3. **Compra e avaliação:** checklist com fotos, FIPE de referência, valor oferecido, aprovação. Aprovado, vira veículo no estoque, gera a conta a pagar e, se configurado, a NF-e de entrada.
4. **Custos por veículo:** lançamentos (funilaria, mecânica, estética, despachante, documentação) com fornecedor. Geram conta a pagar e somam no custo total e na margem prevista.
5. **Vendas:**
   - proposta com várias formas de pagamento: entrada, troca (que vira uma avaliação), financiamento, cartão, Pix;
   - reserva com sinal;
   - fechamento: veículo vendido, contas a receber, NF-e de saída, saída no RENAVE e comunicação de venda;
   - sobra (lucro) calculada por venda.
6. **Financeiro básico:** contas a pagar e a receber (manuais e geradas automaticamente), baixa, contas bancárias e caixa, categorias, fluxo de caixa, lucro por veículo.
7. **Contratos:** modelos editáveis com variáveis, PDF de compra e venda, recibo e termo de garantia.
8. **Dashboard:** estoque (quantidade, valor, idade média), vendas e lucro do mês, contas a vencer, alertas de carro parado há mais de 60 ou 90 dias.
9. **Consultas inclusas:** contador mensal por plano. Acima disso, cobrança pela carteira.

**Pronto quando:** uma loja de teste cadastra um carro pela placa, lança custos, vende com troca e financiamento, emite as duas notas, faz entrada e saída no RENAVE, e o dashboard e o financeiro batem com a operação.

### Fase 2 — Profissional

1. **CRM:** leads com origem, funil em kanban, tarefas de retorno, histórico do cliente, lead → proposta.
2. **Vendedores e comissões:** regra por loja (percentual da sobra, percentual do preço ou valor fixo), metas, ranking, fechamento mensal que gera a conta a pagar.
3. **Consignação:** contrato, comissão da loja ou valor líquido garantido ao dono, repasse automático na venda.
4. **Site da loja:** vitrine pública em `<loja>.revendadigital.kaibez.com.br`, com filtros, página do carro, botão de WhatsApp e formulário que vira lead.
5. **Integrador de anúncios:** começar por um portal (OLX ou Mercado Livre, que têm API aberta com OAuth). Webmotors depende de parceria.
6. **Assinatura eletrônica** dos contratos (ZapSign ou Clicksign).

### Fase 3 — Premium

1. **Financiamento:** ficha cadastral, simulador (taxa, prazo, CET), propostas por banco com status e retorno. O envio ao banco começa manual.
2. **Multi-loja:** grupo de CNPJs, transferência de veículo entre lojas (RENAVE transferência entre filiais), visão consolidada.
3. **Relatórios avançados:** giro por modelo e faixa de preço, margem por vendedor e por origem do lead, exportação.
4. **Pós-venda e garantia:** prazos, ocorrências, custo de garantia por veículo.
5. **Avaliação no pátio pelo celular:** PWA com câmera.
6. **Conciliação bancária** por arquivo OFX.

## 4. Frontend

- Telas atuais `estoque.tsx` (RENAVE), `notas.tsx` e `comunicacao.tsx` passam a ser acionadas a partir do veículo e da venda, mantendo as telas avulsas para quem usa só o RENAVE.
- Telas novas da fase 1: Estoque (lista e ficha do veículo), Avaliação, Vendas (lista, proposta, fechamento), Pessoas, Financeiro, Contratos, Dashboard novo, Planos e Faturas.
- Recurso fora do plano aparece com cadeado e leva para a tela de planos, em vez de ficar escondido.

### Design system (grafite e verde, 2026-11-23)

Tokens em `frontend/src/styles.css`:

| Token | Cor | Uso |
|---|---|---|
| `graphite` | #18181b | menu lateral, blocos escuros |
| `brand` | #047857 | botão principal, links, seleção |
| `mint` | #34d399 | destaque sobre fundo escuro (item ativo, foco) |
| `warn` | #d97706 / #fef3c7 | avisos (fatura vencida, certificado) |
| `green` / `red` | — | resultado: lucro e prejuízo, ok e erro |
| `line` / `pale` / `muted` | tons de zinco | bordas, fundos de linha, texto secundário |

Fonte Inter, números tabulares em tabelas, títulos semibold, botões de 40 px, badges retangulares. O site institucional (`dist/`) ainda usa a identidade antiga.

## 5. Testes e qualidade

- Testes de serviço para cada fluxo que mexe com dinheiro: fechamento de venda, custos → margem, fechamento mensal da carteira, limite do plano, webhook do gateway.
- Testes de isolamento entre empresas em toda view nova (o `OrganizationScopedViewSet` já cobre o filtro).
- Provedores sempre em homologação fora da produção (Carven, Geranet, gateway).

## 6. Decisões

| Item | Decisão |
|---|---|
| Custo do RENAVE | R$ 19,90 na Carven, **já com a taxa do Serpro**. Preço de venda: **R$ 30,00** por entrada ou saída |
| Gateway de pagamento | **Asaas** (assinatura recorrente, Pix, boleto, cartão) |
| Fotos | **Cloudflare R2** via `django-storages` (API S3) |
| Domínio | **revendadigital.kaibez.com.br** |
| Site das lojas | **Subdomínio** `<loja>.revendadigital.kaibez.com.br` (DNS curinga + certificado curinga) |

## 7. Pontos em aberto

1. Fornecedor de consulta por placa: API PLACAS (R$ 0,03) ou fipeplaca (R$ 0,08). Validar a qualidade dos dados com placas reais.
2. NF-e de veículo: confirmar com a Geranet o envio do grupo `veicProd` (já listado em `docs/arquitetura.md`).
