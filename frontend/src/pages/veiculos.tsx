import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Camera, Car, FileUp, Plus, Search, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useLocation, useParams } from "wouter";

import { Money, MoneyInput, Pager, PessoaPicker, Profit, SearchInput, Tabs, useDebounced, useTab, KV, type Paged } from "@/components/kit";
import { LockedPanel } from "@/components/PlanGate";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { date, money, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { ask } from "@/components/confirm";

export type VehicleRow = {
  id: string;
  title: string;
  marca: string;
  modelo: string;
  versao: string;
  placa: string;
  ano_fabricacao: number | null;
  ano_modelo: number | null;
  km: number | null;
  status: string;
  status_display: string;
  ownership: string;
  price_cents: number;
  fipe_price_cents: number | null;
  cover: string | null;
  days_in_stock: number | null;
  published: boolean;
};

type Vehicle = VehicleRow & {
  kind: string;
  renavam: string;
  chassi: string;
  cor: string;
  combustivel: string;
  cambio: string;
  portas: number | null;
  opcionais: string[];
  descricao: string;
  consignor: string | null;
  consignor_name: string | null;
  consignment_mode: string;
  consignment_value: number;
  consignment_until: string | null;
  supplier: string | null;
  supplier_name: string | null;
  purchase_date: string | null;
  purchase_price_cents: number;
  entry_date: string | null;
  min_price_cents: number;
  fipe_code: string;
  fipe_reference: string;
  featured: boolean;
  location: string;
  keys: string;
  photos: { id: string; url: string }[];
  costs: { id: string; category: string; category_display: string; description: string; supplier_name: string | null; amount_cents: number; date: string; payable_status: string | null }[];
  documents: { id: string; kind_display: string; name: string; url: string; created_at: string }[];
  renave: { id: string; state: string; state_display: string } | null;
  summary: { costs_cents: number; total_cost_cents: number; expected_profit_cents: number | null; consignor_payout_cents: number; days_in_stock: number | null };
};

export const STATUS_TONE: Record<string, "green" | "yellow" | "blue" | "gray" | "red"> = {
  disponivel: "green",
  preparacao: "yellow",
  reservado: "blue",
  vendido: "gray",
  devolvido: "gray",
  transferido: "gray",
};

const PH: Record<string, string> = {
  marca: "Chevrolet",
  modelo: "Onix",
  versao: "LT 1.0 Turbo",
  ano_fabricacao: "2021",
  ano_modelo: "2022",
  cor: "Prata",
  km: "45000",
  combustivel: "Flex",
  cambio: "Manual ou automático",
  renavam: "11 dígitos",
  chassi: "17 caracteres",
  location: "Pátio 2, vaga 14",
};

const OPCIONAIS = ["Ar-condicionado", "Direção hidráulica/elétrica", "Vidros elétricos", "Travas elétricas", "Airbag", "Freios ABS", "Multimídia", "Câmera de ré", "Sensor de estacionamento", "Bancos de couro", "Rodas de liga", "Teto solar", "Piloto automático", "Chave presencial", "Único dono", "Manual e chave reserva", "IPVA pago"];

export { PH as VEHICLE_PLACEHOLDERS };

export function VeiculosPage() {
  const { organization, can } = useAuth();
  const [, navigate] = useLocation();
  const [status, setStatus] = useState("");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const search = useDebounced(term);
  const q = useQuery({
    queryKey: ["veiculos", organization?.id, status, search, page],
    queryFn: () => api<Paged<VehicleRow>>("/estoque/veiculos", { params: { status: status || undefined, active: status ? undefined : "true", search, page } }),
  });
  return (
    <>
      <PageHeader
        title="Veículos"
        description="Estoque da loja: preço, custos, fotos e situação de cada carro."
        action={
          can("estoque.manage") && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Cadastrar veículo
            </Button>
          )
        }
      />
      <Card
        title="Estoque"
        action={
          <div className="flex flex-wrap gap-2">
            <SearchInput value={term} onChange={(v) => { setTerm(v); setPage(1); }} placeholder="Modelo, marca ou placa" />
            <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-9 w-44">
              <option value="">Em estoque</option>
              <option value="disponivel">Disponíveis</option>
              <option value="preparacao">Em preparação</option>
              <option value="reservado">Reservados</option>
              <option value="vendido">Vendidos</option>
              <option value="devolvido">Devolvidos</option>
            </Select>
          </div>
        }
      >
        {q.isLoading ? (
          <Spinner />
        ) : !q.data?.results.length ? (
          <Empty title="Cadastre o primeiro carro do estoque" icon={<Car />}>
            Use a placa para puxar os dados e a FIPE automaticamente.
          </Empty>
        ) : (
          <>
            <Table head={["", "Veículo", "Situação", "Dias", "FIPE", "Preço", ""]}>
              {q.data.results.map((v) => (
                <tr key={v.id} className="cursor-pointer hover:bg-pale/60" onClick={() => navigate(`/veiculos/${v.id}`)}>
                  <td className="w-20 py-2 pl-5">
                    {v.cover ? <img src={v.cover} alt="" className="h-12 w-16 rounded-md object-cover" /> : <div className="grid h-12 w-16 place-items-center rounded-md bg-pale text-muted"><Car className="size-5" /></div>}
                  </td>
                  <td className="px-5 py-3">
                    <p className="font-medium">{v.marca} {v.modelo}</p>
                    <p className="text-xs text-muted">
                      {[v.versao, v.ano_fabricacao && `${v.ano_fabricacao}/${v.ano_modelo}`, v.km != null && `${v.km.toLocaleString("pt-BR")} km`, v.placa && plate(v.placa)].filter(Boolean).join(" · ")}
                    </p>
                  </td>
                  <td className="px-5 py-3">
                    <Badge tone={STATUS_TONE[v.status]}>{v.status_display}</Badge>
                    {v.ownership === "consignado" && <span className="ml-1 text-xs text-muted">consignado</span>}
                  </td>
                  <td className={clsx("px-5 py-3 tabular", (v.days_in_stock ?? 0) > 90 ? "text-red" : (v.days_in_stock ?? 0) > 60 ? "text-warn" : "")}>{v.days_in_stock ?? "—"}</td>
                  <td className="px-5 py-3"><Money cents={v.fipe_price_cents} className="text-muted" /></td>
                  <td className="px-5 py-3 font-medium"><Money cents={v.price_cents || null} /></td>
                  <td className="px-5 py-3 text-right text-xs text-muted">{v.published ? "no site" : ""}</td>
                </tr>
              ))}
            </Table>
            <Pager page={page} data={q.data} onPage={setPage} />
          </>
        )}
      </Card>
      <VehicleForm open={creating} onOpenChange={setCreating} onSaved={(id) => navigate(`/veiculos/${id}`)} />
    </>
  );
}

