import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Car, Download, FileSignature, LogIn, LogOut, Plus, RefreshCw, Undo2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link, useLocation, useParams } from "wouter";

import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api, download, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, document, maskDocument, maskMoney, money, parseMoney, plate } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { lookupAddress, maskCep } from "@/lib/lookup";
import { ask } from "@/components/confirm";

type Vehicle = {
  id: string;
  id_estoque: number | null;
  protocolo: string;
  placa: string;
  renavam: string;
  state: string;
  state_display: string;
  situacao: string;
  marca_modelo: string;
  client_name: string | null;
  owner_document: string;
  entry_date: string | null;
  entry_value_cents: number | null;
  entry_km: number | null;
  exit_date: string | null;
  exit_value_cents: number | null;
  last_synced_at: string | null;
  created_at: string;
  operations?: { id: string; kind_display: string; success: boolean; message: string; price_cents: number; user_name: string | null; created_at: string }[];
};

const STATE_TONE: Record<string, "green" | "yellow" | "red" | "blue" | "gray"> = {
  CONFIRMADO: "green",
  SOLICITADO: "yellow",
  NEGADO: "red",
  FINALIZADO: "blue",
  TRANSFERIDO: "blue",
  CANCELADO: "gray",
};

export function useClients() {
  const { organization } = useAuth();
  return useQuery({
    queryKey: ["clients-choices", organization?.id],
    queryFn: () => api<{ id: string; name: string; document: string }[]>("/organizations/clients/choices"),
    staleTime: 60_000,
  });
}

function usePrices() {
  const { organization } = useAuth();
  return useQuery({ queryKey: ["prices", organization?.id], queryFn: () => api<{ code: string; price_cents: number }[]>("/wallet/prices"), staleTime: 5 * 60_000 });
}

function priceOf(prices: { code: string; price_cents: number }[] | undefined, code: string) {
  return prices?.find((p) => p.code === code)?.price_cents;
}

type EntradaForm = {
  client_id: string;
  tipo_operacao: "compra_veiculo" | "entrada_veiculo_proprio";
  placa: string;
  renavam: string;
  crv: string;
  codigo_seguranca_crv: string;
  tipo_crv: string;
  km: string;
  data_hora_km: string;
  data_compra: string;
  vendedor_tipo: "fisica" | "juridica";
  vendedor_documento: string;
  valor_compra: string;
};

