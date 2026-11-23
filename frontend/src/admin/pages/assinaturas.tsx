import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Gift, Timer, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner } from "@/components/ui";
import { date, dateTime, maskMoney, money, parseMoney } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { adminApi } from "../api";
import { OrgCell, ResourceTable } from "../components";
import { ask } from "@/components/confirm";

const SUB_TONE: Record<string, "blue" | "green" | "yellow" | "red"> = { trialing: "blue", active: "green", past_due: "yellow", suspended: "red" };
const INV_TONE: Record<string, "yellow" | "green" | "gray" | "red"> = { open: "yellow", paid: "green", overdue: "red", canceled: "gray" };
const PLAN_OPTIONS: [string, string][] = [
  ["gratis", "Grátis"],
  ["essencial", "Essencial"],
  ["profissional", "Profissional"],
  ["premium", "Premium"],
];

type Sub = {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_cnpj: string;
  plan: { code: string; name: string };
  status: string;
  status_display: string;
  cycle: string;
  trial_ends_at: string | null;
  paid_through: string | null;
  next_billing_date: string | null;
  scheduled_plan: string | null;
};

const orgOf = (r: { organization_id: string; organization_name: string; organization_cnpj: string }) => ({
  id: r.organization_id,
  name: r.organization_name,
  cnpj: r.organization_cnpj,
});

export function AssinaturasPage() {
  const qc = useQueryClient();
  const [trialFor, setTrialFor] = useState<Sub | null>(null);
  const [grantFor, setGrantFor] = useState<Sub | null>(null);
  const [days, setDays] = useState("7");
  const [grant, setGrant] = useState({ plan: "profissional", cycle: "monthly", reason: "" });
  const done = (msg: string) => {
    toast.success(msg);
    setTrialFor(null);
    setGrantFor(null);
    qc.invalidateQueries({ queryKey: ["admin"] });
  };
  const extend = useMutation({
    mutationFn: () => adminApi(`/subscriptions/${trialFor!.id}/extend-trial`, { method: "POST", body: { days: Number(days) } }),
    onSuccess: () => done("Teste estendido."),
    onError: (e) => handleApiError(e),
  });
  const grantPlan = useMutation({
    mutationFn: () => adminApi(`/subscriptions/${grantFor!.id}/grant-plan`, { method: "POST", body: grant }),
    onSuccess: () => done("Plano concedido."),
    onError: (e) => handleApiError(e),
  });

  return (
    <>
      <PageHeader title="Assinaturas" description="Plano de cada loja do Revenda Digital. Estenda testes ou conceda planos de cortesia." />
      <ResourceTable<Sub>
        endpoint="/subscriptions"
        searchPlaceholder="Empresa ou CNPJ"
        filters={[
          {
            name: "status",
            label: "Situação",
            options: [
              ["", "Todas"],
              ["trialing", "Em teste"],
              ["active", "Ativas"],
              ["past_due", "Em atraso"],
              ["suspended", "Suspensas"],
            ],
          },
          { name: "plan", label: "Plano", options: [["", "Todos"], ...PLAN_OPTIONS] },
        ]}
        columns={[
          { header: "Empresa", cell: (s) => <OrgCell org={orgOf(s)} /> },
          {
            header: "Plano",
            cell: (s) => (
              <>
                <strong>{s.plan.name}</strong> <span className="text-xs text-muted">{s.cycle === "annual" ? "anual" : "mensal"}</span>
                {s.scheduled_plan && <span className="block text-xs text-muted">→ {s.scheduled_plan} no fim do período</span>}
              </>
            ),
          },
          { header: "Situação", cell: (s) => <Badge tone={SUB_TONE[s.status]}>{s.status_display}</Badge> },
          {
            header: "Datas",
            cell: (s) =>
              s.status === "trialing" ? (
                <span className="text-sm">Teste até {dateTime(s.trial_ends_at)}</span>
              ) : (
                <span className="text-sm">
                  Pago até {date(s.paid_through)}
                  <span className="block text-xs text-muted">Fechamento {date(s.next_billing_date)}</span>
                </span>
              ),
          },
          {
            header: "",
            cell: (s) => (
              <div className="flex justify-end gap-1">
                <Button size="sm" variant="secondary" onClick={() => setTrialFor(s)}>
                  <Timer className="size-4" /> Teste
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setGrantFor(s)}>
                  <Gift className="size-4" /> Conceder
                </Button>
              </div>
            ),
          },
        ]}
      />

      <Modal open={!!trialFor} onOpenChange={(v) => !v && setTrialFor(null)} title="Estender teste" description={trialFor?.organization_name}>
        <Field label="Dias a mais" htmlFor="days" hint="Entre 1 e 90. Quem está no Grátis volta para o teste do Profissional.">
          <Input id="days" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} />
        </Field>
        <Button className="mt-4 w-full" onClick={() => extend.mutate()} loading={extend.isPending}>
          Estender
        </Button>
      </Modal>

      <Modal open={!!grantFor} onOpenChange={(v) => !v && setGrantFor(null)} title="Conceder plano sem cobrança" description={grantFor?.organization_name}>
        <div className="space-y-4">
          <Field label="Plano" htmlFor="g-plan">
            <Select id="g-plan" value={grant.plan} onChange={(e) => setGrant({ ...grant, plan: e.target.value })}>
              {PLAN_OPTIONS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Período" htmlFor="g-cycle">
            <Select id="g-cycle" value={grant.cycle} onChange={(e) => setGrant({ ...grant, cycle: e.target.value })}>
              <option value="monthly">1 mês</option>
              <option value="annual">12 meses</option>
            </Select>
          </Field>
          <Field label="Motivo" htmlFor="g-reason" hint="Fica registrado na auditoria.">
            <Input id="g-reason" value={grant.reason} onChange={(e) => setGrant({ ...grant, reason: e.target.value })} placeholder="Ex.: cortesia de lançamento" />
          </Field>
          <Button className="w-full" onClick={() => grantPlan.mutate()} loading={grantPlan.isPending}>
            Conceder
          </Button>
        </div>
      </Modal>
    </>
  );
}