type Form = Partial<Vehicle> & { consignorRef?: { id: string; nome: string; documento: string } | null; supplierRef?: { id: string; nome: string; documento: string } | null };

export function VehicleForm({ open, onOpenChange, vehicle, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; vehicle?: Vehicle; onSaved?: (id: string) => void }) {
  const qc = useQueryClient();
  const { has } = useBilling();
  const [f, setF] = useState<Form>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [fipeOpen, setFipeOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setF(
      vehicle
        ? { ...vehicle, consignorRef: vehicle.consignor ? { id: vehicle.consignor, nome: vehicle.consignor_name ?? "", documento: "" } : null, supplierRef: vehicle.supplier ? { id: vehicle.supplier, nome: vehicle.supplier_name ?? "", documento: "" } : null }
        : { kind: "carro", ownership: "proprio", opcionais: [], purchase_date: new Date().toISOString().slice(0, 10) },
    );
  }, [open, vehicle?.id]);
  const set = (k: keyof Form, v: unknown) => setF((x) => ({ ...x, [k]: v }));

  const lookup = useMutation({
    mutationFn: (p: string) => api<any>(`/estoque/veiculos/plate/${p}`),
    onSuccess: (d) => {
      setF((x) => ({
        ...x,
        marca: d.marca || x.marca,
        modelo: d.modelo || x.modelo,
        versao: d.versao || x.versao,
        ano_fabricacao: d.ano_fabricacao || x.ano_fabricacao,
        ano_modelo: d.ano_modelo || x.ano_modelo,
        cor: d.cor || x.cor,
        combustivel: d.combustivel || x.combustivel,
        fipe_code: d.fipe?.code || x.fipe_code,
        fipe_price_cents: d.fipe?.price_cents ?? x.fipe_price_cents,
        fipe_reference: d.fipe?.reference || x.fipe_reference,
      }));
      toast.success(d.cached ? "Dados preenchidos (consulta recente, sem custo)" : "Dados preenchidos pela placa");
    },
    onError: (e) => handleApiError(e),
  });

  const save = useMutation({
    mutationFn: () => {
      const { consignorRef, supplierRef, photos: _p, costs: _c, documents: _d, renave: _r, summary: _s, ...rest } = f as any;
      const body = { ...rest, consignor: consignorRef?.id ?? null, supplier: supplierRef?.id ?? null, placa: (rest.placa || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase() };
      return api<Vehicle>(vehicle ? `/estoque/veiculos/${vehicle.id}` : "/estoque/veiculos", { method: vehicle ? "PATCH" : "POST", body });
    },
    onSuccess: (v) => {
      toast.success(vehicle ? "Veículo atualizado" : "Veículo cadastrado");
      qc.invalidateQueries({ queryKey: ["veiculos"] });
      qc.invalidateQueries({ queryKey: ["veiculo", v.id] });
      onOpenChange(false);
      onSaved?.(v.id);
    },
    onError: (e: any) => {
      const errs: Record<string, string> = {};
      Object.entries(e?.fields ?? {}).forEach(([k, v]) => (errs[k] = Array.isArray(v) ? String(v[0]) : String(v)));
      setErrors(errs);
      handleApiError(e);
    },
  });

  const text = (k: keyof Form, label: string, props: Record<string, unknown> = {}) => (
    <Field label={label} htmlFor={`v-${k}`} error={errors[k as string]}>
      <Input id={`v-${k}`} placeholder={PH[k as string]} value={(f[k] as any) ?? ""} onChange={(e) => set(k, e.target.value)} aria-invalid={!!errors[k as string]} {...props} />
    </Field>
  );
  const num = (k: keyof Form, label: string) => (
    <Field label={label} htmlFor={`v-${k}`} error={errors[k as string]}>
      <Input id={`v-${k}`} inputMode="numeric" placeholder={PH[k as string]} value={(f[k] as any) ?? ""} onChange={(e) => set(k, e.target.value.replace(/\D/g, "") ? Number(e.target.value.replace(/\D/g, "")) : null)} />
    </Field>
  );

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={vehicle ? "Editar veículo" : "Cadastrar veículo"} wide>
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="flex flex-wrap items-end gap-2 rounded-lg bg-pale p-3">
          <Field label="Placa" htmlFor="v-placa" error={errors.placa} className="w-40">
            <Input id="v-placa" value={f.placa ?? ""} onChange={(e) => set("placa", e.target.value.toUpperCase())} placeholder="ABC1D23" />
          </Field>
          <Button type="button" variant="secondary" loading={lookup.isPending} disabled={(f.placa ?? "").replace(/\W/g, "").length < 7} onClick={() => lookup.mutate((f.placa ?? "").replace(/\W/g, ""))}>
            <Search className="size-4" /> Buscar pela placa
          </Button>
          <Button type="button" variant="ghost" onClick={() => setFipeOpen(true)}>
            Escolher na tabela FIPE
          </Button>
          {f.fipe_price_cents ? <span className="ml-auto text-sm">FIPE: <strong>{money(f.fipe_price_cents)}</strong> <span className="text-muted">{f.fipe_reference}</span></span> : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Tipo" htmlFor="v-kind">
            <Select id="v-kind" value={f.kind ?? "carro"} onChange={(e) => set("kind", e.target.value)}>
              <option value="carro">Carro</option>
              <option value="moto">Moto</option>
              <option value="caminhao">Caminhão / utilitário</option>
            </Select>
          </Field>
          {text("marca", "Marca")}
          {text("modelo", "Modelo")}
          {text("versao", "Versão")}
          {num("ano_fabricacao", "Ano de fabricação")}
          {num("ano_modelo", "Ano do modelo")}
          {text("cor", "Cor")}
          {num("km", "Quilometragem")}
          {text("combustivel", "Combustível")}
          {text("cambio", "Câmbio")}
          {text("renavam", "RENAVAM")}
          {text("chassi", "Chassi")}
        </div>
        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold">Opcionais</legend>
          <div className="flex flex-wrap gap-2">
            {OPCIONAIS.map((o) => {
              const on = (f.opcionais ?? []).includes(o);
              return (
                <button key={o} type="button" onClick={() => set("opcionais", on ? (f.opcionais ?? []).filter((x) => x !== o) : [...(f.opcionais ?? []), o])} className={clsx("rounded-md border px-2.5 py-1 text-xs", on ? "border-brand bg-brand-50 text-brand" : "border-line text-muted hover:text-ink")}>
                  {o}
                </button>
              );
            })}
          </div>
        </fieldset>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Origem" htmlFor="v-own">
            <Select id="v-own" value={f.ownership ?? "proprio"} onChange={(e) => set("ownership", e.target.value)}>
              <option value="proprio">Próprio (comprado pela loja)</option>
              <option value="consignado" disabled={!has("consignacao")}>Consignado{!has("consignacao") ? " (plano Profissional)" : ""}</option>
            </Select>
          </Field>
          {f.ownership === "consignado" ? (
            <>
              <Field label="Como a loja ganha" htmlFor="v-cm" error={errors.consignment_mode}>
                <Select id="v-cm" value={f.consignment_mode ?? ""} onChange={(e) => set("consignment_mode", e.target.value)}>
                  <option value="">Escolha</option>
                  <option value="comissao">Comissão sobre a venda (%)</option>
                  <option value="liquido">Valor líquido garantido ao dono</option>
                </Select>
              </Field>
              {f.consignment_mode === "liquido" ? (
                <Field label="Valor líquido ao dono"><MoneyInput value={f.consignment_value} onChange={(c) => set("consignment_value", c)} /></Field>
              ) : (
                <Field label="Comissão da loja (%)" htmlFor="v-cv">
                  <Input placeholder="8" id="v-cv" inputMode="decimal" value={f.consignment_value ? String(f.consignment_value / 100).replace(".", ",") : ""} onChange={(e) => set("consignment_value", Math.round(Number(e.target.value.replace(",", ".") || 0) * 100))} />
                </Field>
              )}
              <div className="sm:col-span-2"><PessoaPicker label="Dono do veículo" value={f.consignorRef ?? null} onChange={(p) => set("consignorRef", p)} required /></div>
              {errors.consignor && <p className="text-sm text-red">{errors.consignor}</p>}
              <Field label="Consignado até" htmlFor="v-cu"><Input id="v-cu" type="date" value={f.consignment_until ?? ""} onChange={(e) => set("consignment_until", e.target.value || null)} /></Field>
            </>
          ) : (
            <>
              <Field label="Valor de compra"><MoneyInput value={f.purchase_price_cents} onChange={(c) => set("purchase_price_cents", c)} /></Field>
              <Field label="Data da compra" htmlFor="v-pd"><Input id="v-pd" type="date" value={f.purchase_date ?? ""} onChange={(e) => set("purchase_date", e.target.value || null)} /></Field>
              <div className="sm:col-span-3"><PessoaPicker label="Comprado de" tipo="fornecedor" value={f.supplierRef ?? null} onChange={(p) => set("supplierRef", p)} /></div>
            </>
          )}
          <Field label="Preço anunciado"><MoneyInput value={f.price_cents} onChange={(c) => set("price_cents", c)} /></Field>
          <Field label="Preço mínimo (gerente)"><MoneyInput value={f.min_price_cents} onChange={(c) => set("min_price_cents", c)} /></Field>
          {text("location", "Localização / pátio")}
        </div>
        <Field label="Descrição para o anúncio" htmlFor="v-desc">
          <Textarea id="v-desc" rows={3} value={f.descricao ?? ""} onChange={(e) => set("descricao", e.target.value)} placeholder="Revisões em dia, pneus novos, único dono…" />
        </Field>
        {has("vitrine") && (
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-brand" checked={!!f.published} onChange={(e) => set("published", e.target.checked)} /> Publicar no site da loja</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-brand" checked={!!f.featured} onChange={(e) => set("featured", e.target.checked)} /> Destaque</label>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button type="submit" loading={save.isPending}>Salvar</Button>
        </div>
      </form>
      <FipePicker
        open={fipeOpen}
        onOpenChange={setFipeOpen}
        kind={f.kind ?? "carro"}
        onPick={(r) => setF((x) => ({ ...x, marca: x.marca || r.brand, modelo: x.modelo || r.model, ano_modelo: x.ano_modelo || r.model_year, fipe_code: r.code, fipe_price_cents: r.price_cents, fipe_reference: r.reference, combustivel: x.combustivel || r.fuel }))}
      />
    </Modal>
  );
}

type Opt = { code: string; name: string };

export function FipePicker({ open, onOpenChange, kind, onPick }: { open: boolean; onOpenChange: (v: boolean) => void; kind: string; onPick: (r: any) => void }) {
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const brands = useQuery({ queryKey: ["fipe", kind], queryFn: () => api<Opt[]>(`/estoque/fipe/${kind}/marcas`), enabled: open, staleTime: Infinity });
  const models = useQuery({ queryKey: ["fipe", kind, brand], queryFn: () => api<Opt[]>(`/estoque/fipe/${kind}/marcas/${brand}/modelos`), enabled: open && !!brand, staleTime: Infinity });
  const years = useQuery({ queryKey: ["fipe", kind, brand, model], queryFn: () => api<Opt[]>(`/estoque/fipe/${kind}/marcas/${brand}/modelos/${model}/anos`), enabled: open && !!model, staleTime: Infinity });
  const price = useQuery({ queryKey: ["fipe", kind, brand, model, year], queryFn: () => api<any>(`/estoque/fipe/${kind}/marcas/${brand}/modelos/${model}/anos/${year}`), enabled: open && !!year });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Tabela FIPE" description="Consulta gratuita, sem custo de franquia.">
      <div className="space-y-3">
        <Field label="Marca" htmlFor="f-b"><Select id="f-b" value={brand} onChange={(e) => { setBrand(e.target.value); setModel(""); setYear(""); }}><option value="">{brands.isLoading ? "Carregando…" : "Escolha"}</option>{brands.data?.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}</Select></Field>
        <Field label="Modelo" htmlFor="f-m"><Select id="f-m" value={model} disabled={!brand} onChange={(e) => { setModel(e.target.value); setYear(""); }}><option value="">Escolha</option>{models.data?.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}</Select></Field>
        <Field label="Ano" htmlFor="f-y"><Select id="f-y" value={year} disabled={!model} onChange={(e) => setYear(e.target.value)}><option value="">Escolha</option>{years.data?.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}</Select></Field>
        {price.data && (
          <div className="flex items-center justify-between rounded-lg bg-pale p-3">
            <div>
              <p className="text-lg font-semibold">{money(price.data.price_cents)}</p>
              <p className="text-xs text-muted">{price.data.model} · {price.data.code} · {price.data.reference}</p>
            </div>
            <Button onClick={() => { onPick(price.data); onOpenChange(false); }}>Usar este valor</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}

// --- ficha do veículo ----------------------------------------------------------------------------

export function VeiculoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { organization, can } = useAuth();
  const { has } = useBilling();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useTab("resumo");
  const q = useQuery({ queryKey: ["veiculo", id], queryFn: () => api<Vehicle>(`/estoque/veiculos/${id}`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["veiculo", id] });
    qc.invalidateQueries({ queryKey: ["veiculos"] });
  };
  const status = useMutation({
    mutationFn: (s: string) => api(`/estoque/veiculos/${id}/status`, { body: { status: s } }),
    onSuccess: () => { toast.success("Situação atualizada"); refresh(); },
    onError: (e) => handleApiError(e),
  });
  if (q.isLoading) return <Spinner />;
  const v = q.data;
  if (!v) return <Empty title="Veículo não encontrado" />;
  const manage = can("estoque.manage");
  const tabs: [string, string][] = [["resumo", "Resumo"], ["fotos", `Fotos (${v.photos.length})`], ["custos", `Custos (${v.costs.length})`], ["documentos", "Documentos"], ["renave", "RENAVE"]];
  if (has("vitrine")) tabs.push(["site", "Site"]);
  return (
    <>
      <Link href="/veiculos" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Veículos</Link>
      <PageHeader
        title={`${v.marca} ${v.modelo}`}
        description={[v.versao, v.ano_fabricacao && `${v.ano_fabricacao}/${v.ano_modelo}`, v.placa && plate(v.placa), v.km != null && `${v.km.toLocaleString("pt-BR")} km`].filter(Boolean).join(" · ")}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[v.status]}>{v.status_display}</Badge>
            {manage && v.status === "preparacao" && <Button size="sm" variant="secondary" onClick={() => status.mutate("disponivel")}>Liberar para venda</Button>}
            {manage && v.status === "disponivel" && <Button size="sm" variant="ghost" onClick={() => status.mutate("preparacao")}>Voltar para preparação</Button>}
            {manage && v.ownership === "consignado" && ["disponivel", "preparacao"].includes(v.status) && <Button size="sm" variant="ghost" onClick={() => void ask("Devolver o carro ao dono?").then((ok) => ok && status.mutate("devolvido"))}>Devolver ao dono</Button>}
            {can("vendas.operate") && ["disponivel", "preparacao", "reservado"].includes(v.status) && <Link href={`/vendas/nova?veiculo=${v.id}`}><Button size="sm">Vender</Button></Link>}
            {manage && <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>Editar</Button>}
          </div>
        }
      />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "resumo" && <Resumo v={v} />}
      {tab === "fotos" && <Fotos v={v} manage={manage} onChange={refresh} />}
      {tab === "custos" && (has("custos") ? <Custos v={v} manage={manage} onChange={refresh} /> : <LockedPanel feature="custos" title="Custos por veículo" />)}
      {tab === "documentos" && <Documentos v={v} manage={manage} onChange={refresh} />}
      {tab === "renave" && <RenaveTab v={v} onChange={refresh} />}
      {tab === "site" && <SiteTab v={v} manage={manage} />}
      <VehicleForm open={editing} onOpenChange={setEditing} vehicle={v} />
      {has("multiloja") && manage && <TransferBox v={v} orgId={organization?.id} />}
    </>
  );
}

