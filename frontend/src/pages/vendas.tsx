import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Handshake, Plus, Printer, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useLocation, useParams, useSearch } from "wouter";

import { KV, Money, MoneyInput, Pager, PessoaPicker, Profit, SearchInput, useDebounced, useMembers, type Paged } from "@/components/kit";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { date, money, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import type { VehicleRow } from "./veiculos";
import { ask } from "@/components/confirm";

type Pagamento = { method: string; method_display?: string; amount_cents: number; installments: number; first_due: string | null; bank: string; trade_in: string | null; trade_in_title?: string | null };

type Venda = {
  id: string;
  status: "proposta" | "reservada" | "fechada" | "cancelada";
  status_display: string;
  vehicle: string;
  vehicle_title: string;
  vehicle_placa: string;
  cliente: string;
  cliente_name: string;
  seller: string | null;
  seller_name: string | null;
  price_cents: number;
  notes: string;
  reserved_until: string | null;
  closed_at: string | null;
  cancel_reason: string;
  cost_cents: number;
  consignor_payout_cents: number;
  profit_cents: number;
  commission_cents: number;
  pagamentos: Pagamento[];
  paid_total_cents: number;
  nota_id: string | null;
  nota_status: string | null;
  renave_state: string | null;
  has_renave: boolean;
  garantia_ate: string | null;
  created_at: string;
};

const TONE: Record<string, "yellow" | "blue" | "green" | "gray"> = { proposta: "yellow", reservada: "blue", fechada: "green", cancelada: "gray" };

const METHODS: [string, string][] = [["pix", "Pix"], ["dinheiro", "Dinheiro"], ["transferencia", "Transferência"], ["debito", "Cartão de débito"], ["credito", "Cartão de crédito"], ["financiamento", "Financiamento bancário"], ["boleto", "Boleto / promissória"], ["troca", "Veículo na troca"]];

export function VendasPage() {
  const { organization, can } = useAuth();
  const [, navigate] = useLocation();
  const [status, setStatus] = useState("");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  const search = useDebounced(term);
  const q = useQuery({ queryKey: ["vendas", organization?.id, status, search, page], queryFn: () => api<Paged<Venda>>("/vendas/", { params: { status, search, page } }) });
  return (
    <>
      <PageHeader title="Vendas" description="Propostas, reservas e vendas fechadas." action={can("vendas.operate") && <Link href="/vendas/nova"><Button><Plus className="size-4" /> Nova venda</Button></Link>} />
      <Card title="Negociações" action={
        <div className="flex flex-wrap gap-2">
          <SearchInput value={term} onChange={(v) => { setTerm(v); setPage(1); }} placeholder="Cliente, modelo ou placa" />
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-9 w-40">
            <option value="">Todas</option><option value="proposta,reservada">Em aberto</option><option value="fechada">Fechadas</option><option value="cancelada">Canceladas</option>
          </Select>
        </div>
      }>
        {q.isLoading ? <Spinner /> : !q.data?.results.length ? (
          <Empty title="Nenhuma venda ainda" icon={<Handshake />}>Comece uma proposta a partir de um carro do estoque.</Empty>
        ) : (
          <>
            <Table head={["Data", "Veículo", "Cliente", "Vendedor", "Valor", "Lucro", "Situação"]}>
              {q.data.results.map((v) => (
                <tr key={v.id} className="cursor-pointer hover:bg-pale/60" onClick={() => navigate(`/vendas/${v.id}`)}>
                  <td className="px-5 py-3 text-muted">{date(v.closed_at ?? v.created_at)}</td>
                  <td className="px-5 py-3"><p className="font-medium">{v.vehicle_title}</p><p className="text-xs text-muted">{plate(v.vehicle_placa)}</p></td>
                  <td className="px-5 py-3">{v.cliente_name}</td>
                  <td className="px-5 py-3 text-muted">{v.seller_name ?? "—"}</td>
                  <td className="px-5 py-3 font-medium"><Money cents={v.price_cents} /></td>
                  <td className="px-5 py-3">{v.status === "fechada" ? <Profit cents={v.profit_cents} /> : <span className="text-muted">—</span>}</td>
                  <td className="px-5 py-3"><Badge tone={TONE[v.status]}>{v.status_display}</Badge></td>
                </tr>
              ))}
            </Table>
            <Pager page={page} data={q.data} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}

export function NovaVendaPage() {
  const params = new URLSearchParams(useSearch());
  const { organization, user } = useAuth();
  const [, navigate] = useLocation();
  const members = useMembers();
  const [vehicleId, setVehicleId] = useState(params.get("veiculo") ?? "");
  const [cliente, setCliente] = useState<any>(null);
  const [price, setPrice] = useState(0);
  const [seller, setSeller] = useState("");
  const [term, setTerm] = useState("");
  const search = useDebounced(term);
  const vehicles = useQuery({ queryKey: ["veiculos-venda", organization?.id, search], queryFn: () => api<Paged<VehicleRow>>("/estoque/veiculos", { params: { search, status: "disponivel,preparacao,reservado", page_size: 30 } }) });
  const selected = vehicles.data?.results.find((v) => v.id === vehicleId);
  useEffect(() => { if (selected && !price) setPrice(selected.price_cents); }, [selected, price]);
  useEffect(() => { if (members.data && !seller) setSeller(members.data.find((m) => m.name === user?.full_name)?.id ?? ""); }, [members.data, seller, user]);
  const create = useMutation({
    mutationFn: () => api<Venda>("/vendas/", { body: { vehicle: vehicleId, cliente: cliente?.id, price_cents: price, seller: seller || null } }),
    onSuccess: (v) => navigate(`/vendas/${v.id}`),
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <Link href="/vendas" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Vendas</Link>
      <PageHeader title="Nova venda" description="Escolha o carro e o cliente. Pagamentos, sinal e fechamento vêm em seguida." />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card title="Veículo" action={<SearchInput value={term} onChange={setTerm} placeholder="Buscar no estoque" />}>
          {vehicles.isLoading ? <Spinner /> : (
            <div className="grid gap-2 sm:grid-cols-2">
              {vehicles.data?.results.map((v) => (
                <button key={v.id} type="button" onClick={() => { setVehicleId(v.id); setPrice(v.price_cents); }} className={`flex gap-3 rounded-lg border p-2 text-left ${vehicleId === v.id ? "border-brand bg-brand-50" : "border-line hover:bg-pale"}`}>
                  {v.cover ? <img src={v.cover} alt="" className="h-14 w-20 rounded object-cover" /> : <div className="h-14 w-20 rounded bg-pale" />}
                  <span className="min-w-0 text-sm">
                    <span className="block truncate font-medium">{v.marca} {v.modelo}</span>
                    <span className="block text-xs text-muted">{v.ano_fabricacao}/{v.ano_modelo} · {plate(v.placa)}</span>
                    <span className="block text-xs font-medium">{money(v.price_cents)} {v.status === "reservado" && <span className="text-sky-700">· reservado</span>}</span>
                  </span>
                </button>
              ))}
              {!vehicles.data?.results.length && <p className="text-sm text-muted">Nenhum carro disponível.</p>}
            </div>
          )}
        </Card>
        <Card title="Negociação">
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <PessoaPicker value={cliente} onChange={setCliente} required />
            <Field label="Valor negociado"><MoneyInput value={price} onChange={setPrice} /></Field>
            {selected && price > 0 && price < selected.price_cents && <p className="text-xs text-muted">Desconto de {money(selected.price_cents - price)} sobre o anunciado.</p>}
            <Field label="Vendedor" htmlFor="n-seller"><Select id="n-seller" value={seller} onChange={(e) => setSeller(e.target.value)}><option value="">Sem vendedor</option>{members.data?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select></Field>
            <Button type="submit" className="w-full" disabled={!vehicleId || !cliente || !price} loading={create.isPending}>Criar proposta</Button>
          </form>
        </Card>
      </div>
    </>
  );
}

export function VendaDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { has } = useBilling();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["venda", id], queryFn: () => api<Venda>(`/vendas/${id}`) });
  const refresh = (v?: Venda) => {
    if (v) qc.setQueryData(["venda", id], v);
    qc.invalidateQueries({ queryKey: ["venda", id] });
    qc.invalidateQueries({ queryKey: ["vendas"] });
    qc.invalidateQueries({ queryKey: ["veiculos"] });
  };
  const [reserveOpen, setReserveOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [renaveOpen, setRenaveOpen] = useState(false);
  const act = (path: string, body?: unknown, msg?: string) => api<Venda>(`/vendas/${id}/${path}`, { body: body ?? {} }).then((v) => { toast.success(msg ?? "Feito"); refresh(v); return v; });
  const close = useMutation({ mutationFn: () => act("close", {}, "Venda fechada"), onError: (e) => handleApiError(e) });
  const nfe = useMutation({
    mutationFn: () => act("nfe", {}, "Nota fiscal enviada para autorização"),
    onError: (e: any) => {
      const missing = e?.fields?.missing;
      if (missing) toast.error(`Complete o cadastro: ${Object.keys(missing).join(", ")}`);
      else handleApiError(e);
    },
  });
  if (q.isLoading) return <Spinner />;
  const v = q.data;
  if (!v) return <Empty title="Venda não encontrada" />;
  const open = v.status === "proposta" || v.status === "reservada";
  const operate = can("vendas.operate");
  return (
    <>
      <Link href="/vendas" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Vendas</Link>
      <PageHeader
        title={v.vehicle_title}
        description={`${v.cliente_name} · ${plate(v.vehicle_placa)}`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONE[v.status]}>{v.status_display}</Badge>
            {operate && v.status === "proposta" && <Button size="sm" variant="secondary" onClick={() => setReserveOpen(true)}>Reservar com sinal</Button>}
            {operate && open && <Button size="sm" onClick={() => void ask("Fechar a venda? O carro sai do estoque e os recebimentos vão para o financeiro.").then((ok) => ok && close.mutate())} loading={close.isPending}>Fechar venda</Button>}
            {operate && v.status !== "cancelada" && <Button size="sm" variant="ghost" onClick={() => setCancelOpen(true)}>Cancelar</Button>}
          </div>
        }
      />
      {v.status === "cancelada" && <p className="mb-4 rounded-lg bg-pale p-3 text-sm">Cancelada: {v.cancel_reason}</p>}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Pagamentos v={v} editable={operate && open} onSaved={refresh} />
          {v.status === "fechada" && (
            <Card title="Documentação da venda">
              <div className="flex flex-wrap gap-2">
                {has("fiscal") && can("fiscal.emit") && (v.nota_id ? (
                  <Link href={`/notas/${v.nota_id}`}><Button variant="secondary" size="sm"><FileText className="size-4" /> Nota fiscal ({v.nota_status})</Button></Link>
                ) : <Button size="sm" variant="secondary" onClick={() => nfe.mutate()} loading={nfe.isPending}><FileText className="size-4" /> Emitir NF-e de venda</Button>)}
                {v.has_renave && can("renave.operate") && (v.renave_state === "FINALIZADO" ? <Badge tone="green">Saída no RENAVE feita</Badge> : <Button size="sm" variant="secondary" onClick={() => setRenaveOpen(true)}>Dar saída no RENAVE</Button>)}
                {!v.has_renave && <span className="self-center text-sm text-muted">Carro sem entrada no RENAVE nesta plataforma.</span>}
              </div>
            </Card>
          )}
          {has("contratos") && <Contratos venda={v} />}
        </div>
        <Card title="Resumo">
          <KV label="Valor da venda"><Money cents={v.price_cents} /></KV>
          <KV label="Pagamentos informados"><Money cents={v.paid_total_cents} className={v.paid_total_cents !== v.price_cents ? "text-red" : ""} /></KV>
          <KV label="Vendedor">{v.seller_name ?? "—"}</KV>
          {v.reserved_until && <KV label="Reservado até">{date(v.reserved_until)}</KV>}
          {v.status === "fechada" && (
            <>
              <div className="my-2 border-t border-line" />
              <KV label="Custo do carro"><Money cents={v.cost_cents} /></KV>
              {v.consignor_payout_cents > 0 && <KV label="Repasse ao dono"><Money cents={v.consignor_payout_cents} /></KV>}
              <KV label="Lucro (sobra)"><Profit cents={v.profit_cents} /></KV>
              {v.commission_cents > 0 && <KV label="Comissão"><Money cents={v.commission_cents} /></KV>}
              <KV label="Fechada em">{date(v.closed_at)}</KV>
              {v.garantia_ate && <KV label="Garantia até">{date(v.garantia_ate)}</KV>}
            </>
          )}
        </Card>
      </div>
      <ReserveModal open={reserveOpen} onOpenChange={setReserveOpen} v={v} onDone={refresh} />
      <CancelModal open={cancelOpen} onOpenChange={setCancelOpen} v={v} onDone={refresh} />
      <RenaveSaidaModal open={renaveOpen} onOpenChange={setRenaveOpen} v={v} onDone={refresh} />
    </>
  );
}

export function Pagamentos({ v, editable, onSaved }: { v: Venda; editable: boolean; onSaved: (v: Venda) => void }) {
  const { organization } = useAuth();
  const [items, setItems] = useState<Pagamento[]>([]);
  const initializedId = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (initializedId.current !== v.id) {
      initializedId.current = v.id;
      setItems(v.pagamentos.filter((p) => p.method !== "sinal"));
    }
  }, [v]);
  const sinal = v.pagamentos.filter((p) => p.method === "sinal").reduce((s, p) => s + p.amount_cents, 0);
  const total = items.reduce((s, p) => s + (p.amount_cents || 0), 0) + sinal;
  const evaluations = useQuery({ queryKey: ["avaliacoes-aprovadas", organization?.id], queryFn: () => api<Paged<any>>("/estoque/avaliacoes", { params: { status: "aprovada" } }), enabled: editable });
  const save = useMutation({
    mutationFn: () => api<Venda>(`/vendas/${v.id}/payments`, { method: "PUT", body: { items } }),
    onSuccess: (r) => { setItems(r.pagamentos.filter((p) => p.method !== "sinal")); toast.success("Pagamentos salvos"); onSaved(r); },
    onError: (e) => handleApiError(e),
  });
  const upd = (i: number, patch: Partial<Pagamento>) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const remaining = v.price_cents - total;
  return (
    <Card title="Formas de pagamento" description="A soma precisa bater com o valor da venda para fechar." action={editable && (
      <Button size="sm" variant="secondary" onClick={() => setItems([...items, { method: "pix", amount_cents: Math.max(remaining, 0), installments: 1, first_due: null, bank: "", trade_in: null }])}><Plus className="size-4" /> Adicionar</Button>
    )}>
      {sinal > 0 && <p className="mb-3 text-sm">Sinal pago na reserva: <strong>{money(sinal)}</strong></p>}
      {!items.length && !sinal && <p className="text-sm text-muted">Nenhuma forma de pagamento informada.</p>}
      <div className="space-y-3">
        {items.map((p, i) => (
          <div key={i} className="grid items-end gap-3 rounded-lg border border-line p-3 sm:grid-cols-[220px_200px_1fr]">
            <Field label="Forma" htmlFor={`pg-m-${i}`}><Select id={`pg-m-${i}`} value={p.method} disabled={!editable} onChange={(e) => upd(i, { method: e.target.value })}>{METHODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            <Field label="Valor" htmlFor={`pg-v-${i}`}><MoneyInput id={`pg-v-${i}`} value={p.amount_cents} disabled={!editable} onChange={(c) => upd(i, { amount_cents: c })} /></Field>
            <div className="flex justify-end pb-2">{editable && <button type="button" aria-label="Remover forma de pagamento" className="text-muted hover:text-red" onClick={() => setItems(items.filter((_, j) => j !== i))}><Trash2 className="size-4" /></button>}</div>
            <div className="grid gap-3 empty:hidden sm:col-span-3 sm:grid-cols-3">
              {p.method === "troca" && (
                <Field label="Avaliação do carro da troca" className="sm:col-span-2">
                  <Select value={p.trade_in ?? ""} disabled={!editable} onChange={(e) => { const ev = evaluations.data?.results.find((x) => x.id === e.target.value); upd(i, { trade_in: e.target.value || null, amount_cents: ev?.offer_cents ?? p.amount_cents }); }}>
                    <option value="">{p.trade_in_title ?? "Escolha uma avaliação aprovada"}</option>
                    {evaluations.data?.results.map((ev) => <option key={ev.id} value={ev.id}>{ev.marca} {ev.modelo} {ev.placa} — {money(ev.offer_cents)}</option>)}
                  </Select>
                </Field>
              )}
              {p.method === "financiamento" && <Field label="Banco"><Input value={p.bank} disabled={!editable} onChange={(e) => upd(i, { bank: e.target.value })} placeholder="Banco / financeira" /></Field>}
              {["boleto", "credito"].includes(p.method) && <Field label="Parcelas"><Input placeholder="1" inputMode="numeric" value={p.installments} disabled={!editable} onChange={(e) => upd(i, { installments: Number(e.target.value.replace(/\D/g, "") || 1) })} /></Field>}
              {["boleto", "credito", "financiamento"].includes(p.method) && <Field label="1º vencimento"><Input type="date" value={p.first_due ?? ""} disabled={!editable} onChange={(e) => upd(i, { first_due: e.target.value || null })} /></Field>}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span>Total: <strong>{money(total)}</strong> {remaining !== 0 && <span className={remaining > 0 ? "text-warn" : "text-red"}>· {remaining > 0 ? `faltam ${money(remaining)}` : `passou ${money(-remaining)}`}</span>}</span>
        {editable && <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>Salvar pagamentos</Button>}
      </div>
    </Card>
  );
}

function ReserveModal({ open, onOpenChange, v, onDone }: { open: boolean; onOpenChange: (b: boolean) => void; v: Venda; onDone: (v: Venda) => void }) {
  const [amount, setAmount] = useState(0);
  const [until, setUntil] = useState(new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10));
  const m = useMutation({
    mutationFn: () => api<Venda>(`/vendas/${v.id}/reserve`, { body: { amount_cents: amount, until } }),
    onSuccess: (r) => { toast.success("Carro reservado"); onOpenChange(false); onDone(r); },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Reservar com sinal" description="O carro fica reservado e o sinal entra como recebido no financeiro.">
      <div className="space-y-4">
        <Field label="Valor do sinal"><MoneyInput value={amount} onChange={setAmount} /></Field>
        <Field label="Reservado até" htmlFor="r-until"><Input id="r-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></Field>
        <Button className="w-full" onClick={() => m.mutate()} loading={m.isPending} disabled={!amount}>Reservar</Button>
      </div>
    </Modal>
  );
}

function CancelModal({ open, onOpenChange, v, onDone }: { open: boolean; onOpenChange: (b: boolean) => void; v: Venda; onDone: (v: Venda) => void }) {
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => api<Venda & { paid_entries_to_refund: number }>(`/vendas/${v.id}/cancel`, { body: { reason } }),
    onSuccess: (r) => {
      toast.success(r.paid_entries_to_refund ? `Venda cancelada. ${r.paid_entries_to_refund} recebimento(s) já pago(s): faça a devolução pelo financeiro.` : "Venda cancelada");
      onOpenChange(false);
      onDone(r);
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Cancelar venda" description={v.status === "fechada" ? "O carro volta ao estoque e os recebimentos em aberto são cancelados." : "A proposta deixa de valer."}>
      <div className="space-y-4">
        <Field label="Motivo" htmlFor="c-reason"><Input id="c-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Cliente desistiu, crédito negado…" /></Field>
        <Button variant="danger" className="w-full" onClick={() => m.mutate()} loading={m.isPending}>Cancelar venda</Button>
      </div>
    </Modal>
  );
}

function RenaveSaidaModal({ open, onOpenChange, v, onDone }: { open: boolean; onOpenChange: (b: boolean) => void; v: Venda; onDone: (v: Venda) => void }) {
  const [code, setCode] = useState("");
  const m = useMutation({
    mutationFn: () => api<Venda>(`/vendas/${v.id}/renave-saida`, { body: { cod_seguranca_crv: code } }),
    onSuccess: (r) => { toast.success("Saída enviada ao RENAVE"); onOpenChange(false); onDone(r); },
    onError: (e: any) => {
      const missing = e?.fields?.missing;
      if (missing) toast.error(`Complete o cadastro do comprador: ${Object.keys(missing).join(", ")}`);
      else handleApiError(e);
    },
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Saída no RENAVE" description="Os dados do comprador e da venda vêm do cadastro. Custa R$ 30,00.">
      <div className="space-y-4">
        <Field label="Código de segurança do CRV" htmlFor="rs-code"><Input placeholder="Código no CRV" id="rs-code" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
        <Button className="w-full" disabled={!code} loading={m.isPending} onClick={() => m.mutate()}>Enviar saída</Button>
      </div>
    </Modal>
  );
}

function Contratos({ venda }: { venda: Venda }) {
  const { organization } = useAuth();
  const qc = useQueryClient();
  const modelos = useQuery({ queryKey: ["modelos", organization?.id], queryFn: () => api<any[]>("/contratos/modelos") });
  const docs = useQuery({ queryKey: ["documentos", venda.id], queryFn: () => api<Paged<any>>("/contratos/documentos", { params: { venda: venda.id } }) });
  const gen = useMutation({
    mutationFn: (modelo: string) => api("/contratos/documentos/generate", { body: { modelo, venda: venda.id } }),
    onSuccess: () => { toast.success("Documento gerado"); qc.invalidateQueries({ queryKey: ["documentos", venda.id] }); },
    onError: (e) => handleApiError(e),
  });
  const kinds = useMemo(() => modelos.data?.filter((m) => ["compra_venda", "recibo", "garantia", "procuracao"].includes(m.kind) && m.is_active) ?? [], [modelos.data]);
  return (
    <Card title="Contratos e recibos">
      <div className="mb-4 flex flex-wrap gap-2">
        {kinds.map((m) => <Button key={m.id} size="sm" variant="secondary" onClick={() => gen.mutate(m.id)} loading={gen.isPending && gen.variables === m.id}>{m.kind_display}</Button>)}
      </div>
      {docs.data?.results.length ? (
        <ul className="divide-y divide-line text-sm">
          {docs.data.results.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2">
              <span>{d.kind_display} <span className="text-muted">· {date(d.created_at)}</span> {d.signature_status && <Badge tone={d.signature_status === "signed" ? "green" : "yellow"}>{d.signature_display}</Badge>}</span>
              <Link href={`/contratos/${d.id}`} className="inline-flex items-center gap-1 font-medium text-brand"><Printer className="size-4" /> Abrir</Link>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-muted">Gere o contrato com os dados da venda já preenchidos.</p>}
    </Card>
  );
}
