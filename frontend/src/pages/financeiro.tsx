import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDownLeft, ArrowUpRight, Check, Plus, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { Money, MoneyInput, Pager, PessoaPicker, SearchInput, Tabs, useDebounced, useTab, type Paged } from "@/components/kit";
import { LockedPanel, PlanGate } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { date, money } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { ask } from "@/components/confirm";

type Lanc = {
  id: string;
  kind: "receber" | "pagar";
  origin_display: string;
  description: string;
  categoria: string | null;
  categoria_name: string | null;
  pessoa_name: string | null;
  vehicle_id: string | null;
  vehicle_title: string | null;
  amount_cents: number;
  due_date: string;
  paid_at: string | null;
  paid_cents: number | null;
  conta_name: string | null;
  status: "aberto" | "vencido" | "pago" | "cancelado";
};
type Conta = { id: string; name: string; kind: string; balance_cents: number; is_active: boolean };
type Categoria = { id: string; name: string; kind: string; is_system: boolean };

const STATUS_TONE = { aberto: "yellow", vencido: "red", pago: "green", cancelado: "gray" } as const;

export function FinanceiroPage() {
  const [tab, setTab] = useTab("resumo");
  const { has } = useBilling();
  return (
    <>
      <PageHeader title="Financeiro" description="Contas a pagar e a receber, caixa e resultado da loja." />
      <PlanGate feature="financeiro" title="Financeiro">
        <Tabs tabs={[["resumo", "Resumo"], ["receber", "A receber"], ["pagar", "A pagar"], ["dre", "Resultado (DRE)"], ["contas", "Contas e categorias"], ["conciliacao", "Conciliação"]]} value={tab} onChange={setTab} />
        {tab === "resumo" && <Resumo />}
        {tab === "receber" && <Lancamentos kind="receber" />}
        {tab === "pagar" && <Lancamentos kind="pagar" />}
        {tab === "dre" && <Dre />}
        {tab === "contas" && <ContasCategorias />}
        {tab === "conciliacao" && (has("conciliacao") ? <Conciliacao /> : <LockedPanel feature="conciliacao" title="Conciliação bancária" />)}
      </PlanGate>
    </>
  );
}

function Resumo() {
  const { organization } = useAuth();
  const r = useQuery({ queryKey: ["fin-resumo", organization?.id], queryFn: () => api<any>("/financeiro/resumo") });
  const fluxo = useQuery({ queryKey: ["fin-fluxo", organization?.id], queryFn: () => api<any[]>("/financeiro/fluxo") });
  const contas = useQuery({ queryKey: ["fin-contas", organization?.id], queryFn: () => api<Conta[]>("/financeiro/contas") });
  if (r.isLoading) return <Spinner />;
  const d = r.data;
  const chart = (fluxo.data ?? []).map((x) => ({ dia: x.date.slice(8, 10) + "/" + x.date.slice(5, 7), Entradas: (x.in_paid + x.in_open) / 100, Saidas: (x.out_paid + x.out_open) / 100 }));
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Saldo em caixa e bancos" value={money(d.saldo_cents)} />
        <Stat label="A receber (em aberto)" value={money(d.receber_aberto_cents)} hint={d.receber_vencido_cents ? <span className="text-red">{money(d.receber_vencido_cents)} vencidos</span> : `${money(d.receber_7d_cents)} nos próximos 7 dias`} />
        <Stat label="A pagar (em aberto)" value={money(d.pagar_aberto_cents)} hint={d.pagar_vencido_cents ? <span className="text-red">{money(d.pagar_vencido_cents)} vencidos</span> : `${money(d.pagar_7d_cents)} nos próximos 7 dias`} />
        <Stat label="Saldo previsto" value={money(d.saldo_cents + d.receber_aberto_cents - d.pagar_aberto_cents)} />
      </div>
      <Card title="Fluxo de caixa" description="15 dias para trás e 30 para frente (pago + previsto).">
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
              <XAxis dataKey="dia" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: number) => money(Math.round(v * 100))} />
              <Bar dataKey="Entradas" fill="#047857" radius={[3, 3, 0, 0]} />
              <Bar dataKey="Saidas" name="Saídas" fill="#a1a1aa" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Contas">
        <ul className="divide-y divide-line text-sm">{contas.data?.map((c) => <li key={c.id} className="flex justify-between py-2"><span>{c.name}</span><Money cents={c.balance_cents} className={c.balance_cents < 0 ? "text-red" : ""} /></li>)}</ul>
      </Card>
    </div>
  );
}