function Resumo({ v }: { v: Vehicle }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        {v.photos[0] && <img src={v.photos[0].url} alt="" className="aspect-[16/9] w-full rounded-xl object-cover" />}
        <Card title="Dados do veículo">
          <div className="grid gap-x-8 sm:grid-cols-2">
            <KV label="Cor">{v.cor || "—"}</KV>
            <KV label="Combustível">{v.combustivel || "—"}</KV>
            <KV label="Câmbio">{v.cambio || "—"}</KV>
            <KV label="RENAVAM">{v.renavam || "—"}</KV>
            <KV label="Chassi">{v.chassi || "—"}</KV>
            <KV label="Localização">{v.location || "—"}</KV>
            <KV label="Entrada no estoque">{date(v.entry_date)}</KV>
            <KV label="Código FIPE">{v.fipe_code || "—"}</KV>
          </div>
          {v.opcionais.length > 0 && <p className="mt-3 text-sm text-muted">{v.opcionais.join(" · ")}</p>}
          {v.descricao && <p className="mt-3 text-sm whitespace-pre-line">{v.descricao}</p>}
        </Card>
      </div>
      <Card title="Números">
        <KV label="Preço anunciado"><Money cents={v.price_cents || null} /></KV>
        <KV label="Preço mínimo"><Money cents={v.min_price_cents || null} /></KV>
        <KV label="FIPE"><Money cents={v.fipe_price_cents} /></KV>
        <div className="my-2 border-t border-line" />
        {v.ownership === "consignado" ? (
          <>
            <KV label="Dono (consignado)">{v.consignor_name}</KV>
            <KV label="Repasse ao dono"><Money cents={v.summary.consignor_payout_cents} /></KV>
          </>
        ) : (
          <KV label="Compra"><Money cents={v.purchase_price_cents} /></KV>
        )}
        <KV label="Custos de preparação"><Money cents={v.summary.costs_cents} /></KV>
        <KV label="Custo total"><Money cents={v.summary.total_cost_cents} /></KV>
        <div className="my-2 border-t border-line" />
        <KV label="Lucro previsto"><Profit cents={v.summary.expected_profit_cents} /></KV>
        <KV label="Dias em estoque">{v.summary.days_in_stock ?? "—"}</KV>
      </Card>
    </div>
  );
}

