/** Pós-venda e garantia, relatórios avançados e lojas do grupo (Premium). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, Download, Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Money, MoneyInput, Pager, SearchInput, useDebounced, type Paged } from "@/components/kit";
import { PlanGate } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, document, maskPhone, money, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

// --- pós-venda -----------------------------------------------------------------------------------

type Garantia = { id: string; venda_id: string; vehicle_title: string; vehicle_placa: string; cliente_name: string; cliente_phone: string; starts_on: string; ends_on: string; km_limit: number | null; coverage: string; is_active: boolean; open_issues: number };

export function PosVendaPage() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const [term, setTerm] = useState("");
  const [active, setActive] = useState("1");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Garantia | null>(null);
  const search = useDebounced(term);
  const q = useQuery({ queryKey: ["garantias", organization?.id, search, active, page], queryFn: () => api<Paged<Garantia>>("/posvenda/garantias", { params: { search, active, page } }) });
  const issues = useQuery({ queryKey: ["ocorrencias", open?.id], queryFn: () => api<Paged<any>>("/posvenda/ocorrencias", { params: { garantia: open!.id } }), enabled: !!open });
  const [oc, setOc] = useState({ description: "", cost_cents: 0 });
  const add = useMutation({
    mutationFn: () => api("/posvenda/ocorrencias", { body: { ...oc, garantia: open!.id } }),
    onSuccess: () => { toast.success("Ocorrência registrada"); setOc({ description: "", cost_cents: 0 }); qc.invalidateQueries({ queryKey: ["ocorrencias"] }); qc.invalidateQueries({ queryKey: ["garantias"] }); },
    onError: (e) => handleApiError(e),
  });
  const upd = useMutation({
    mutationFn: ({ id, ...body }: any) => api(`/posvenda/ocorrencias/${id}`, { method: "PATCH", body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ocorrencias"] }); qc.invalidateQueries({ queryKey: ["garantias"] }); },
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <PageHeader title="Pós-venda e garantia" description="Garantia dos carros vendidos (90 dias por padrão) e ocorrências atendidas." />
      <PlanGate feature="posvenda" title="Pós-venda e garantia">
        <Card title="Garantias" action={<div className="flex gap-2"><SearchInput value={term} onChange={setTerm} placeholder="Cliente ou placa" /><Select value={active} onChange={(e) => setActive(e.target.value)} className="h-9 w-36"><option value="1">Vigentes</option><option value="">Todas</option></Select></div>}>
          {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhuma garantia" icon={<ShieldCheck />}>Cada venda fechada registra a garantia automaticamente.</Empty> : (
            <>
              <Table head={["Veículo", "Cliente", "Vence em", "Ocorrências", ""]}>
                {q.data.results.map((g) => (
                  <tr key={g.id}>
                    <td className="px-5 py-3"><p className="font-medium">{g.vehicle_title}</p><p className="text-xs text-muted">{plate(g.vehicle_placa)}</p></td>
                    <td className="px-5 py-3">{g.cliente_name}<span className="block text-xs text-muted">{g.cliente_phone && maskPhone(g.cliente_phone)}</span></td>
                    <td className={clsx("px-5 py-3", !g.is_active && "text-muted")}>{date(g.ends_on)} {!g.is_active && "(vencida)"}</td>
                    <td className="px-5 py-3">{g.open_issues ? <Badge tone="yellow">{g.open_issues} aberta(s)</Badge> : "—"}</td>
                    <td className="px-5 py-3 text-right"><Button size="sm" variant="secondary" onClick={() => setOpen(g)}>Ocorrências</Button></td>
                  </tr>
                ))}
              </Table>
              <Pager page={page} data={q.data} onPage={setPage} />
            </>
          )}
        </Card>
        <Modal open={!!open} onOpenChange={(v) => !v && setOpen(null)} title={open?.vehicle_title ?? ""} description={open ? `${open.cliente_name} · garantia até ${date(open.ends_on)}` : ""} wide>
          <div className="space-y-4">
            {issues.data?.results.map((o) => (
              <div key={o.id} className="rounded-lg border border-line p-3 text-sm">
                <div className="flex justify-between gap-2"><p>{o.description}</p><Select value={o.status} disabled={!can("vendas.operate")} onChange={(e) => upd.mutate({ id: o.id, status: e.target.value })} className="h-8 w-40"><option value="aberta">Aberta</option><option value="andamento">Em andamento</option><option value="resolvida">Resolvida</option><option value="negada">Fora da garantia</option></Select></div>
                <p className="mt-1 text-xs text-muted">{date(o.created_at)} · custo {money(o.cost_cents)}</p>
              </div>
            ))}
            {can("vendas.operate") && (
              <form className="space-y-2 rounded-lg bg-pale p-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
                <Textarea required rows={2} placeholder="O que o cliente relatou" value={oc.description} onChange={(e) => setOc({ ...oc, description: e.target.value })} />
                <div className="flex gap-2"><div className="w-48"><MoneyInput value={oc.cost_cents} onChange={(c) => setOc({ ...oc, cost_cents: c })} placeholder="Custo" /></div><Button type="submit" variant="secondary" loading={add.isPending}>Registrar ocorrência</Button></div>
                <p className="text-xs text-muted">O custo vira conta a pagar na categoria Garantia.</p>
              </form>
            )}
          </div>
        </Modal>
      </PlanGate>
    </>
  );
}

// --- relatórios ----------------------------------------------------------------------------------

const REPORTS: [string, string][] = [["giro", "Giro por modelo"], ["vendedores", "Desempenho por vendedor"], ["origens", "Leads por origem"], ["estoque", "Estoque atual"], ["vendas", "Vendas detalhadas"]];

export function RelatoriosPage() {
  const { organization } = useAuth();
  const today = new Date();
  const [tipo, setTipo] = useState("giro");
  const [from, setFrom] = useState(new Date(today.getFullYear(), today.getMonth() - 5, 1).toISOString().slice(0, 10));
  const [to, setTo] = useState(today.toISOString().slice(0, 10));
  const [grupo, setGrupo] = useState(false);
  const params = { tipo, from, to, grupo: grupo ? "1" : undefined };
  const q = useQuery({ queryKey: ["relatorio", organization?.id, params], queryFn: () => api<{ columns: { key: string; label: string; type?: string }[]; rows: any[] }>("/painel/relatorios", { params }) });
  const csv = () => download(`/painel/relatorios?${new URLSearchParams({ ...params, grupo: grupo ? "1" : "", export: "csv" } as Record<string, string>)}`);
  return (
    <>
      <PageHeader title="Relatórios" description="Giro, margem e desempenho para decidir o que comprar e como vender." />
      <PlanGate feature="relatorios" title="Relatórios avançados">
        <Card>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Select value={tipo} onChange={(e) => setTipo(e.target.value)} className="h-9 w-52">{REPORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            {tipo !== "estoque" && <><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 w-40" /><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 w-40" /></>}
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" className="size-4 accent-brand" checked={grupo} onChange={(e) => setGrupo(e.target.checked)} /> Todas as lojas</label>
            <Button size="sm" variant="secondary" onClick={csv}><Download className="size-4" /> CSV</Button>
          </div>
          {q.isLoading ? <Spinner /> : !q.data?.rows.length ? <Empty title="Sem dados no período" /> : (
            <Table head={q.data.columns.map((c) => c.label)}>
              {q.data.rows.map((r, i) => (
                <tr key={i}>{q.data!.columns.map((c) => <td key={c.key} className="px-5 py-2.5">{c.type === "money" ? <Money cents={r[c.key]} /> : c.key.includes("data") ? date(r[c.key]) : r[c.key] ?? "—"}</td>)}</tr>
              ))}
            </Table>
          )}
        </Card>
      </PlanGate>
    </>
  );
}

// --- lojas do grupo ------------------------------------------------------------------------------

export function LojasPage() {
  const { organization, setOrganization, reload } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lojas", organization?.id], queryFn: () => api<{ stores: { id: string; name: string; cnpj: string; is_root: boolean; is_member: boolean; vehicles: number }[] }>("/lojas/") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ cnpj: "", legal_name: "", trade_name: "", uf: "", city: "" });
  const create = useMutation({
    mutationFn: () => api<{ id: string }>("/lojas/", { body: f }),
    onSuccess: async () => { toast.success("Filial criada. Cada filial soma R$ 49,90 na mensalidade."); setOpen(false); qc.invalidateQueries({ queryKey: ["lojas"] }); await reload(); },
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <PageHeader title="Lojas" description="Filiais com CNPJ próprio, sob o plano da loja principal." action={<Button onClick={() => setOpen(true)}><Plus className="size-4" /> Nova filial</Button>} />
      <PlanGate feature="multiloja" title="Multi-loja">
        <Card>
          {q.isLoading ? <Spinner /> : (
            <ul className="divide-y divide-line">
              {q.data?.stores.map((s) => (
                <li key={s.id} className="flex items-center justify-between py-3 text-sm">
                  <span className="flex items-center gap-2"><Building2 className="size-4 text-muted" /> <span className="font-medium">{s.name}</span> <span className="text-muted">{document(s.cnpj)}</span> {s.is_root && <Badge tone="green">principal</Badge>}</span>
                  <span className="flex items-center gap-3"><span className="text-muted">{s.vehicles} carros</span>{s.is_member && s.id !== organization?.id && <Button size="sm" variant="secondary" onClick={() => setOrganization(s.id)}>Abrir</Button>}{s.id === organization?.id && <span className="text-xs text-muted">aberta agora</span>}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-muted">Para mover um carro entre lojas, use “Transferir para outra loja” na ficha do veículo. No RENAVE, faça também a transferência entre filiais.</p>
        </Card>
        <Modal open={open} onOpenChange={setOpen} title="Nova filial">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label="CNPJ" htmlFor="fl-c"><Input placeholder="00.000.000/0000-00" id="fl-c" required value={f.cnpj} onChange={(e) => setF({ ...f, cnpj: e.target.value })} /></Field>
            <Field label="Razão social" htmlFor="fl-r"><Input placeholder="Loja Exemplo Filial LTDA" id="fl-r" required value={f.legal_name} onChange={(e) => setF({ ...f, legal_name: e.target.value })} /></Field>
            <Field label="Nome fantasia" htmlFor="fl-n"><Input placeholder="Loja Exemplo Centro" id="fl-n" value={f.trade_name} onChange={(e) => setF({ ...f, trade_name: e.target.value })} /></Field>
            <div className="grid grid-cols-[80px_1fr] gap-3"><Field label="UF" htmlFor="fl-u"><Input placeholder="RN" id="fl-u" required value={f.uf} onChange={(e) => setF({ ...f, uf: e.target.value.toUpperCase().slice(0, 2) })} /></Field><Field label="Cidade" htmlFor="fl-ci"><Input placeholder="Mossoró" id="fl-ci" required value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field></div>
            <Button type="submit" className="w-full" loading={create.isPending}>Criar filial</Button>
          </form>
        </Modal>
      </PlanGate>
    </>
  );
}