function Lancamentos({ kind }: { kind: "receber" | "pagar" }) {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState("pendente");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [paying, setPaying] = useState<Lanc | null>(null);
  const search = useDebounced(term);
  const q = useQuery({ queryKey: ["lancamentos", organization?.id, kind, status, search, page], queryFn: () => api<Paged<Lanc>>("/financeiro/lancamentos", { params: { kind, status, search, page } }) });
  const act = useMutation({
    mutationFn: ({ id, path }: { id: string; path: string }) => api(`/financeiro/lancamentos/${id}/${path}`, { body: {} }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["lancamentos"] }); qc.invalidateQueries({ queryKey: ["fin-resumo"] }); },
    onError: (e) => handleApiError(e),
  });
  const manage = can("financeiro.manage");
  return (
    <Card
      title={kind === "receber" ? "Contas a receber" : "Contas a pagar"}
      action={
        <div className="flex flex-wrap gap-2">
          <SearchInput value={term} onChange={(v) => { setTerm(v); setPage(1); }} placeholder="Descrição ou pessoa" />
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-9 w-36"><option value="pendente">Pendentes</option><option value="vencido">Vencidos</option><option value="pago">Pagos</option><option value="cancelado">Cancelados</option><option value="">Todos</option></Select>
          {manage && <Button size="sm" onClick={() => setCreating(true)}><Plus className="size-4" /> Lançar</Button>}
        </div>
      }
    >
      {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nada por aqui" /> : (
        <>
          <Table head={["Vencimento", "Descrição", "Categoria", "Valor", "Situação", ""]}>
            {q.data.results.map((l) => (
              <tr key={l.id}>
                <td className={clsx("px-5 py-3 whitespace-nowrap", l.status === "vencido" && "text-red")}>{date(l.due_date)}</td>
                <td className="px-5 py-3"><p>{l.description}</p><p className="text-xs text-muted">{[l.pessoa_name, l.origin_display].filter(Boolean).join(" · ")}</p></td>
                <td className="px-5 py-3 text-muted">{l.categoria_name ?? "—"}</td>
                <td className="px-5 py-3 font-medium">{kind === "receber" ? <ArrowDownLeft className="mr-1 inline size-3.5 text-green" /> : <ArrowUpRight className="mr-1 inline size-3.5 text-muted" />}<Money cents={l.paid_cents ?? l.amount_cents} /></td>
                <td className="px-5 py-3"><Badge tone={STATUS_TONE[l.status]}>{l.status}</Badge>{l.paid_at && <span className="block text-xs text-muted">{date(l.paid_at)} · {l.conta_name}</span>}</td>
                <td className="px-5 py-3 text-right whitespace-nowrap">
                  {manage && (l.status === "aberto" || l.status === "vencido") && (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => setPaying(l)}><Check className="size-4" /> {kind === "receber" ? "Receber" : "Pagar"}</Button>
                      <button className="ml-2 text-xs text-muted hover:text-red" onClick={() => void ask("Cancelar este lançamento?").then((ok) => ok && act.mutate({ id: l.id, path: "cancelar" }))}>Cancelar</button>
                    </>
                  )}
                  {manage && l.status === "pago" && <button className="text-xs text-muted hover:text-ink" onClick={() => void ask("Estornar a baixa?").then((ok) => ok && act.mutate({ id: l.id, path: "estornar" }))}>Estornar</button>}
                </td>
              </tr>
            ))}
          </Table>
          <Pager page={page} data={q.data} onPage={setPage} />
        </>
      )}
      <NovoLancamento open={creating} onOpenChange={setCreating} kind={kind} />
      <PagarModal lanc={paying} onClose={() => setPaying(null)} />
    </Card>
  );
}

