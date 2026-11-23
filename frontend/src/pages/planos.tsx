import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, CreditCard, ExternalLink, Receipt } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, buttonClass, Card, Empty, Modal, PageHeader, Spinner, Table } from "@/components/ui";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { daysUntil, useBilling, type Invoice, type Plan, type Subscription } from "@/lib/billing";
import { date, money } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Cycle = "monthly" | "annual";

const INVOICE_TONE: Record<Invoice["status"], "green" | "yellow" | "red" | "gray"> = { paid: "green", open: "yellow", overdue: "red", canceled: "gray" };

function limitText(n: number | null, unit: string, unlimited: string) {
  return n == null ? unlimited : `Até ${n} ${unit}`;
}

function StatusLine({ sub }: { sub: Subscription }) {
  if (sub.status === "trialing") {
    const days = daysUntil(sub.trial_ends_at);
    return (
      <p>
        Teste grátis do <strong>{sub.plan.name}</strong>: {days === 0 ? "termina hoje" : `${days} dia${days > 1 ? "s" : ""} restantes`}. Depois, sua conta passa para o
        Grátis se você não assinar.
      </p>
    );
  }
  if (sub.status === "past_due") return <p className="text-red">Há uma fatura vencida. Pague para não ter os recursos suspensos.</p>;
  if (sub.status === "suspended") return <p className="text-red">Assinatura suspensa por falta de pagamento. Seus dados estão guardados; pague a fatura para voltar.</p>;
  if (sub.plan.monthly_price_cents === 0) return <p>Você está no plano Grátis: RENAVE por uso e estoque básico.</p>;
  return (
    <p>
      Plano {sub.cycle === "annual" ? "anual" : "mensal"}, pago até <strong>{date(sub.paid_through)}</strong>. Próximo fechamento em {date(sub.next_billing_date)}.
    </p>
  );
}

