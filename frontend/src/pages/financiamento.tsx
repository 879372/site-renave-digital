import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, Landmark, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Money, MoneyInput, Pager, PessoaPicker, Tabs, useTab, type Paged } from "@/components/kit";
import { PlanGate } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, money } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

type Proposta = { id: string; bank: string; status: string; status_display: string; monthly_rate_bp: number; term_months: number; financed_cents: number; installment_cents: number; cet_annual_bp: number; dealer_return_cents: number; notes: string; updated_at: string };
type Ficha = { id: string; cliente: string; cliente_name: string; vehicle_title: string | null; occupation: string; monthly_income_cents: number; employer: string; vehicle_price_cents: number; down_payment_cents: number; term_months: number; financed_cents: number; propostas: Proposta[]; best_status: string | null; created_at: string };

const TONE: Record<string, "yellow" | "blue" | "green" | "red" | "gray"> = { enviada: "yellow", analise: "blue", aprovada: "green", paga: "green", recusada: "red", cancelada: "gray" };
const pct = (bp: number) => `${(bp / 100).toFixed(2).replace(".", ",")}%`;

export function FinanciamentoPage() {
  const [tab, setTab] = useTab("fichas");
  return (
    <>
      <PageHeader title="Financiamento" description="Ficha do cliente, simulação e acompanhamento das propostas nos bancos." />
      <PlanGate feature="financiamento" title="Financiamento">
        <Tabs tabs={[["fichas", "Fichas e propostas"], ["simulador", "Simulador"]]} value={tab} onChange={setTab} />
        {tab === "fichas" ? <Fichas /> : <Simulador />}
      </PlanGate>
    </>
  );
}