function NovoLancamento({ open, onOpenChange, kind }: { open: boolean; onOpenChange: (b: boolean) => void; kind: "receber" | "pagar" }) {
  const { organization } = useAuth();
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ["fin-categorias", organization?.id], queryFn: () => api<Categoria[]>("/financeiro/categorias"), enabled: open });
  const [f, setF] = useState({ description: "", amount_cents: 0, due_date: new Date().toISOString().slice(0, 10), installments: 1, categoria: "", pessoa: null as any });
  const m = useMutation({
    mutationFn: () => api("/financeiro/lancamentos", { body: { ...f, kind, categoria: f.categoria || null, pessoa: f.pessoa?.id ?? null } }),
    onSuccess: () => { toast.success("Lançamento criado"); qc.invalidateQueries({ queryKey: ["lancamentos"] }); qc.invalidateQueries({ queryKey: ["fin-resumo"] }); onOpenChange(false); setF({ ...f, description: "", amount_cents: 0 }); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title={kind === "receber" ? "Nova conta a receber" : "Nova conta a pagar"}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Descrição" htmlFor="l-d"><Input placeholder="Aluguel de novembro" id="l-d" required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Valor total"><MoneyInput value={f.amount_cents} onChange={(c) => setF({ ...f, amount_cents: c })} /></Field>
          <Field label="Parcelas" htmlFor="l-p"><Input placeholder="1" id="l-p" inputMode="numeric" value={f.installments} onChange={(e) => setF({ ...f, installments: Number(e.target.value.replace(/\D/g, "") || 1) })} /></Field>
          <Field label="Vencimento" htmlFor="l-v"><Input id="l-v" type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
          <Field label="Categoria" htmlFor="l-c"><Select id="l-c" value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })}><option value="">Sem categoria</option>{cats.data?.filter((c) => c.kind === (kind === "receber" ? "receita" : "despesa")).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        </div>
        <PessoaPicker label={kind === "receber" ? "Cliente" : "Fornecedor"} tipo={kind === "pagar" ? "fornecedor" : "cliente"} value={f.pessoa} onChange={(p) => setF({ ...f, pessoa: p })} />
        <Button type="submit" className="w-full" loading={m.isPending}>Salvar</Button>
      </form>
    </Modal>
  );
}