export function PlanosPage() {
  const { organization, can } = useAuth();
  const org = organization?.id;
  const qc = useQueryClient();
  const billing = useBilling();
  const [cycle, setCycle] = useState<Cycle>("monthly");
  const [confirm, setConfirm] = useState<Plan | null>(null);
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api<Plan[]>("/billing/plans") });
  const invoices = useQuery({ queryKey: ["invoices", org], queryFn: () => api<Page<Invoice>>("/billing/invoices") });

  const change = useMutation({
    mutationFn: (p: Plan) => api<{ invoice: Invoice | null; subscription: Subscription }>("/billing/change-plan", { body: { plan: p.code, cycle } }),
    onSuccess: (r) => {
      setConfirm(null);
      qc.invalidateQueries({ queryKey: ["billing", org] });
      qc.invalidateQueries({ queryKey: ["invoices", org] });
      qc.invalidateQueries({ queryKey: ["wallet", org] });
      if (r.invoice?.payment_url) {
        window.open(r.invoice.payment_url, "_blank", "noopener");
        toast.success("Fatura gerada. O plano é liberado assim que o pagamento for confirmado.");
      } else if (r.invoice && r.invoice.status === "paid") {
        toast.success("Plano alterado.");
      } else if (r.invoice) {
        toast.success("Fatura gerada. Nossa equipe envia as instruções de pagamento.");
      } else if (r.subscription.scheduled_plan) {
        toast.success(`A troca para o plano ${r.subscription.scheduled_plan} acontece no fim do período pago.`);
      } else {
        toast.success("Plano atualizado.");
      }
    },
    onError: (e) => handleApiError(e),
  });

  if (billing.isLoading || plans.isLoading) return <Spinner />;
  const me = billing.data;
  if (!me || !me.applies) {
    return (
      <>
        <PageHeader title="Plano" />
        <Empty title="Não foi possível carregar seu plano" icon={<CreditCard />}>
          Atualize a página. Se continuar, fale com o suporte.
        </Empty>
      </>
    );
  }
  const sub = me.subscription;
  const manage = can("billing.manage");
  const currentCode = sub.status === "trialing" ? null : sub.plan.code;

  return (
    <>
      <PageHeader title="Plano e faturas" description="Escolha o plano da sua loja. RENAVE é cobrado por operação em todos os planos." />

      <section className="mb-6 rounded-xl bg-graphite p-6 text-white">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-[#a1a1aa]">Plano atual</p>
            <p className="mt-1 font-display text-3xl font-semibold">
              {sub.plan.name} {sub.status !== "active" && <span className="align-middle text-base font-semibold text-mint">· {sub.status_display}</span>}
            </p>
          </div>
          {me.postpaid.credit_limit_cents > 0 && (
            <div className="text-right">
              <p className="text-sm text-[#a1a1aa]">Consumo a faturar</p>
              <p className="font-display text-2xl font-semibold">{money(me.postpaid.owed_cents)}</p>
              <p className="text-xs text-[#a1a1aa]">limite de {money(me.postpaid.credit_limit_cents)} por mês</p>
            </div>
          )}
        </div>
        <div className="mt-3 text-sm text-[#d4d4d8]">
          <StatusLine sub={sub} />
          {sub.scheduled_plan && (
            <p className="mt-1">
              Troca agendada para o plano <strong>{plans.data?.find((p) => p.code === sub.scheduled_plan)?.name}</strong> em {date(sub.paid_through)}.
            </p>
          )}
        </div>
        {me.open_invoice && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl bg-white/10 p-3 text-sm">
            <span>
              Fatura {me.open_invoice.status === "overdue" ? "vencida" : "em aberto"}: <strong>{money(me.open_invoice.total_cents)}</strong>, vence em {date(me.open_invoice.due_date)}
            </span>
            {me.open_invoice.payment_url && (
              <a href={me.open_invoice.payment_url} target="_blank" rel="noopener noreferrer" className={buttonClass("mint", "sm", "ml-auto")}>
                Pagar agora <ExternalLink className="size-4" />
              </a>
            )}
          </div>
        )}
      </section>

      <div className="mb-4 flex justify-center">
        <div className="inline-flex rounded-full border border-line bg-white p-1 text-sm font-semibold" role="radiogroup" aria-label="Ciclo de cobrança">
          {(["monthly", "annual"] as Cycle[]).map((c) => (
            <button
              key={c}
              role="radio"
              aria-checked={cycle === c}
              onClick={() => setCycle(c)}
              className={clsx("rounded-full px-4 py-1.5", cycle === c ? "bg-graphite text-white" : "text-muted hover:text-ink")}
            >
              {c === "monthly" ? "Mensal" : "Anual · 2 meses grátis"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {plans.data?.map((p) => {
          const price = cycle === "annual" ? p.annual_price_cents : p.monthly_price_cents;
          const isCurrent = currentCode === p.code && (p.monthly_price_cents === 0 || sub.cycle === cycle);
          const highlight = p.code === "profissional";
          return (
            <article key={p.code} className={clsx("flex flex-col rounded-xl border bg-white p-5", highlight ? "border-brand shadow-lg" : "border-line")}>
              <div className="flex items-center justify-between">
                <h2 className="font-display text-xl font-semibold">{p.name}</h2>
                {highlight && <Badge tone="blue">Mais escolhido</Badge>}
                {isCurrent && <Badge tone="green">Atual</Badge>}
              </div>
              <p className="mt-3">
                <span className="font-display text-3xl font-semibold">{price === 0 ? "R$ 0" : money(price)}</span>
                {price > 0 && <span className="text-sm text-muted">/{cycle === "annual" ? "ano" : "mês"}</span>}
              </p>
              {cycle === "annual" && price > 0 && <p className="text-xs text-muted">equivale a {money(Math.round(price / 12))}/mês</p>}
              <ul className="mt-4 flex-1 space-y-2 text-sm">
                <li className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-green" />
                  {limitText(p.vehicle_limit, "veículos em estoque", "Estoque ilimitado")}
                </li>
                <li className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-green" />
                  {limitText(p.user_limit, p.user_limit === 1 ? "usuário" : "usuários", "Usuários ilimitados")}
                </li>
                <li className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-green" />
                  {p.plate_queries_included} consultas de placa por mês
                </li>
                {p.feature_labels.filter((f) => f !== "RENAVE").map((f) => (
                  <li key={f} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-green" />
                    {f === "Nota fiscal" ? "Nota fiscal ilimitada" : f}
                  </li>
                ))}
                <li className="flex gap-2 text-muted">
                  <Check className="mt-0.5 size-4 shrink-0 text-green" />
                  RENAVE {p.postpaid ? "na fatura do mês" : "pré-pago na carteira"}
                </li>
              </ul>
              {manage && (
                <Button className="mt-5 w-full" variant={highlight ? "primary" : "secondary"} disabled={isCurrent} onClick={() => setConfirm(p)}>
                  {isCurrent ? "Seu plano" : p.monthly_price_cents === 0 ? "Usar o Grátis" : "Escolher"}
                </Button>
              )}
            </article>
          );
        })}
      </div>
      {!manage && <p className="mt-3 text-center text-sm text-muted">Só o proprietário, administradores e o financeiro podem trocar de plano.</p>}

      <Card title="Faturas" className="mt-8">
        {invoices.isLoading ? (
          <Spinner />
        ) : !invoices.data?.results.length ? (
          <Empty title="Nenhuma fatura ainda" icon={<Receipt />} />
        ) : (
          <Table head={["Emitida", "Descrição", "Vencimento", "Valor", "Situação", ""]}>
            {invoices.data.results.map((inv) => (
              <tr key={inv.id}>
                <td className="px-5 py-3 whitespace-nowrap text-muted">{date(inv.created_at)}</td>
                <td className="px-5 py-3">
                  {inv.items.map((i) => (
                    <span key={i.description} className="block">
                      {i.description} <span className="text-muted">({money(i.total_cents)})</span>
                    </span>
                  ))}
                </td>
                <td className="px-5 py-3 whitespace-nowrap">{date(inv.due_date)}</td>
                <td className="px-5 py-3 font-semibold whitespace-nowrap">{money(inv.total_cents)}</td>
                <td className="px-5 py-3">
                  <Badge tone={INVOICE_TONE[inv.status]}>{inv.status_display}</Badge>
                </td>
                <td className="px-5 py-3 text-right">
                  {inv.payment_url && (inv.status === "open" || inv.status === "overdue") && (
                    <a href={inv.payment_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-brand">
                      Pagar
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Modal open={!!confirm} onOpenChange={(v) => !v && setConfirm(null)} title={confirm ? `Plano ${confirm.name}` : ""}>
        {confirm && <ConfirmBody plan={confirm} cycle={cycle} sub={sub} />}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirm(null)}>
            Voltar
          </Button>
          <Button onClick={() => confirm && change.mutate(confirm)} loading={change.isPending}>
            Confirmar
          </Button>
        </div>
      </Modal>
    </>
  );
}

function ConfirmBody({ plan, cycle, sub }: { plan: Plan; cycle: Cycle; sub: Subscription }) {
  const paidPeriod = (sub.status === "active" || sub.status === "past_due") && sub.plan.monthly_price_cents > 0;
  const downgrade = paidPeriod && (plan.monthly_price_cents < sub.plan.monthly_price_cents || (plan.code === sub.plan.code && cycle === "monthly"));
  const price = cycle === "annual" ? plan.annual_price_cents : plan.monthly_price_cents;
  if (plan.monthly_price_cents === 0 || downgrade) {
    return paidPeriod ? (
      <p className="text-sm text-muted">
        A troca acontece em {date(sub.paid_through)}, no fim do período já pago. Até lá, você continua com o plano {sub.plan.name}. Recursos fora do novo plano
        ficam bloqueados, mas seus dados continuam guardados.
      </p>
    ) : (
      <p className="text-sm text-muted">Sua conta passa para o plano {plan.name} agora. Recursos fora dele ficam bloqueados, mas seus dados continuam guardados.</p>
    );
  }
  return (
    <div className="space-y-2 text-sm text-muted">
      <p>
        Vamos gerar uma fatura de <strong className="text-ink">{money(price)}</strong> ({cycle === "annual" ? "anual" : "mensal"}). Você paga por Pix, boleto ou cartão, e o plano
        é liberado assim que o pagamento for confirmado.
      </p>
      {paidPeriod && <p>O valor dos dias não usados do plano atual é descontado na fatura.</p>}
      <p>As operações RENAVE do mês entram na fatura seguinte, até o limite do plano.</p>
    </div>
  );
}
