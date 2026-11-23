import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Camera, ClipboardCheck, Plus, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useLocation, useParams } from "wouter";

import { KV, Money, MoneyInput, Pager, PessoaPicker, type Paged } from "@/components/kit";
import { Badge, Button, Card, Empty, Field, Input, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, money, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { FipePicker, VEHICLE_PLACEHOLDERS as PH } from "./veiculos";
import { ask } from "@/components/confirm";

type Avaliacao = {
  id: string;
  status: string;
  status_display: string;
  cliente: string | null;
  cliente_name: string | null;
  evaluator_name: string | null;
  kind: string;
  placa: string;
  marca: string;
  modelo: string;
  versao: string;
  ano_fabricacao: number | null;
  ano_modelo: number | null;
  cor: string;
  km: number | null;
  checklist: Record<string, string>;
  notes: string;
  fipe_code: string;
  fipe_price_cents: number | null;
  estimated_repairs_cents: number;
  offer_cents: number;
  max_offer_cents: number | null;
  photos: { id: string; url: string; label: string }[];
  vehicle_id: string | null;
  created_at: string;
};

const TONE: Record<string, "yellow" | "green" | "red" | "gray"> = { aberta: "yellow", aprovada: "green", recusada: "red", comprada: "gray" };
const CHECKLIST = ["Lataria", "Pintura", "Vidros", "Pneus", "Suspensão", "Freios", "Motor", "Câmbio", "Ar-condicionado", "Elétrica", "Interior", "Documentação"];
const STATES: [string, string, string][] = [["ok", "OK", "border-green text-green bg-green-50"], ["atencao", "Atenção", "border-warn text-[#8a6500] bg-warn-50"], ["ruim", "Ruim", "border-red text-red bg-red-50"]];

export function AvaliacoesPage() {
  const { organization, can } = useAuth();
  const [, navigate] = useLocation();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["avaliacoes", organization?.id, status, page], queryFn: () => api<Paged<Avaliacao>>("/estoque/avaliacoes", { params: { status, page } }) });
  return (
    <>
      <PageHeader title="Avaliações" description="Avalie carros para compra ou troca. Aprovada, a avaliação vira veículo do estoque com um clique." action={can("vendas.operate") && <Link href="/avaliacoes/nova"><Button><Plus className="size-4" /> Nova avaliação</Button></Link>} />
      <Card title="Avaliações" action={<Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-9 w-40"><option value="">Todas</option><option value="aberta">Em avaliação</option><option value="aprovada">Aprovadas</option><option value="comprada">Compradas</option><option value="recusada">Recusadas</option></Select>}>
        {q.isLoading ? <Spinner /> : !q.data?.results.length ? <Empty title="Nenhuma avaliação" icon={<ClipboardCheck />}>Use pelo celular no pátio: fotos e checklist em poucos minutos.</Empty> : (
          <>
            <Table head={["Data", "Veículo", "Cliente", "FIPE", "Oferta", "Situação"]}>
              {q.data.results.map((a) => (
                <tr key={a.id} className="cursor-pointer hover:bg-pale/60" onClick={() => navigate(`/avaliacoes/${a.id}`)}>
                  <td className="px-5 py-3 text-muted">{date(a.created_at)}</td>
                  <td className="px-5 py-3"><p className="font-medium">{a.marca} {a.modelo}</p><p className="text-xs text-muted">{[a.ano_fabricacao && `${a.ano_fabricacao}/${a.ano_modelo}`, a.placa && plate(a.placa)].filter(Boolean).join(" · ")}</p></td>
                  <td className="px-5 py-3">{a.cliente_name ?? "—"}</td>
                  <td className="px-5 py-3 text-muted"><Money cents={a.fipe_price_cents} /></td>
                  <td className="px-5 py-3 font-medium"><Money cents={a.offer_cents || null} /></td>
                  <td className="px-5 py-3"><Badge tone={TONE[a.status]}>{a.status_display}</Badge></td>
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

export function AvaliacaoPage() {
  const params = useParams<{ id?: string }>();
  const isNew = !params.id;
  const { can } = useAuth();
  const qc = useQueryClient();
  const [, navigate] = useLocation();
  const q = useQuery({ queryKey: ["avaliacao", params.id], queryFn: () => api<Avaliacao>(`/estoque/avaliacoes/${params.id}`), enabled: !isNew });
  const [f, setF] = useState<Partial<Avaliacao> & { clienteRef?: any }>({ kind: "carro", checklist: {} });
  const [fipeOpen, setFipeOpen] = useState(false);
  const photoInput = useRef<HTMLInputElement>(null);
  const hydratedId = useRef<string | undefined>(undefined);
  useEffect(() => { if (q.data && hydratedId.current !== q.data.id) { hydratedId.current = q.data.id; setF({ ...q.data, clienteRef: q.data.cliente ? { id: q.data.cliente, nome: q.data.cliente_name, documento: "" } : null }); } }, [q.data]);
  const set = (k: string, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  const status = q.data?.status ?? f.status;
  const locked = status === "comprada";

  const save = useMutation({
    mutationFn: () => {
      const { clienteRef, photos: _p, ...rest } = f as any;
      const body = { ...rest, cliente: clienteRef?.id ?? null, placa: (rest.placa || "").replace(/\W/g, "").toUpperCase() };
      return api<Avaliacao>(isNew ? "/estoque/avaliacoes" : `/estoque/avaliacoes/${params.id}`, { method: isNew ? "POST" : "PATCH", body });
    },
    onSuccess: (a) => { toast.success("Avaliação salva"); qc.invalidateQueries({ queryKey: ["avaliacoes"] }); qc.setQueryData(["avaliacao", a.id], a); if (isNew) navigate(`/avaliacoes/${a.id}`); },
    onError: (e) => handleApiError(e),
  });
  const lookup = useMutation({
    mutationFn: () => api<any>(`/estoque/veiculos/plate/${(f.placa ?? "").replace(/\W/g, "")}`),
    onSuccess: (d) => setF((x) => ({ ...x, marca: d.marca || x.marca, modelo: d.modelo || x.modelo, versao: d.versao || x.versao, ano_fabricacao: d.ano_fabricacao || x.ano_fabricacao, ano_modelo: d.ano_modelo || x.ano_modelo, cor: d.cor || x.cor, fipe_code: d.fipe?.code || x.fipe_code, fipe_price_cents: d.fipe?.price_cents ?? x.fipe_price_cents })),
    onError: (e) => handleApiError(e),
  });
  const photos = useMutation({
    mutationFn: (files: FileList) => { const fd = new FormData(); Array.from(files).forEach((x) => fd.append("files", x)); return api<Avaliacao>(`/estoque/avaliacoes/${params.id}/photos`, { form: fd }); },
    onSuccess: (a) => { qc.setQueryData(["avaliacao", a.id], a); toast.success("Fotos enviadas"); },
    onError: (e) => handleApiError(e),
  });
  const decide = useMutation({
    mutationFn: (path: "approve" | "refuse") => api<Avaliacao>(`/estoque/avaliacoes/${params.id}/${path}`, { body: { offer_cents: f.offer_cents } }),
    onSuccess: (a) => { qc.setQueryData(["avaliacao", a.id], a); qc.invalidateQueries({ queryKey: ["avaliacoes"] }); toast.success(a.status === "aprovada" ? "Avaliação aprovada" : "Avaliação recusada"); },
    onError: (e) => handleApiError(e),
  });
  const buy = useMutation({
    mutationFn: () => api<{ vehicle_id: string }>(`/estoque/avaliacoes/${params.id}/buy`, { body: { price_cents: f.offer_cents } }),
    onSuccess: (r) => { toast.success("Carro comprado e incluído no estoque"); navigate(`/veiculos/${r.vehicle_id}`); },
    onError: (e) => handleApiError(e),
  });
  if (!isNew && q.isLoading) return <Spinner />;
  const input = (k: keyof Avaliacao, label: string, props: Record<string, unknown> = {}) => (
    <Field label={label} htmlFor={`a-${k}`}><Input id={`a-${k}`} placeholder={PH[k as string]} disabled={locked} value={(f[k] as any) ?? ""} onChange={(e) => set(k, e.target.value)} {...props} /></Field>
  );
  const numeric = (k: keyof Avaliacao, label: string) => (
    <Field label={label} htmlFor={`a-${k}`}><Input id={`a-${k}`} inputMode="numeric" placeholder={PH[k as string]} disabled={locked} value={(f[k] as any) ?? ""} onChange={(e) => set(k, e.target.value.replace(/\D/g, "") ? Number(e.target.value.replace(/\D/g, "")) : null)} /></Field>
  );
  const suggested = f.fipe_price_cents ? Math.max(Math.floor((f.fipe_price_cents * 85) / 100) - (f.estimated_repairs_cents ?? 0), 0) : null;
  return (
    <>
      <Link href="/avaliacoes" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Avaliações</Link>
      <PageHeader title={isNew ? "Nova avaliação" : `${f.marca ?? ""} ${f.modelo ?? ""}`} action={!isNew && <Badge tone={TONE[status ?? "aberta"]}>{q.data?.status_display ?? f.status_display}</Badge>} />
      <form className="grid gap-6 lg:grid-cols-[1fr_340px]" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="space-y-6">
          <Card title="Veículo">
            <div className="mb-4 flex flex-wrap items-end gap-2">
              <div className="w-40">{input("placa", "Placa", { placeholder: "ABC1D23" })}</div>
              <Button type="button" variant="secondary" disabled={locked || (f.placa ?? "").replace(/\W/g, "").length < 7} loading={lookup.isPending} onClick={() => lookup.mutate()}><Search className="size-4" /> Buscar pela placa</Button>
              <Button type="button" variant="ghost" disabled={locked} onClick={() => setFipeOpen(true)}>Tabela FIPE</Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {input("marca", "Marca", { required: true })}
              {input("modelo", "Modelo", { required: true })}
              {input("versao", "Versão")}
              {numeric("ano_fabricacao", "Ano fab.")}
              {numeric("ano_modelo", "Ano modelo")}
              {numeric("km", "Quilometragem")}
              {input("cor", "Cor")}
            </div>
            <div className="mt-4"><PessoaPicker label="Dono do carro / cliente" value={f.clienteRef ?? null} onChange={(p) => set("clienteRef", p)} /></div>
          </Card>
          <Card title="Checklist">
            <div className="grid gap-2 sm:grid-cols-2">
              {CHECKLIST.map((item) => (
                <div key={item} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                  <span>{item}</span>
                  <span className="flex gap-1">
                    {STATES.map(([k, l, cls]) => (
                      <button key={k} type="button" disabled={locked} onClick={() => set("checklist", { ...(f.checklist ?? {}), [item]: k })} className={clsx("rounded-md border px-2 py-0.5 text-xs", (f.checklist ?? {})[item] === k ? cls : "border-line text-muted")}>{l}</button>
                    ))}
                  </span>
                </div>
              ))}
            </div>
            <Field label="Observações" htmlFor="a-notes" className="mt-4"><Textarea id="a-notes" rows={3} disabled={locked} value={f.notes ?? ""} onChange={(e) => set("notes", e.target.value)} placeholder="Batidas, peças a trocar, histórico…" /></Field>
          </Card>
          {!isNew && (
            <Card title="Fotos" action={!locked && (<><input ref={photoInput} type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={(e) => e.target.files?.length && photos.mutate(e.target.files)} /><Button type="button" size="sm" onClick={() => photoInput.current?.click()} loading={photos.isPending}><Camera className="size-4" /> Tirar / enviar fotos</Button></>)}>
              {q.data?.photos.length ? <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{q.data.photos.map((p) => <img key={p.id} src={p.url} alt="" className="aspect-[4/3] w-full rounded-md object-cover" />)}</div> : <p className="text-sm text-muted">Fotografe os quatro lados, painel, motor e avarias.</p>}
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card title="Valores">
            <div className="space-y-3">
              <Field label="FIPE"><MoneyInput value={f.fipe_price_cents} disabled={locked} onChange={(c) => set("fipe_price_cents", c)} /></Field>
              <Field label="Reparos estimados"><MoneyInput value={f.estimated_repairs_cents} disabled={locked} onChange={(c) => set("estimated_repairs_cents", c)} /></Field>
              {suggested !== null && <KV label="Sugestão (85% FIPE − reparos)">{money(suggested)}</KV>}
              <Field label="Oferta da loja"><MoneyInput value={f.offer_cents} disabled={locked} onChange={(c) => set("offer_cents", c)} /></Field>
            </div>
            {!locked && <Button type="submit" className="mt-4 w-full" loading={save.isPending}>Salvar avaliação</Button>}
          </Card>
          {!isNew && can("estoque.manage") && status !== "comprada" && (
            <Card title="Decisão">
              <div className="flex flex-col gap-2">
                {status !== "aprovada" && <Button type="button" variant="secondary" onClick={() => decide.mutate("approve")}>Aprovar com esta oferta</Button>}
                {status === "aprovada" && <Button type="button" onClick={() => void ask(`Comprar por ${money(f.offer_cents)}? O carro entra no estoque e a compra vai para contas a pagar.`).then((ok) => ok && buy.mutate())} loading={buy.isPending}>Comprar e incluir no estoque</Button>}
                {status !== "recusada" && <Button type="button" variant="ghost" onClick={() => decide.mutate("refuse")}>Recusar</Button>}
                {status === "aprovada" && <p className="text-xs text-muted">Se for troca, use a avaliação aprovada como forma de pagamento na venda.</p>}
              </div>
            </Card>
          )}
          {f.vehicle_id && <Link href={`/veiculos/${f.vehicle_id}`} className="block text-sm font-medium text-brand">Ver veículo no estoque →</Link>}
        </div>
      </form>
      <FipePicker open={fipeOpen} onOpenChange={setFipeOpen} kind={f.kind ?? "carro"} onPick={(r) => setF((x) => ({ ...x, marca: x.marca || r.brand, modelo: x.modelo || r.model, ano_modelo: x.ano_modelo || r.model_year, fipe_code: r.code, fipe_price_cents: r.price_cents }))} />
    </>
  );
}