function Fotos({ v, manage, onChange }: { v: Vehicle; manage: boolean; onChange: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (files: FileList) => {
      const fd = new FormData();
      Array.from(files).forEach((f) => fd.append("files", f));
      return api(`/estoque/veiculos/${v.id}/photos`, { form: fd });
    },
    onSuccess: () => { toast.success("Fotos enviadas"); onChange(); },
    onError: (e) => handleApiError(e),
  });
  const remove = useMutation({ mutationFn: (pid: string) => api(`/estoque/veiculos/${v.id}/photos/${pid}`, { method: "DELETE" }), onSuccess: onChange, onError: (e) => handleApiError(e) });
  const cover = useMutation({
    mutationFn: (pid: string) => api(`/estoque/veiculos/${v.id}/photos/reorder`, { body: { order: [pid, ...v.photos.map((p) => p.id).filter((x) => x !== pid)] } }),
    onSuccess: () => { toast.success("Capa definida"); onChange(); },
  });
  return (
    <Card title="Fotos" description="A primeira foto é a capa no site e nos portais. Até 40 fotos." action={manage && (
      <>
        <input ref={input} type="file" accept="image/*" multiple capture="environment" className="hidden" onChange={(e) => e.target.files?.length && upload.mutate(e.target.files)} />
        <Button size="sm" onClick={() => input.current?.click()} loading={upload.isPending}><Camera className="size-4" /> Adicionar fotos</Button>
      </>
    )}>
      {!v.photos.length ? (
        <Empty title="Sem fotos ainda" icon={<Camera />}>Carros com fotos vendem mais rápido. Tire pelo celular direto do pátio.</Empty>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {v.photos.map((p, i) => (
            <div key={p.id} className="group relative overflow-hidden rounded-lg border border-line">
              <img src={p.url} alt="" className="aspect-[4/3] w-full object-cover" loading="lazy" />
              {i === 0 && <span className="absolute top-2 left-2 rounded bg-graphite/80 px-1.5 py-0.5 text-[11px] text-white">Capa</span>}
              {manage && (
                <div className="absolute inset-x-0 bottom-0 flex justify-between bg-graphite/70 p-1.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                  {i !== 0 ? <button className="text-xs text-white" onClick={() => cover.mutate(p.id)}>Usar como capa</button> : <span />}
                  <button className="text-white" aria-label="Apagar foto" onClick={() => void ask("Apagar esta foto?").then((ok) => ok && remove.mutate(p.id))}><Trash2 className="size-4" /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

const COST_CATEGORIES: [string, string][] = [["mecanica", "Mecânica"], ["funilaria", "Funilaria e pintura"], ["estetica", "Estética e higienização"], ["pneus", "Pneus"], ["documentacao", "Documentação e taxas"], ["despachante", "Despachante"], ["transporte", "Transporte / guincho"], ["comissao", "Comissão de compra"], ["outros", "Outros"]];

function Custos({ v, manage, onChange }: { v: Vehicle; manage: boolean; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ category: "mecanica", description: "", amount_cents: 0, date: new Date().toISOString().slice(0, 10), paid: false, supplier: null as any });
  const add = useMutation({
    mutationFn: () => api(`/estoque/veiculos/${v.id}/costs`, { body: { ...f, supplier: f.supplier?.id ?? null } }),
    onSuccess: () => { toast.success("Custo lançado"); setOpen(false); setF({ ...f, description: "", amount_cents: 0 }); onChange(); },
    onError: (e) => handleApiError(e),
  });
  const remove = useMutation({ mutationFn: (cid: string) => api(`/estoque/veiculos/${v.id}/costs/${cid}`, { method: "DELETE" }), onSuccess: onChange, onError: (e) => handleApiError(e) });
  return (
    <Card title="Custos de preparação" description="Cada custo entra no lucro do carro e vira conta a pagar no financeiro." action={manage && <Button size="sm" onClick={() => setOpen(true)}><Plus className="size-4" /> Lançar custo</Button>}>
      {!v.costs.length ? <Empty title="Nenhum custo lançado" /> : (
        <Table head={["Data", "Categoria", "Descrição", "Fornecedor", "Valor", "Financeiro", ""]}>
          {v.costs.map((c) => (
            <tr key={c.id}>
              <td className="px-5 py-3 text-muted">{date(c.date)}</td>
              <td className="px-5 py-3">{c.category_display}</td>
              <td className="px-5 py-3">{c.description}</td>
              <td className="px-5 py-3 text-muted">{c.supplier_name ?? "—"}</td>
              <td className="px-5 py-3 font-medium"><Money cents={c.amount_cents} /></td>
              <td className="px-5 py-3">{c.payable_status && <Badge tone={c.payable_status === "pago" ? "green" : c.payable_status === "vencido" ? "red" : "yellow"}>{c.payable_status}</Badge>}</td>
              <td className="px-5 py-3 text-right">{manage && <button aria-label="Remover custo" className="text-muted hover:text-red" onClick={() => void ask("Remover este custo?").then((ok) => ok && remove.mutate(c.id))}><Trash2 className="size-4" /></button>}</td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Lançar custo">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Categoria" htmlFor="c-cat"><Select id="c-cat" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{COST_CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Descrição" htmlFor="c-desc"><Input id="c-desc" required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Troca de pastilhas" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Valor"><MoneyInput value={f.amount_cents} onChange={(c) => setF({ ...f, amount_cents: c })} /></Field>
            <Field label="Data" htmlFor="c-date"><Input id="c-date" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          </div>
          <PessoaPicker label="Fornecedor" tipo="fornecedor" value={f.supplier} onChange={(p) => setF({ ...f, supplier: p })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-brand" checked={f.paid} onChange={(e) => setF({ ...f, paid: e.target.checked })} /> Já foi pago</label>
          <Button type="submit" className="w-full" loading={add.isPending}>Lançar</Button>
        </form>
      </Modal>
    </Card>
  );
}

function Documentos({ v, manage, onChange }: { v: Vehicle; manage: boolean; onChange: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState("crlv");
  const up = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", kind);
      return api(`/estoque/veiculos/${v.id}/documents`, { form: fd });
    },
    onSuccess: () => { toast.success("Documento anexado"); onChange(); },
    onError: (e) => handleApiError(e),
  });
  const remove = useMutation({ mutationFn: (did: string) => api(`/estoque/veiculos/${v.id}/documents/${did}`, { method: "DELETE" }), onSuccess: onChange });
  return (
    <Card title="Documentos do veículo" description="CRLV, laudo cautelar, vistoria. Ficam guardados com acesso só da equipe." action={manage && (
      <div className="flex gap-2">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="h-8 w-36">
          <option value="crlv">CRLV</option><option value="atpv">ATPV / recibo</option><option value="laudo">Laudo cautelar</option><option value="vistoria">Vistoria</option><option value="nota">Nota fiscal</option><option value="outro">Outro</option>
        </Select>
        <input ref={input} type="file" accept="application/pdf,image/*" className="hidden" onChange={(e) => e.target.files?.[0] && up.mutate(e.target.files[0])} />
        <Button size="sm" onClick={() => input.current?.click()} loading={up.isPending}><FileUp className="size-4" /> Anexar</Button>
      </div>
    )}>
      {!v.documents.length ? <Empty title="Nenhum documento anexado" /> : (
        <ul className="divide-y divide-line">
          {v.documents.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2.5 text-sm">
              <button className="text-left font-medium text-brand" onClick={() => download(d.url.replace(/^\/api/, ""), true)}>{d.name}</button>
              <span className="flex items-center gap-3 text-muted">{d.kind_display} · {date(d.created_at)}{manage && <button aria-label="Remover" className="hover:text-red" onClick={() => void ask("Remover documento?").then((ok) => ok && remove.mutate(d.id))}><Trash2 className="size-4" /></button>}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function RenaveTab({ v, onChange }: { v: Vehicle; onChange: () => void }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString();
  const [f, setF] = useState({ renavam: v.renavam, crv: "", codigo_seguranca_crv: "", tipo_crv: "DIGITAL", km: v.km ?? 0, data_hora_km: local.slice(0, 16), data_compra: v.purchase_date ?? local.slice(0, 10), tipo_operacao: "compra_veiculo", vendedor_documento: "", valor_compra_cents: v.purchase_price_cents });
  const entry = useMutation({
    mutationFn: () => api(`/estoque/veiculos/${v.id}/renave-entry`, { body: f }),
    onSuccess: () => { toast.success("Entrada enviada ao RENAVE"); setOpen(false); onChange(); },
    onError: (e) => handleApiError(e),
  });
  if (v.renave) {
    return (
      <Card title="RENAVE">
        <p className="text-sm">Situação no RENAVE: <Badge tone={v.renave.state === "CONFIRMADO" ? "green" : v.renave.state === "NEGADO" ? "red" : "yellow"}>{v.renave.state_display}</Badge></p>
        <p className="mt-3 text-sm text-muted">A saída é feita pela venda, depois de fechada. Documentos e cancelamentos ficam em <Link href={`/estoque/${v.renave.id}`} className="font-medium text-brand">Estoque RENAVE</Link>.</p>
      </Card>
    );
  }
  return (
    <Card title="RENAVE" description="Registre a entrada do carro no Registro Nacional de Veículos em Estoque. Cada operação custa R$ 30,00.">
      {!v.placa ? <p className="text-sm text-muted">Cadastre a placa do veículo para dar entrada.</p> : can("renave.operate") ? <Button onClick={() => setOpen(true)}><Upload className="size-4" /> Dar entrada no RENAVE</Button> : <p className="text-sm text-muted">Seu perfil não opera o RENAVE.</p>}
      <Modal open={open} onOpenChange={setOpen} title="Entrada no RENAVE" description={`${v.title} · ${plate(v.placa)}`} wide>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); entry.mutate(); }}>
          <Field label="Tipo de entrada" htmlFor="r-op"><Select id="r-op" value={f.tipo_operacao} onChange={(e) => setF({ ...f, tipo_operacao: e.target.value })}><option value="compra_veiculo">Compra de terceiro</option><option value="entrada_veiculo_proprio">Veículo próprio da loja</option></Select></Field>
          <Field label="RENAVAM" htmlFor="r-rv"><Input placeholder="11 dígitos" id="r-rv" required value={f.renavam} onChange={(e) => setF({ ...f, renavam: e.target.value })} /></Field>
          <Field label="Tipo de CRV" htmlFor="r-tc"><Select id="r-tc" value={f.tipo_crv} onChange={(e) => setF({ ...f, tipo_crv: e.target.value })}><option value="DIGITAL">Digital (CRV-e)</option><option value="FISICO">Físico</option></Select></Field>
          <Field label="Número do CRV" htmlFor="r-crv"><Input placeholder="Número do CRV" id="r-crv" required value={f.crv} onChange={(e) => setF({ ...f, crv: e.target.value })} /></Field>
          <Field label="Código de segurança do CRV" htmlFor="r-cs"><Input placeholder="Código de segurança do CRV" id="r-cs" required value={f.codigo_seguranca_crv} onChange={(e) => setF({ ...f, codigo_seguranca_crv: e.target.value })} /></Field>
          <Field label="Quilometragem" htmlFor="r-km"><Input placeholder="45000" id="r-km" inputMode="numeric" value={f.km} onChange={(e) => setF({ ...f, km: Number(e.target.value.replace(/\D/g, "") || 0) })} /></Field>
          <Field label="Data e hora da medição" htmlFor="r-dk"><Input id="r-dk" type="datetime-local" value={f.data_hora_km} onChange={(e) => setF({ ...f, data_hora_km: e.target.value })} /></Field>
          <Field label="Data da compra" htmlFor="r-dc"><Input id="r-dc" type="date" value={f.data_compra} onChange={(e) => setF({ ...f, data_compra: e.target.value })} /></Field>
          {f.tipo_operacao === "compra_veiculo" && (
            <>
              <Field label="CPF/CNPJ do vendedor" htmlFor="r-vd"><Input placeholder="000.000.000-00" id="r-vd" required value={f.vendedor_documento} onChange={(e) => setF({ ...f, vendedor_documento: e.target.value })} /></Field>
              <Field label="Valor da compra"><MoneyInput value={f.valor_compra_cents} onChange={(c) => setF({ ...f, valor_compra_cents: c })} /></Field>
            </>
          )}
          <Button type="submit" className="sm:col-span-2" loading={entry.isPending}>Enviar ao RENAVE (R$ 30,00)</Button>
        </form>
      </Modal>
    </Card>
  );
}

function SiteTab({ v, manage }: { v: Vehicle; manage: boolean }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: (published: boolean) => api(`/estoque/veiculos/${v.id}`, { method: "PATCH", body: { published } }),
    onSuccess: (_, published) => {
      toast.success(published ? "Publicado no site" : "Retirado do site");
      qc.invalidateQueries({ queryKey: ["veiculo", v.id] });
      qc.invalidateQueries({ queryKey: ["veiculos"] });
    },
    onError: (e) => handleApiError(e),
  });
  const sellable = ["disponivel", "reservado"].includes(v.status);
  return (
    <Card title="Site da loja" description="Carros publicados aparecem no site da loja e no feed de estoque (link em Site da loja).">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          Situação: <strong>{v.published ? "publicado" : "não publicado"}</strong>
          {v.published && !sellable && <span className="block text-xs text-muted">Só aparece no site quando estiver disponível ou reservado.</span>}
        </p>
        {manage && (
          <Button size="sm" variant={v.published ? "secondary" : "primary"} loading={toggle.isPending} onClick={() => toggle.mutate(!v.published)}>
            {v.published ? "Retirar do site" : "Publicar no site"}
          </Button>
        )}
      </div>
    </Card>
  );
}

function TransferBox({ v, orgId }: { v: Vehicle; orgId?: string }) {
  const [target, setTarget] = useState("");
  const [, navigate] = useLocation();
  const stores = useQuery({ queryKey: ["lojas", orgId], queryFn: () => api<{ stores: { id: string; name: string; is_member: boolean }[] }>("/lojas/") });
  const others = stores.data?.stores.filter((s) => s.id !== orgId && s.is_member) ?? [];
  const move = useMutation({
    mutationFn: () => api("/lojas/transferir", { body: { vehicle: v.id, target } }),
    onSuccess: () => { toast.success("Veículo transferido"); navigate("/veiculos"); },
    onError: (e) => handleApiError(e),
  });
  if (!others.length || !["preparacao", "disponivel"].includes(v.status)) return null;
  return (
    <Card title="Transferir para outra loja" className="mt-6">
      <div className="flex flex-wrap gap-2">
        <Select value={target} onChange={(e) => setTarget(e.target.value)} className="w-64"><option value="">Escolha a loja</option>{others.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
        <Button variant="secondary" disabled={!target} loading={move.isPending} onClick={() => void ask("Transferir o veículo?").then((ok) => ok && move.mutate())}>Transferir</Button>
      </div>
    </Card>
  );
}