export function FaturasAdminPage() {
  const qc = useQueryClient();
  const act = useMutation({
    mutationFn: ({ id, path }: { id: string; path: "mark-paid" | "cancel" }) => adminApi(`/invoices/${id}/${path}`, { method: "POST" }),
    onSuccess: (_, v) => {
      toast.success(v.path === "mark-paid" ? "Fatura marcada como paga." : "Fatura cancelada.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <PageHeader title="Faturas" description="Mensalidades e consumo pós-pago. Pagamentos pelo Asaas são confirmados automaticamente." />
      <ResourceTable<any>
        endpoint="/invoices"
        searchPlaceholder="Empresa, CNPJ ou id da cobrança"
        filters={[
          {
            name: "status",
            label: "Situação",
            options: [
              ["", "Todas"],
              ["open", "Em aberto"],
              ["overdue", "Vencidas"],
              ["paid", "Pagas"],
              ["canceled", "Canceladas"],
            ],
          },
        ]}
        columns={[
          { header: "Emitida", cell: (i) => date(i.created_at), className: "whitespace-nowrap" },
          { header: "Empresa", cell: (i) => <OrgCell org={orgOf(i)} /> },
          {
            header: "Itens",
            cell: (i) => (
              <>
                {i.items.map((it: { description: string; total_cents: number }) => (
                  <span key={it.description} className="block text-sm">
                    {it.description} <span className="text-muted">({money(it.total_cents)})</span>
                  </span>
                ))}
              </>
            ),
          },
          { header: "Vence", cell: (i) => date(i.due_date), className: "whitespace-nowrap" },
          { header: "Valor", cell: (i) => <strong>{money(i.total_cents)}</strong>, className: "text-right whitespace-nowrap" },
          { header: "Situação", cell: (i) => <Badge tone={INV_TONE[i.status]}>{i.status_display}</Badge> },
          {
            header: "",
            cell: (i) =>
              (i.status === "open" || i.status === "overdue") && (
                <div className="flex justify-end gap-1">
                  <Button size="sm" onClick={() => void ask(`Confirmar o recebimento de ${money(i.total_cents)} de ${i.organization_name}?`).then((ok) => ok && act.mutate({ id: i.id, path: "mark-paid" }))}>
                    <Check className="size-4" /> Paga
                  </Button>
                  <Button size="sm" variant="ghost" aria-label="Cancelar fatura" onClick={() => void ask("Cancelar esta fatura?").then((ok) => ok && act.mutate({ id: i.id, path: "cancel" }))}>
                    <X className="size-4 text-red" />
                  </Button>
                </div>
              ),
          },
        ]}
      />
    </>
  );
}

type PlanRow = {
  code: string;
  name: string;
  monthly_price_cents: number;
  annual_price_cents: number;
  vehicle_limit: number | null;
  user_limit: number | null;
  plate_queries_included: number;
  credit_limit_cents: number;
  extra_store_price_cents: number;
};

const MONEY_FIELDS = ["monthly_price_cents", "annual_price_cents", "credit_limit_cents", "extra_store_price_cents"] as const;
const NUM_FIELDS = ["vehicle_limit", "user_limit", "plate_queries_included"] as const;
const LABELS: Record<string, string> = {
  monthly_price_cents: "Mensal (R$)",
  annual_price_cents: "Anual (R$)",
  credit_limit_cents: "Limite pós-pago (R$)",
  extra_store_price_cents: "Loja extra (R$)",
  vehicle_limit: "Veículos (vazio = ilimitado)",
  user_limit: "Usuários (vazio = ilimitado)",
  plate_queries_included: "Consultas de placa/mês",
};

function PlanEditor({ plan }: { plan: PlanRow }) {
  const qc = useQueryClient();
  const initial = () => ({
    ...Object.fromEntries(MONEY_FIELDS.map((f) => [f, maskMoney(String(plan[f]))])),
    ...Object.fromEntries(NUM_FIELDS.map((f) => [f, plan[f] == null ? "" : String(plan[f])])),
  });
  const [form, setForm] = useState<Record<string, string>>(initial);
  const save = useMutation({
    mutationFn: () =>
      adminApi(`/plans/${plan.code}`, {
        method: "PATCH",
        body: {
          ...Object.fromEntries(MONEY_FIELDS.map((f) => [f, parseMoney(form[f])])),
          ...Object.fromEntries(NUM_FIELDS.map((f) => [f, form[f] === "" ? (f === "plate_queries_included" ? 0 : null) : Number(form[f])])),
        },
      }),
    onSuccess: () => {
      toast.success(`Plano ${plan.name} atualizado.`);
      qc.invalidateQueries({ queryKey: ["admin", "plans"] });
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <Card title={plan.name} action={<Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>Salvar</Button>}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[...MONEY_FIELDS, ...NUM_FIELDS].map((f) => (
          <Field key={f} label={LABELS[f]} htmlFor={`${plan.code}-${f}`}>
            <Input
              id={`${plan.code}-${f}`}
              inputMode="decimal"
              value={form[f]}
              onChange={(e) => setForm({ ...form, [f]: (MONEY_FIELDS as readonly string[]).includes(f) ? maskMoney(e.target.value) : e.target.value.replace(/\D/g, "") })}
            />
          </Field>
        ))}
      </div>
    </Card>
  );
}

export function PlanosAdminPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "plans"], queryFn: () => adminApi<PlanRow[]>("/plans") });
  return (
    <>
      <PageHeader title="Planos" description="Preços e limites dos planos do Revenda Digital. Mudanças valem para as próximas faturas." />
      {isLoading ? <Spinner /> : <div className="space-y-4">{data?.map((p) => <PlanEditor key={p.code} plan={p} />)}</div>}
    </>
  );
}