function PagarModal({ lanc, onClose }: { lanc: Lanc | null; onClose: () => void }) {
  const { organization } = useAuth();
  const qc = useQueryClient();
  const contas = useQuery({ queryKey: ["fin-contas", organization?.id], queryFn: () => api<Conta[]>("/financeiro/contas"), enabled: !!lanc });
  const [conta, setConta] = useState("");
  const [paidAt, setPaidAt] = useState(new Date().toISOString().slice(0, 10));
  const [value, setValue] = useState<number | null>(null);
  const m = useMutation({
    mutationFn: () => api(`/financeiro/lancamentos/${lanc!.id}/pagar`, { body: { conta: conta || null, paid_at: paidAt, paid_cents: value ?? lanc!.amount_cents } }),
    onSuccess: () => { toast.success("Baixa registrada"); qc.invalidateQueries({ queryKey: ["lancamentos"] }); qc.invalidateQueries({ queryKey: ["fin-resumo"] }); qc.invalidateQueries({ queryKey: ["fin-contas"] }); onClose(); setValue(null); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={!!lanc} onOpenChange={(v) => !v && onClose()} title={lanc?.kind === "receber" ? "Registrar recebimento" : "Registrar pagamento"} description={lanc?.description}>
      <div className="space-y-4">
        <Field label="Valor"><MoneyInput value={value ?? lanc?.amount_cents} onChange={setValue} /></Field>
        <Field label="Data" htmlFor="pg-d"><Input id="pg-d" type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} /></Field>
        <Field label="Conta" htmlFor="pg-c"><Select id="pg-c" value={conta} onChange={(e) => setConta(e.target.value)}><option value="">Conta padrão</option>{contas.data?.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Button className="w-full" onClick={() => m.mutate()} loading={m.isPending}>Confirmar baixa</Button>
      </div>
    </Modal>
  );
}

function Dre() {
  const { organization } = useAuth();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const q = useQuery({ queryKey: ["dre", organization?.id, month], queryFn: () => api<any>("/financeiro/dre", { params: { month: `${month}-01` } }) });
  const d = q.data;
  return (
    <Card title="Resultado do mês" description="Regime de caixa: o que entrou e saiu de fato no período." action={<Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="h-9 w-44" />}>
      {q.isLoading || !d ? <Spinner /> : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Receitas</h3>
            {d.receitas.map((r: any) => <div key={r.name} className="flex justify-between py-1 text-sm"><span>{r.name}</span><Money cents={r.cents} /></div>)}
            <div className="mt-2 flex justify-between border-t border-line pt-2 text-sm font-semibold"><span>Total</span><Money cents={d.total_receitas_cents} /></div>
            <h3 className="mt-6 mb-2 text-sm font-semibold">Despesas</h3>
            {d.despesas.map((r: any) => <div key={r.name} className="flex justify-between py-1 text-sm"><span>{r.name}</span><Money cents={r.cents} /></div>)}
            <div className="mt-2 flex justify-between border-t border-line pt-2 text-sm font-semibold"><span>Total</span><Money cents={d.total_despesas_cents} /></div>
          </div>
          <div className="space-y-4">
            <Stat label="Resultado do caixa" value={<span className={d.resultado_cents >= 0 ? "text-green" : "text-red"}>{money(d.resultado_cents)}</span>} />
            <Stat label="Carros vendidos no mês" value={d.vendas} hint={`Lucro bruto das vendas: ${money(d.lucro_bruto_vendas_cents)}`} />
          </div>
        </div>
      )}
    </Card>
  );
}

function ContasCategorias() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const contas = useQuery({ queryKey: ["fin-contas", organization?.id], queryFn: () => api<Conta[]>("/financeiro/contas") });
  const cats = useQuery({ queryKey: ["fin-categorias", organization?.id], queryFn: () => api<Categoria[]>("/financeiro/categorias") });
  const [conta, setConta] = useState({ name: "", kind: "banco", opening_balance_cents: 0 });
  const [cat, setCat] = useState({ name: "", kind: "despesa" });
  const addConta = useMutation({ mutationFn: () => api("/financeiro/contas", { body: conta }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["fin-contas"] }); setConta({ ...conta, name: "" }); }, onError: (e) => handleApiError(e) });
  const addCat = useMutation({ mutationFn: () => api("/financeiro/categorias", { body: cat }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["fin-categorias"] }); setCat({ ...cat, name: "" }); }, onError: (e) => handleApiError(e) });
  const manage = can("financeiro.manage");
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Contas bancárias e caixa">
        <ul className="divide-y divide-line text-sm">{contas.data?.map((c) => <li key={c.id} className="flex justify-between py-2"><span>{c.name} <span className="text-muted">· {c.kind}</span></span><Money cents={c.balance_cents} /></li>)}</ul>
        {manage && (
          <form className="mt-4 grid gap-2 sm:grid-cols-[1fr_120px_140px_auto]" onSubmit={(e) => { e.preventDefault(); addConta.mutate(); }}>
            <Input required placeholder="Nome da conta" value={conta.name} onChange={(e) => setConta({ ...conta, name: e.target.value })} />
            <Select value={conta.kind} onChange={(e) => setConta({ ...conta, kind: e.target.value })}><option value="banco">Banco</option><option value="caixa">Caixa</option><option value="cartao">Maquininha</option></Select>
            <MoneyInput value={conta.opening_balance_cents} onChange={(c) => setConta({ ...conta, opening_balance_cents: c })} placeholder="Saldo inicial" />
            <Button type="submit" variant="secondary" loading={addConta.isPending}>Adicionar</Button>
          </form>
        )}
      </Card>
      <Card title="Categorias">
        <div className="flex flex-wrap gap-1.5">{cats.data?.map((c) => <Badge key={c.id} tone={c.kind === "receita" ? "green" : "gray"}>{c.name}</Badge>)}</div>
        {manage && (
          <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); addCat.mutate(); }}>
            <Input required placeholder="Nova categoria" value={cat.name} onChange={(e) => setCat({ ...cat, name: e.target.value })} />
            <Select value={cat.kind} onChange={(e) => setCat({ ...cat, kind: e.target.value })} className="w-32"><option value="despesa">Despesa</option><option value="receita">Receita</option></Select>
            <Button type="submit" variant="secondary">Adicionar</Button>
          </form>
        )}
      </Card>
    </div>
  );
}