function EntradaModal({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const clients = useClients();
  const prices = usePrices();
  const qc = useQueryClient();
  const [, navigate] = useLocation();
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString();
  const form = useForm<EntradaForm>({
    defaultValues: { client_id: "", tipo_operacao: "compra_veiculo", tipo_crv: "DIGITAL", vendedor_tipo: "fisica", data_compra: local.slice(0, 10), data_hora_km: local.slice(0, 16) },
  });
  const { register, watch, setValue, formState } = form;
  const e = formState.errors;
  const compra = watch("tipo_operacao") === "compra_veiculo";

  const [aptidao, setAptidao] = useState<Record<string, unknown> | null>(null);
  const checkAptidao = async () => {
    const v = form.getValues();
    try {
      const r = await api("/renave/aptidao", { body: { client_id: v.client_id || null, placa: v.placa, renavam: v.renavam, crv: v.crv, tipo_crv: v.tipo_crv } });
      setAptidao(r.veiculo);
      toast.success("Consulta de aptidão realizada.");
    } catch (err) {
      handleApiError(err, form.setError);
    }
  };

  const submit = form.handleSubmit(async (v) => {
    const body: Record<string, unknown> = {
      client_id: v.client_id || null,
      tipo_operacao: v.tipo_operacao,
      placa: v.placa,
      renavam: v.renavam,
      crv: v.crv,
      codigo_seguranca_crv: v.codigo_seguranca_crv,
      tipo_crv: v.tipo_crv,
      km: Number(v.km.replace(/\D/g, "")),
      data_hora_km: new Date(v.data_hora_km).toISOString(),
      data_compra: v.data_compra,
    };
    if (compra) Object.assign(body, { vendedor_tipo: v.vendedor_tipo, vendedor_documento: v.vendedor_documento, valor_compra_cents: parseMoney(v.valor_compra) });
    try {
      const vehicle = await api<Vehicle>("/renave/stock", { body });
      toast.success("Entrada registrada no RENAVE.");
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
      onOpenChange(false);
      navigate(`/estoque/${vehicle.id}`);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Registrar entrada no estoque" description="A entrada é registrada no RENAVE com o certificado digital do estabelecimento." wide>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          {!!clients.data?.length && (
          <Field label="Estabelecimento" htmlFor="client_id">
            <Select id="client_id" {...register("client_id")}>
              <option value="">Minha empresa</option>
              {clients.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} — {document(c.document)}
                </option>
              ))}
            </Select>
          </Field>
          )}
          <Field label="Tipo de entrada" htmlFor="tipo_operacao">
            <Select id="tipo_operacao" {...register("tipo_operacao")}>
              <option value="compra_veiculo">Compra de terceiro</option>
              <option value="entrada_veiculo_proprio">Veículo próprio</option>
            </Select>
          </Field>
        </div>

        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-semibold">Veículo e CRV</legend>
          <Field label="Placa" htmlFor="placa" error={e.placa?.message}>
            <Input id="placa" placeholder="ABC1D23" {...register("placa", { required: "Obrigatório", onChange: (ev) => setValue("placa", plate(ev.target.value)) })} className="font-mono uppercase" />
          </Field>
          <Field label="RENAVAM" htmlFor="renavam" error={e.renavam?.message}>
            <Input id="renavam" placeholder="00000000000" inputMode="numeric" maxLength={11} {...register("renavam", { required: "Obrigatório" })} />
          </Field>
          <Field label="Tipo de CRV" htmlFor="tipo_crv">
            <Select id="tipo_crv" {...register("tipo_crv")}>
              {["DIGITAL", "VERDE", "BRANCO", "AZUL"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </Select>
          </Field>
          <Field label="Número do CRV" htmlFor="crv" error={e.crv?.message}>
            <Input id="crv" placeholder="Número impresso no CRV" {...register("crv", { required: "Obrigatório" })} />
          </Field>
          <Field label="Código de segurança do CRV" htmlFor="csc" error={e.codigo_seguranca_crv?.message}>
            <Input id="csc" placeholder="Código de segurança do CRV" autoComplete="off" {...register("codigo_seguranca_crv", { required: "Obrigatório" })} />
          </Field>
          <div className="flex items-end">
            <Button type="button" variant="secondary" className="w-full" onClick={checkAptidao}>
              Consultar aptidão
            </Button>
          </div>
          {aptidao && (
            <pre className="max-h-40 overflow-auto rounded-lg bg-pale p-3 text-xs sm:col-span-3">{JSON.stringify(aptidao, null, 2)}</pre>
          )}
        </fieldset>

        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-semibold">Entrada</legend>
          <Field label={compra ? "Data da compra" : "Data de entrada"} htmlFor="data_compra">
            <Input id="data_compra" type="date" {...register("data_compra", { required: true })} />
          </Field>
          <Field label="Quilometragem" htmlFor="km" error={e.km?.message}>
            <Input id="km" placeholder="Ex.: 54.000" inputMode="numeric" {...register("km", { required: "Obrigatório" })} />
          </Field>
          <Field label="Leitura do hodômetro" htmlFor="data_hora_km">
            <Input id="data_hora_km" type="datetime-local" {...register("data_hora_km", { required: true })} />
          </Field>
          {compra && (
            <>
              <Field label="Vendedor" htmlFor="vendedor_tipo">
                <Select id="vendedor_tipo" {...register("vendedor_tipo")}>
                  <option value="fisica">Pessoa física</option>
                  <option value="juridica">Pessoa jurídica</option>
                </Select>
              </Field>
              <Field label={watch("vendedor_tipo") === "fisica" ? "CPF do vendedor" : "CNPJ do vendedor"} htmlFor="vendedor_documento" error={e.vendedor_documento?.message}>
                <Input id="vendedor_documento" placeholder="CPF ou CNPJ do vendedor" {...register("vendedor_documento", { required: "Obrigatório", onChange: (ev) => setValue("vendedor_documento", maskDocument(ev.target.value)) })} />
              </Field>
              <Field label="Valor da compra (R$)" htmlFor="valor_compra" error={e.valor_compra?.message}>
                <Input id="valor_compra" placeholder="0,00" inputMode="decimal" {...register("valor_compra", { required: "Obrigatório", onChange: (ev) => setValue("valor_compra", maskMoney(ev.target.value)) })} />
              </Field>
            </>
          )}
        </fieldset>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-pale px-4 py-3">
          <span className="text-sm text-muted">
            Tarifa da entrada: <strong className="text-ink">{money(priceOf(prices.data, "renave.entrada"))}</strong> (estornada se o RENAVE recusar)
          </span>
          <Button type="submit" loading={formState.isSubmitting}>
            <LogIn className="size-4" /> Registrar entrada
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function EstoquePage() {
  const { organization, can } = useAuth();
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [openEntrada, setOpenEntrada] = useState(false);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["stock", organization?.id, state, search, page],
    queryFn: () => api<Page<Vehicle>>("/renave/stock", { params: { state, search, page } }),
    placeholderData: (prev) => prev,
  });
  const sync = useMutation({
    mutationFn: () => api<{ updated: number; message: string }>("/renave/stock/sync", { method: "POST", body: {} }),
    onSuccess: (r) => {
      toast.success(r.message || `${r.updated} veículo(s) sincronizado(s).`);
      qc.invalidateQueries({ queryKey: ["stock"] });
    },
    onError: (e) => handleApiError(e),
  });

  return (
    <>
      <PageHeader
        title="Estoque RENAVE"
        description="Entradas, saídas e documentos dos veículos no Registro Nacional de Veículos em Estoque."
        action={
          can("renave.operate") && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => sync.mutate()} loading={sync.isPending}>
                <RefreshCw className="size-4" /> Sincronizar
              </Button>
              <Button onClick={() => setOpenEntrada(true)}>
                <Plus className="size-4" /> Nova entrada
              </Button>
            </div>
          )
        }
      />
      <Card
        action={
          <div className="flex flex-wrap gap-2">
            <Input placeholder="Buscar placa…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className="h-9 w-44" />
            <Select value={state} onChange={(e) => { setState(e.target.value); setPage(1); }} className="h-9 w-44">
              <option value="">Todos os status</option>
              <option value="CONFIRMADO">Em estoque</option>
              <option value="SOLICITADO">Entrada solicitada</option>
              <option value="FINALIZADO">Vendidos</option>
              <option value="TRANSFERIDO">Transferidos</option>
              <option value="NEGADO">Negados</option>
            </Select>
          </div>
        }
        title="Veículos"
      >
        {q.isLoading ? (
          <Spinner />
        ) : !q.data?.results.length ? (
          <Empty title="Nenhum veículo no estoque" icon={<Car />}>
            Registre a primeira entrada ou sincronize com o RENAVE.
          </Empty>
        ) : (
          <>
            <Table head={["Placa", "Veículo", "Estabelecimento", "Status", "Entrada", "Valor", "ID RENAVE"]}>
              {q.data.results.map((v) => (
                <tr key={v.id} className="hover:bg-pale/60">
                  <td className="px-5 py-3">
                    <Link href={`/estoque/${v.id}`} className="font-mono font-semibold text-brand hover:underline">
                      {plate(v.placa)}
                    </Link>
                  </td>
                  <td className="px-5 py-3">{v.marca_modelo || "—"}</td>
                  <td className="px-5 py-3 text-muted">{v.client_name ?? "Própria"}</td>
                  <td className="px-5 py-3">
                    <Badge tone={STATE_TONE[v.state]}>{v.state_display}</Badge>
                  </td>
                  <td className="px-5 py-3">{date(v.entry_date)}</td>
                  <td className="px-5 py-3">{money(v.entry_value_cents)}</td>
                  <td className="px-5 py-3 font-mono text-muted">{v.id_estoque ?? "aguardando"}</td>
                </tr>
              ))}
            </Table>
            <div className="mt-4 flex items-center justify-between text-sm text-muted">
              <span>{q.data.count} veículo(s)</span>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" disabled={!q.data.previous} onClick={() => setPage((p) => p - 1)}>
                  Anterior
                </Button>
                <Button size="sm" variant="secondary" disabled={!q.data.next} onClick={() => setPage((p) => p + 1)}>
                  Próxima
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
      <EntradaModal open={openEntrada} onOpenChange={setOpenEntrada} />
    </>
  );
}