function Simulador() {
  const [f, setF] = useState({ price_cents: 6000000, down_cents: 2000000, monthly_rate_bp: 199, fees_cents: 0, iof_pct_bp: 0 });
  const m = useMutation({ mutationFn: () => api<any[]>("/financiamento/simular", { body: { ...f, months: 48, terms: [12, 24, 36, 48, 60] } }), onError: (e) => handleApiError(e) });
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Card title="Dados">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Valor do carro"><MoneyInput value={f.price_cents} onChange={(c) => setF({ ...f, price_cents: c })} /></Field>
          <Field label="Entrada"><MoneyInput value={f.down_cents} onChange={(c) => setF({ ...f, down_cents: c })} /></Field>
          <Field label="Taxa ao mês (%)" htmlFor="s-r"><Input placeholder="1,99" id="s-r" inputMode="decimal" value={(f.monthly_rate_bp / 100).toString().replace(".", ",")} onChange={(e) => setF({ ...f, monthly_rate_bp: Math.round(Number(e.target.value.replace(",", ".") || 0) * 100) })} /></Field>
          <Field label="Tarifas (cadastro, registro)"><MoneyInput value={f.fees_cents} onChange={(c) => setF({ ...f, fees_cents: c })} /></Field>
          <Field label="IOF (%)" htmlFor="s-i"><Input placeholder="0,38" id="s-i" inputMode="decimal" value={(f.iof_pct_bp / 100).toString().replace(".", ",")} onChange={(e) => setF({ ...f, iof_pct_bp: Math.round(Number(e.target.value.replace(",", ".") || 0) * 100) })} /></Field>
          <Button type="submit" className="w-full" loading={m.isPending}><Calculator className="size-4" /> Simular</Button>
        </form>
      </Card>
      <Card title="Parcelas" description="Tabela Price. O CET inclui tarifas e IOF.">
        {!m.data ? <p className="text-sm text-muted">Preencha e clique em simular.</p> : (
          <Table head={["Prazo", "Parcela", "Total pago", "Juros", "CET a.m.", "CET a.a."]}>
            {m.data.map((s) => (
              <tr key={s.months}>
                <td className="px-5 py-3 font-medium">{s.months}x</td>
                <td className="px-5 py-3 font-semibold"><Money cents={s.installment_cents} /></td>
                <td className="px-5 py-3"><Money cents={s.total_cents} /></td>
                <td className="px-5 py-3 text-muted"><Money cents={s.interest_cents} /></td>
                <td className="px-5 py-3">{pct(s.cet_monthly_bp)}</td>
                <td className="px-5 py-3">{pct(s.cet_annual_bp)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function Fichas() {
  const { organization, can } = useAuth();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<Ficha | null>(null);
  const q = useQuery({ queryKey: ["fichas", organization?.id, page], queryFn: () => api<Paged<Ficha>>("/financiamento/fichas", { params: { page } }) });
  return (
    <Card title="Fichas" action={can("vendas.operate") && <Button size="sm" onClick={() => setCreating(true)}><Plus className="size-4" /> Nova ficha</Button>}>
      {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhuma ficha" icon={<Landmark />} /> : (
        <>
          <Table head={["Data", "Cliente", "Veículo", "Financiado", "Propostas", "Melhor situação"]}>
            {q.data.results.map((f) => (
              <tr key={f.id} className="cursor-pointer hover:bg-pale/60" onClick={() => setOpen(f)}>
                <td className="px-5 py-3 text-muted">{date(f.created_at)}</td>
                <td className="px-5 py-3 font-medium">{f.cliente_name}</td>
                <td className="px-5 py-3">{f.vehicle_title ?? "—"}</td>
                <td className="px-5 py-3"><Money cents={f.financed_cents} /></td>
                <td className="px-5 py-3 tabular">{f.propostas.length}</td>
                <td className="px-5 py-3">{f.best_status ? <Badge tone={TONE[f.best_status]}>{f.propostas.find((p) => p.status === f.best_status)?.status_display}</Badge> : "—"}</td>
              </tr>
            ))}
          </Table>
          <Pager page={page} data={q.data} onPage={setPage} />
        </>
      )}
      <FichaForm open={creating} onOpenChange={setCreating} />
      <FichaDetail ficha={open} onClose={() => setOpen(null)} />
    </Card>
  );
}

function FichaForm({ open, onOpenChange }: { open: boolean; onOpenChange: (b: boolean) => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ cliente: null as any, occupation: "clt", employer: "", job_title: "", monthly_income_cents: 0, mother_name: "", reference_name: "", reference_phone: "", vehicle_price_cents: 0, down_payment_cents: 0, term_months: 48 });
  const m = useMutation({
    mutationFn: () => api("/financiamento/fichas", { body: { ...f, cliente: f.cliente?.id } }),
    onSuccess: () => { toast.success("Ficha criada"); qc.invalidateQueries({ queryKey: ["fichas"] }); onOpenChange(false); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Ficha de financiamento" wide>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <PessoaPicker value={f.cliente} onChange={(p) => setF({ ...f, cliente: p })} required />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Nome da mãe" htmlFor="fi-m"><Input placeholder="Nome completo da mãe" id="fi-m" value={f.mother_name} onChange={(e) => setF({ ...f, mother_name: e.target.value })} /></Field>
          <Field label="Ocupação" htmlFor="fi-o"><Select id="fi-o" value={f.occupation} onChange={(e) => setF({ ...f, occupation: e.target.value })}><option value="clt">Assalariado (CLT)</option><option value="autonomo">Autônomo</option><option value="empresario">Empresário</option><option value="aposentado">Aposentado</option><option value="servidor">Servidor público</option><option value="outro">Outro</option></Select></Field>
          <Field label="Renda mensal"><MoneyInput value={f.monthly_income_cents} onChange={(c) => setF({ ...f, monthly_income_cents: c })} /></Field>
          <Field label="Empresa" htmlFor="fi-e"><Input placeholder="Empresa onde trabalha" id="fi-e" value={f.employer} onChange={(e) => setF({ ...f, employer: e.target.value })} /></Field>
          <Field label="Cargo" htmlFor="fi-c"><Input placeholder="Vendedor, motorista, gerente…" id="fi-c" value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></Field>
          <Field label="Referência (nome e telefone)" htmlFor="fi-r"><Input placeholder="João Souza (84) 99999-9999" id="fi-r" value={f.reference_name} onChange={(e) => setF({ ...f, reference_name: e.target.value })} /></Field>
          <Field label="Valor do carro"><MoneyInput value={f.vehicle_price_cents} onChange={(c) => setF({ ...f, vehicle_price_cents: c })} /></Field>
          <Field label="Entrada"><MoneyInput value={f.down_payment_cents} onChange={(c) => setF({ ...f, down_payment_cents: c })} /></Field>
          <Field label="Prazo (meses)" htmlFor="fi-t"><Input placeholder="48" id="fi-t" inputMode="numeric" value={f.term_months} onChange={(e) => setF({ ...f, term_months: Number(e.target.value.replace(/\D/g, "") || 48) })} /></Field>
        </div>
        <p className="text-xs text-muted">Dados pessoais do cliente: use só para a análise de crédito e não compartilhe fora dos bancos parceiros.</p>
        <Button type="submit" disabled={!f.cliente} loading={m.isPending}>Salvar ficha</Button>
      </form>
    </Modal>
  );
}

function FichaDetail({ ficha, onClose }: { ficha: Ficha | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [p, setP] = useState({ bank: "", monthly_rate_bp: 0, term_months: 48, installment_cents: 0, dealer_return_cents: 0 });
  const add = useMutation({
    mutationFn: () => api(`/financiamento/fichas/${ficha!.id}/propostas`, { body: { ...p, financed_cents: ficha!.financed_cents } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["fichas"] }); onClose(); toast.success("Proposta registrada"); },
    onError: (e) => handleApiError(e),
  });
  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/financiamento/fichas/${ficha!.id}/propostas/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["fichas"] }); onClose(); toast.success("Situação atualizada"); },
    onError: (e) => handleApiError(e),
  });
  if (!ficha) return null;
  return (
    <Modal open={!!ficha} onOpenChange={(v) => !v && onClose()} title={ficha.cliente_name} description={`Financiado: ${money(ficha.financed_cents)} · renda ${money(ficha.monthly_income_cents)}`} wide>
      <div className="space-y-5">
        {ficha.propostas.length > 0 && (
          <Table head={["Banco", "Taxa", "Prazo", "Parcela", "Retorno", "Situação"]}>
            {ficha.propostas.map((x) => (
              <tr key={x.id}>
                <td className="px-5 py-2 font-medium">{x.bank}</td>
                <td className="px-5 py-2">{pct(x.monthly_rate_bp)} a.m.</td>
                <td className="px-5 py-2">{x.term_months}x</td>
                <td className="px-5 py-2"><Money cents={x.installment_cents || null} /></td>
                <td className="px-5 py-2"><Money cents={x.dealer_return_cents || null} /></td>
                <td className="px-5 py-2"><Select value={x.status} onChange={(e) => update.mutate({ id: x.id, status: e.target.value })} className="h-8 w-36"><option value="enviada">Enviada</option><option value="analise">Em análise</option><option value="aprovada">Aprovada</option><option value="recusada">Recusada</option><option value="paga">Paga à loja</option><option value="cancelada">Cancelada</option></Select></td>
              </tr>
            ))}
          </Table>
        )}
        <form className="grid items-end gap-3 rounded-lg border border-line p-3 sm:grid-cols-6" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Banco" className="sm:col-span-2"><Input placeholder="Banco Pan, BV, Santander…" required value={p.bank} onChange={(e) => setP({ ...p, bank: e.target.value })} /></Field>
          <Field label="Taxa a.m. (%)"><Input placeholder="1,99" inputMode="decimal" value={(p.monthly_rate_bp / 100).toString().replace(".", ",")} onChange={(e) => setP({ ...p, monthly_rate_bp: Math.round(Number(e.target.value.replace(",", ".") || 0) * 100) })} /></Field>
          <Field label="Prazo"><Input placeholder="48" inputMode="numeric" value={p.term_months} onChange={(e) => setP({ ...p, term_months: Number(e.target.value.replace(/\D/g, "") || 48) })} /></Field>
          <Field label="Parcela"><MoneyInput value={p.installment_cents} onChange={(c) => setP({ ...p, installment_cents: c })} /></Field>
          <Field label="Retorno"><MoneyInput value={p.dealer_return_cents} onChange={(c) => setP({ ...p, dealer_return_cents: c })} /></Field>
          <Button type="submit" className="sm:col-span-6" variant="secondary" loading={add.isPending}>Registrar proposta enviada</Button>
        </form>
        <p className="text-xs text-muted">Quando a proposta fica “Paga à loja”, o retorno da financeira entra em contas a receber.</p>
      </div>
    </Modal>
  );
}