function Conciliacao() {
  const { organization } = useAuth();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<any[] | null>(null);
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [conta, setConta] = useState("");
  const contas = useQuery({ queryKey: ["fin-contas", organization?.id], queryFn: () => api<Conta[]>("/financeiro/contas") });
  const upload = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api<any[]>("/financeiro/conciliacao", { form: fd }); },
    onSuccess: (r) => { setRows(r); setSelected(Object.fromEntries(r.map((x, i) => [i, !!x.match]))); },
    onError: (e) => handleApiError(e),
  });
  const confirmM = useMutation({
    mutationFn: () => api<{ reconciled: number }>("/financeiro/conciliacao", { body: { confirm: true, conta: conta || null, pairs: (rows ?? []).map((r, i) => (selected[i] && r.match ? { lancamento: r.match.id, fitid: r.fitid, date: r.date } : null)).filter(Boolean) } }),
    onSuccess: (r) => { toast.success(`${r.reconciled} lançamento(s) baixado(s)`); setRows(null); qc.invalidateQueries({ queryKey: ["lancamentos"] }); qc.invalidateQueries({ queryKey: ["fin-resumo"] }); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Card title="Conciliação bancária" description="Envie o extrato OFX do banco. O sistema sugere o lançamento correspondente e você confirma a baixa." action={<><input ref={input} type="file" accept=".ofx,.OFX" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /><Button size="sm" onClick={() => input.current?.click()} loading={upload.isPending}><Upload className="size-4" /> Enviar OFX</Button></>}>
      {!rows ? <p className="text-sm text-muted">No internet banking, exporte o extrato no formato OFX (Money).</p> : (
        <>
          <Table head={["", "Data", "Descrição no extrato", "Valor", "Lançamento sugerido"]}>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="pl-5"><input type="checkbox" className="size-4 accent-brand" disabled={!r.match} checked={!!selected[i]} onChange={(e) => setSelected({ ...selected, [i]: e.target.checked })} /></td>
                <td className="px-5 py-2 text-muted">{date(r.date)}</td>
                <td className="px-5 py-2">{r.memo}</td>
                <td className={clsx("px-5 py-2 tabular", r.amount_cents >= 0 ? "text-green" : "")}>{money(r.amount_cents)}</td>
                <td className="px-5 py-2 text-sm">{r.already_reconciled ? <span className="text-muted">já conciliado</span> : r.match ? `${r.match.description} (venc. ${date(r.match.due_date)})` : <span className="text-muted">sem correspondência</span>}</td>
              </tr>
            ))}
          </Table>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <Select value={conta} onChange={(e) => setConta(e.target.value)} className="w-56"><option value="">Conta padrão</option>{contas.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
            <Button onClick={() => confirmM.mutate()} loading={confirmM.isPending}>Baixar selecionados</Button>
          </div>
        </>
      )}
    </Card>
  );
}