// --- Detalhe -----------------------------------------------------------------------

type SaidaForm = {
  tipo_transferencia: string;
  data_venda: string;
  cod_seguranca_crv: string;
  comprador_nome: string;
  comprador_documento: string;
  valor_venda: string;
  municipio: string;
  email: string;
  cep: string;
  logradouro: string;
  numero: string;
  bairro: string;
};

function SaidaModal({ vehicle, open, onOpenChange }: { vehicle: Vehicle; open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const prices = usePrices();
  const form = useForm<SaidaForm>({ defaultValues: { tipo_transferencia: "1", data_venda: new Date().toISOString().slice(0, 10) } });
  const { register, watch, setValue, formState } = form;
  const venda = watch("tipo_transferencia") === "1";
  const e = formState.errors;
  const submit = form.handleSubmit(async (v) => {
    const body: Record<string, unknown> = {
      tipo_transferencia: Number(v.tipo_transferencia),
      data_venda: v.data_venda,
      cod_seguranca_crv: v.cod_seguranca_crv,
      comprador_nome: v.comprador_nome,
      comprador_documento: v.comprador_documento,
    };
    if (venda) Object.assign(body, { valor_venda_cents: parseMoney(v.valor_venda), municipio: v.municipio, email: v.email, cep: v.cep, logradouro: v.logradouro, numero: v.numero, bairro: v.bairro });
    try {
      await api(`/renave/stock/${vehicle.id}/saida`, { body });
      toast.success("Saída registrada no RENAVE.");
      qc.invalidateQueries({ queryKey: ["vehicle", vehicle.id] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
      onOpenChange(false);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title={`Registrar saída — ${plate(vehicle.placa)}`} wide>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Field label="Tipo de saída" htmlFor="tipo">
          <Select id="tipo" {...register("tipo_transferencia")}>
            <option value="1">Venda (comprador pessoa física)</option>
            <option value="2">Transferência entre filiais</option>
            <option value="3">Transferência entre estabelecimentos</option>
          </Select>
        </Field>
        <Field label="Data" htmlFor="data_venda">
          <Input id="data_venda" type="date" {...register("data_venda", { required: true })} />
        </Field>
        <Field label={venda ? "Nome do comprador" : "Razão social do destino"} htmlFor="nome" error={e.comprador_nome?.message}>
          <Input id="nome" placeholder="Nome completo / razão social" {...register("comprador_nome", { required: "Obrigatório" })} />
        </Field>
        <Field label={venda ? "CPF do comprador" : "CNPJ do destino"} htmlFor="doc" error={e.comprador_documento?.message}>
          <Input id="doc" placeholder="CPF ou CNPJ" {...register("comprador_documento", { required: "Obrigatório", onChange: (ev) => setValue("comprador_documento", maskDocument(ev.target.value)) })} />
        </Field>
        <Field label="Código de segurança do CRV" htmlFor="csc" error={e.cod_seguranca_crv?.message}>
          <Input id="csc" placeholder="Código de segurança do CRV" autoComplete="off" {...register("cod_seguranca_crv", { required: "Obrigatório" })} />
        </Field>
        {venda && (
          <>
            <Field label="Valor da venda (R$)" htmlFor="valor" error={(e as any).valor_venda_cents?.message}>
              <Input id="valor" placeholder="0,00" inputMode="decimal" {...register("valor_venda", { required: "Obrigatório", onChange: (ev) => setValue("valor_venda", maskMoney(ev.target.value)) })} />
            </Field>
            <Field label="Código do município do comprador" htmlFor="mun" hint="Código do município do comprador (preenchido pelo CEP)." error={e.municipio?.message}>
              <Input id="mun" placeholder="Preenchido pelo CEP" maxLength={7} {...register("municipio", { required: "Obrigatório" })} />
            </Field>
            <Field label="E-mail do comprador" htmlFor="email">
              <Input id="email" placeholder="comprador@email.com" type="email" {...register("email")} />
            </Field>
            <Field label="CEP" htmlFor="cep" hint="Preenche endereço e município.">
              <Input
                id="cep"
                placeholder="00000-000"
                inputMode="numeric"
                {...register("cep", {
                  onChange: async (ev) => {
                    const v = maskCep(ev.target.value);
                    setValue("cep", v);
                    const a = await lookupAddress(v);
                    if (a) {
                      setValue("logradouro", a.street);
                      setValue("bairro", a.district);
                      setValue("municipio", a.city_ibge);
                    }
                  },
                })}
              />
            </Field>
            <Field label="Logradouro" htmlFor="log">
              <Input id="log" placeholder="Rua, avenida…" {...register("logradouro")} />
            </Field>
            <Field label="Número" htmlFor="num">
              <Input id="num" placeholder="Nº" {...register("numero")} />
            </Field>
            <Field label="Bairro" htmlFor="bairro">
              <Input id="bairro" placeholder="Bairro" {...register("bairro")} />
            </Field>
          </>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-pale px-4 py-3 sm:col-span-2">
          <span className="text-sm text-muted">
            Tarifa: <strong className="text-ink">{money(priceOf(prices.data, "renave.saida"))}</strong>
          </span>
          <Button type="submit" loading={formState.isSubmitting}>
            <LogOut className="size-4" /> Registrar saída
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function NotaModal({ vehicle, open, onOpenChange }: { vehicle: Vehicle; open: boolean; onOpenChange: (v: boolean) => void }) {
  const form = useForm<{ chave: string; evento: string }>({ defaultValues: { evento: vehicle.exit_date ? "VENDA" : "COMPRA" } });
  const submit = form.handleSubmit(async (v) => {
    try {
      await api(`/renave/stock/${vehicle.id}/nota-fiscal`, { body: { chave: v.chave.replace(/\s/g, "").toUpperCase(), evento: v.evento } });
      toast.success("Nota fiscal enviada ao RENAVE.");
      onOpenChange(false);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Enviar nota fiscal ao RENAVE">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Evento" htmlFor="evento">
          <Select id="evento" {...form.register("evento")}>
            <option value="COMPRA">Nota de entrada (compra)</option>
            <option value="VENDA">Nota de saída (venda)</option>
          </Select>
        </Field>
        <Field label="Chave de acesso (44 caracteres)" htmlFor="chave" error={form.formState.errors.chave?.message}>
          <Input id="chave" placeholder="44 caracteres da chave de acesso" className="font-mono" {...form.register("chave", { required: "Obrigatório" })} />
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Enviar
        </Button>
      </form>
    </Modal>
  );
}

function AtpvModal({ vehicle, open, onOpenChange }: { vehicle: Vehicle; open: boolean; onOpenChange: (v: boolean) => void }) {
  const [tipo, setTipo] = useState("cartorio");
  const [file, setFile] = useState<File | null>(null);
  const send = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("tipo_assinatura", tipo);
      fd.append("arquivo", file!);
      return api(`/renave/stock/${vehicle.id}/atpv-assinada`, { form: fd });
    },
    onSuccess: () => {
      toast.success("ATPV-e assinada enviada.");
      onOpenChange(false);
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Enviar ATPV-e assinada">
      <div className="space-y-4">
        <Field label="Tipo de assinatura" htmlFor="tipo">
          <Select id="tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="cartorio">Assinada de próprio punho (PDF/imagem)</option>
            <option value="certificado">Assinatura digital (.p7s)</option>
          </Select>
        </Field>
        <Field label="Arquivo" htmlFor="arq">
          <Input id="arq" type="file" accept={tipo === "cartorio" ? ".pdf,.jpg,.jpeg,.png" : ".p7s"} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="pt-2" />
        </Field>
        <Button className="w-full" disabled={!file} loading={send.isPending} onClick={() => send.mutate()}>
          Enviar
        </Button>
      </div>
    </Modal>
  );
}

export function EstoqueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [modal, setModal] = useState<"saida" | "nota" | "atpv" | null>(null);
  const { data: v, isLoading } = useQuery({
    queryKey: ["vehicle", id],
    queryFn: () => api<Vehicle>(`/renave/stock/${id}`),
    refetchInterval: (q) => (q.state.data && !q.state.data.id_estoque && q.state.data.state === "SOLICITADO" ? 15_000 : false),
  });
  const action = useMutation({
    mutationFn: (path: string) => api<Vehicle>(`/renave/stock/${id}/${path}`, { method: "POST" }),
    onSuccess: (d) => {
      qc.setQueryData(["vehicle", id], d);
      qc.invalidateQueries({ queryKey: ["wallet"] });
      toast.success("Solicitação realizada.");
    },
    onError: (e) => handleApiError(e),
  });

  if (isLoading || !v) return <Spinner />;
  const inStock = v.state === "CONFIRMADO";
  const sold = v.state === "FINALIZADO" || v.state === "TRANSFERIDO";
  const op = can("renave.operate");
  const doc = (kind: string) => download(`/renave/stock/${v.id}/documentos/${kind}`).catch(handleApiError);

  return (
    <div className="space-y-6">
      <Link href="/estoque" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Voltar ao estoque
      </Link>
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl bg-graphite p-6 text-white">
        <div>
          <p className="text-xs font-semibold text-mint">{v.client_name ?? "Estoque próprio"}</p>
          <p className="mt-1 font-display text-4xl font-semibold tracking-wider">{plate(v.placa)}</p>
          <p className="text-sm text-[#a1a1aa]">
            {v.marca_modelo || "Veículo"} · RENAVAM {v.renavam} · ID RENAVE {v.id_estoque ?? "aguardando"}
          </p>
        </div>
        <Badge tone={STATE_TONE[v.state]}>{v.state_display}</Badge>
      </section>

      {op && (
        <div className="flex flex-wrap gap-2">
          {inStock && (
            <Button onClick={() => setModal("saida")}>
              <LogOut className="size-4" /> Registrar saída
            </Button>
          )}
          {inStock && (
            <Link href={`/notas?nova=1&tipo=1&vehicle=${v.id}`}>
              <Button variant="secondary">Emitir NF-e de venda</Button>
            </Link>
          )}
          <Button variant="secondary" onClick={() => setModal("nota")} disabled={!v.id_estoque}>
            Enviar chave de NF-e
          </Button>
          {sold && (
            <Button variant="secondary" onClick={() => setModal("atpv")}>
              <FileSignature className="size-4" /> ATPV-e assinada
            </Button>
          )}
          {inStock && (
            <Button variant="danger" loading={action.isPending} onClick={() => void ask("Cancelar a entrada deste veículo no RENAVE?").then((ok) => ok && action.mutate("cancelar-entrada"))}>
              <Undo2 className="size-4" /> Cancelar entrada
            </Button>
          )}
          {sold && (
            <Button variant="danger" loading={action.isPending} onClick={() => void ask("Cancelar a saída e devolver o veículo ao estoque?").then((ok) => ok && action.mutate("cancelar-saida"))}>
              <Undo2 className="size-4" /> Cancelar saída
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card title="Movimentações">
          {!v.operations?.length ? (
            <Empty title="Sem movimentações registradas" />
          ) : (
            <ol className="space-y-4">
              {v.operations.map((o) => (
                <li key={o.id} className="flex gap-3">
                  <span className={`mt-1.5 size-2.5 shrink-0 rounded-full ${o.success ? "bg-green" : "bg-red"}`} aria-hidden />
                  <div>
                    <p className="font-semibold">
                      {o.kind_display} {!o.success && <Badge tone="red">recusada</Badge>}
                    </p>
                    <p className="text-sm text-muted">
                      {dateTime(o.created_at)} · {o.user_name ?? "sistema"} {o.price_cents > 0 && `· ${money(o.price_cents)}`}
                    </p>
                    {o.message && <p className="text-sm">{o.message}</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Dados">
            <dl className="space-y-2 text-sm">
              {[
                ["Entrada", date(v.entry_date)],
                ["Valor de compra", money(v.entry_value_cents)],
                ["KM na entrada", v.entry_km?.toLocaleString("pt-BR") ?? "—"],
                ["Saída", date(v.exit_date)],
                ["Valor de venda", money(v.exit_value_cents)],
                ["Protocolo", v.protocolo || "—"],
                ["Última sincronização", dateTime(v.last_synced_at)],
              ].map(([k, val]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-line/60 pb-2">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-medium">{val}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card title="Documentos">
            <div className="grid gap-2">
              {[
                ["termo_entrada", "Termo de entrada", !!v.id_estoque],
                ["crlve", "CRLV-e / código de segurança", !!v.id_estoque],
                ["termo_saida", "Termo de saída", sold],
                ["atpv", "ATPV-e (ZIP)", sold],
              ].map(([kind, label, enabled]) => (
                <Button key={kind as string} variant="secondary" size="sm" className="justify-start" disabled={!enabled} onClick={() => doc(kind as string)}>
                  <Download className="size-4" /> {label as string}
                </Button>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {modal === "saida" && <SaidaModal vehicle={v} open onOpenChange={(o) => !o && setModal(null)} />}
      {modal === "nota" && <NotaModal vehicle={v} open onOpenChange={(o) => !o && setModal(null)} />}
      {modal === "atpv" && <AtpvModal vehicle={v} open onOpenChange={(o) => !o && setModal(null)} />}
    </div>
  );
}
