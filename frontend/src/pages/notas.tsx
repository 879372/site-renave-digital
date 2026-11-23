import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, FileText, Plus, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link, useLocation, useParams, useSearch } from "wouter";

import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { LockedPanel } from "@/components/PlanGate";
import { api, cursorOf, download, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBilling } from "@/lib/billing";
import { dateTime, document, maskDocument, maskMoney, money, parseMoney, plate, UFS } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { lookupAddress, maskCep } from "@/lib/lookup";

type Nota = {
  id: string;
  tipo: string;
  tipo_display: string;
  ambiente: string;
  serie: number;
  numero: number;
  status: string;
  status_display: string;
  chave: string;
  protocolo: string;
  cstat: string;
  message: string;
  destinatario_nome: string;
  destinatario_documento: string;
  total_cents: number;
  price_cents: number;
  cce_count: number;
  has_pdf: boolean;
  placa: string | null;
  authorized_at: string | null;
  created_at: string;
};

const TONE: Record<string, "green" | "yellow" | "red" | "gray" | "blue"> = { authorized: "green", queued: "yellow", processing: "yellow", rejected: "red", error: "red", canceled: "gray" };

function NovaNotaModal({ open, onOpenChange, preset }: { open: boolean; onOpenChange: (v: boolean) => void; preset: { tipo?: string; vehicle?: string } }) {
  const qc = useQueryClient();
  const [, navigate] = useLocation();
  const { organization, organizations, setOrganization } = useAuth();
  const FISCAL_ROLES = ["owner", "admin", "operator", "finance"];
  const emitters = organizations.filter((o) => FISCAL_ROLES.includes(o.role));
  const form = useForm<Record<string, string>>({ defaultValues: { tipo: preset.tipo ?? "1", forma_pagamento: "17", uf: "" } });
  const { register, setValue, formState, reset } = form;
  const e = formState.errors as Record<string, { message?: string }>;

  const vehicle = useQuery({
    queryKey: ["vehicle", preset.vehicle],
    queryFn: () => api(`/renave/stock/${preset.vehicle}`),
    enabled: !!preset.vehicle,
  });
  useEffect(() => {
    if (vehicle.data) reset({ ...form.getValues(), placa: plate(vehicle.data.placa), renavam: vehicle.data.renavam, marca_modelo: vehicle.data.marca_modelo ?? "" });
  }, [vehicle.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const req = { required: "Obrigatório" };
  const submit = form.handleSubmit(async (v) => {
    const body = {
      ...v,
      vehicle_id: preset.vehicle ?? null,
      valor_cents: parseMoney(v.valor),
      ano_fabricacao: Number(v.ano_fabricacao),
      ano_modelo: Number(v.ano_modelo),
      km: v.km ? Number(v.km.replace(/\D/g, "")) : undefined,
    };
    try {
      const nota = await api<Nota>("/fiscal/notas", { body });
      toast.success(`NF-e ${nota.serie}/${nota.numero} enviada para autorização.`);
      qc.invalidateQueries({ queryKey: ["notas"] });
      onOpenChange(false);
      navigate(`/notas/${nota.id}`);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });

  const PH: Record<string, string> = {
    nome: "Nome completo ou razão social", inscricao_estadual: "Somente se contribuinte", email: "cliente@email.com", telefone: "(84) 99999-9999",
    logradouro: "Rua, avenida…", numero: "Nº", complemento: "Apto, sala…", bairro: "Bairro", cidade: "Preenchida pelo CEP",
    cidade_ibge: "Preenchido pelo CEP", placa: "ABC1D23", chassi: "17 caracteres", renavam: "00000000000", marca_modelo: "Ex.: VW/GOL 1.0",
    cor: "Ex.: Prata", ano_fabricacao: "2020", ano_modelo: "2021", km: "Ex.: 54.000", ncm: "Padrão das configurações",
  };
  const f = (name: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}, rules: object = req) => (
    <Field label={label} htmlFor={name} error={e[name]?.message}>
      <Input id={name} placeholder={PH[name]} {...register(name, rules)} {...props} />
    </Field>
  );
  const onCep = async (raw: string) => {
    const v = maskCep(raw);
    setValue("cep", v);
    const a = await lookupAddress(v);
    if (a) {
      setValue("logradouro", a.street);
      setValue("bairro", a.district);
      setValue("cidade", a.city);
      setValue("cidade_ibge", a.city_ibge);
      setValue("uf", a.uf);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Emitir NF-e de veículo" description="A nota é transmitida à SEFAZ com o certificado A1 da empresa." wide>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Empresa emitente"
          htmlFor="emitente"
          hint={preset.vehicle ? "Definida pelo veículo do estoque." : emitters.length > 1 ? "A nota sai no CNPJ selecionado." : undefined}
        >
          <Select id="emitente" value={organization?.id} disabled={!!preset.vehicle || emitters.length < 2} onChange={(ev) => setOrganization(ev.target.value)}>
            {emitters.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name} — {document(o.cnpj)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Operação" htmlFor="tipo">
          <Select id="tipo" {...register("tipo")}>
            <option value="1">Saída — venda do veículo</option>
            <option value="0">Entrada — compra do veículo</option>
          </Select>
        </Field>
        </div>
        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-semibold">Destinatário</legend>
          <Field label="CPF/CNPJ" htmlFor="documento" error={e.documento?.message}>
            <Input id="documento" placeholder="CPF ou CNPJ" {...register("documento", { ...req, onChange: (ev) => setValue("documento", maskDocument(ev.target.value)) })} />
          </Field>
          <div className="sm:col-span-2">{f("nome", "Nome / razão social")}</div>
          {f("inscricao_estadual", "Inscrição estadual", {}, {})}
          {f("email", "E-mail", { type: "email" }, {})}
          {f("telefone", "Telefone", { type: "tel" }, {})}
          <Field label="CEP" htmlFor="cep" error={e.cep?.message} hint="Preenche endereço, cidade e IBGE.">
            <Input id="cep" inputMode="numeric" placeholder="00000-000" {...register("cep", { ...req, onChange: (ev) => onCep(ev.target.value) })} />
          </Field>
          <div className="sm:col-span-2">{f("logradouro", "Logradouro")}</div>
          {f("numero", "Número")}
          {f("complemento", "Complemento", {}, {})}
          {f("bairro", "Bairro")}
          {f("cidade", "Cidade")}
          {f("cidade_ibge", "Código IBGE da cidade", { inputMode: "numeric", maxLength: 7 })}
          <Field label="UF" htmlFor="uf" error={e.uf?.message}>
            <Select id="uf" {...register("uf", req)}>
              <option value="">—</option>
              {UFS.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </Select>
          </Field>
        </fieldset>
        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-semibold">Veículo</legend>
          {f("placa", "Placa", { className: "font-mono uppercase" })}
          {f("chassi", "Chassi", { className: "font-mono uppercase", maxLength: 17 })}
          {f("renavam", "RENAVAM", { inputMode: "numeric", maxLength: 11 })}
          <div className="sm:col-span-2">{f("marca_modelo", "Marca/modelo")}</div>
          {f("cor", "Cor")}
          {f("ano_fabricacao", "Ano fabricação", { inputMode: "numeric", maxLength: 4 })}
          {f("ano_modelo", "Ano modelo", { inputMode: "numeric", maxLength: 4 })}
          {f("km", "Quilometragem", { inputMode: "numeric" }, {})}
          {f("ncm", "NCM (opcional)", { inputMode: "numeric", maxLength: 8 }, {})}
        </fieldset>
        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-semibold">Valores</legend>
          <Field label="Valor (R$)" htmlFor="valor" error={e.valor_cents?.message}>
            <Input id="valor" inputMode="decimal" placeholder="0,00" {...register("valor", { ...req, onChange: (ev) => setValue("valor", maskMoney(ev.target.value)) })} />
          </Field>
          <Field label="Forma de pagamento" htmlFor="fp">
            <Select id="fp" {...register("forma_pagamento")}>
              <option value="17">PIX</option>
              <option value="01">Dinheiro</option>
              <option value="03">Cartão de crédito</option>
              <option value="04">Cartão de débito</option>
              <option value="15">Boleto</option>
              <option value="18">Transferência</option>
              <option value="99">Outros</option>
            </Select>
          </Field>
          <Field label="Observações" htmlFor="obs" className="sm:col-span-3">
            <Textarea id="obs" rows={2} placeholder="Informações adicionais que devem sair na nota (opcional)" {...register("observacoes")} />
          </Field>
        </fieldset>
        <div className="flex justify-end">
          <Button type="submit" loading={formState.isSubmitting}>
            Emitir NF-e
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function NotasPage() {
  const params = new URLSearchParams(useSearch());
  const { organization, can } = useAuth();
  const fiscalOk = useBilling().has("fiscal");
  const [open, setOpen] = useState(params.get("nova") === "1");
  const [status, setStatus] = useState("");
  const q = useInfiniteQuery({
    queryKey: ["notas", organization?.id, status],
    queryFn: ({ pageParam }) => api<Page<Nota>>("/fiscal/notas", { params: { cursor: pageParam, status } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (l) => cursorOf(l.next),
    refetchInterval: (query) => (query.state.data?.pages.some((p) => p.results.some((n) => ["queued", "processing"].includes(n.status))) ? 5000 : false),
  });
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <>
      <PageHeader
        title="Notas fiscais"
        description="NF-e de entrada e saída de veículos, com envio automático da chave ao RENAVE."
        action={
          can("fiscal.emit") &&
          fiscalOk && (
            <Button onClick={() => setOpen(true)}>
              <Plus className="size-4" /> Emitir NF-e
            </Button>
          )
        }
      />
      {!fiscalOk && (
        <div className="mb-6">
          <LockedPanel feature="fiscal" title="Emissão de nota fiscal" />
        </div>
      )}
      <Card
        title="Notas emitidas"
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 w-44">
            <option value="">Todas</option>
            <option value="authorized">Autorizadas</option>
            <option value="rejected">Rejeitadas</option>
            <option value="canceled">Canceladas</option>
          </Select>
        }
      >
        {q.isLoading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <Empty title="Nenhuma nota emitida" icon={<FileText />} />
        ) : (
          <Table head={["Número", "Operação", "Destinatário", "Veículo", "Valor", "Status", "Data"]}>
            {rows.map((n) => (
              <tr key={n.id} className="hover:bg-pale/60">
                <td className="px-5 py-3">
                  <Link href={`/notas/${n.id}`} className="font-semibold text-brand hover:underline">
                    {n.serie}/{n.numero}
                  </Link>
                  {n.ambiente === "2" && <span className="ml-2 text-xs text-muted">homologação</span>}
                </td>
                <td className="px-5 py-3">{n.tipo_display}</td>
                <td className="px-5 py-3">{n.destinatario_nome}</td>
                <td className="px-5 py-3 font-mono">{n.placa ? plate(n.placa) : "—"}</td>
                <td className="px-5 py-3">{money(n.total_cents)}</td>
                <td className="px-5 py-3">
                  <Badge tone={TONE[n.status]}>{n.status_display}</Badge>
                </td>
                <td className="px-5 py-3 whitespace-nowrap">{dateTime(n.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {open && <NovaNotaModal open onOpenChange={setOpen} preset={{ tipo: params.get("tipo") ?? undefined, vehicle: params.get("vehicle") ?? undefined }} />}
    </>
  );
}

export function NotaDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [modal, setModal] = useState<"cancel" | "cce" | null>(null);
  const [text, setText] = useState("");
  const { data: n, isLoading } = useQuery({
    queryKey: ["nota", id],
    queryFn: () => api<Nota>(`/fiscal/notas/${id}`),
    refetchInterval: (q) => (q.state.data && ["queued", "processing"].includes(q.state.data.status) ? 3000 : false),
  });
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => api<Nota>(`/fiscal/notas/${id}/${path}`, { body: body ?? {} }),
    onSuccess: (d) => {
      qc.setQueryData(["nota", id], d);
      qc.invalidateQueries({ queryKey: ["notas"] });
      setModal(null);
      setText("");
      toast.success("Solicitação realizada.");
    },
    onError: (e) => handleApiError(e),
  });

  if (isLoading || !n) return <Spinner />;
  const ok = n.status === "authorized";
  return (
    <div className="space-y-6">
      <Link href="/notas" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Voltar
      </Link>
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl bg-graphite p-6 text-white">
        <div>
          <p className="text-xs font-semibold text-mint">
            NF-e · {n.tipo_display} {n.ambiente === "2" && "· homologação"}
          </p>
          <p className="mt-1 font-display text-4xl font-semibold">
            {n.serie}/{n.numero}
          </p>
          <p className="text-sm text-[#a1a1aa]">
            {n.destinatario_nome} · {document(n.destinatario_documento)} · {money(n.total_cents)}
          </p>
        </div>
        <Badge tone={TONE[n.status]}>{n.status_display}</Badge>
      </section>

      <div className="flex flex-wrap gap-2">
        {ok && n.has_pdf && (
          <Button variant="secondary" onClick={() => download(`/fiscal/notas/${n.id}/pdf`, true).catch(handleApiError)}>
            <Download className="size-4" /> DANFE
          </Button>
        )}
        {(ok || n.status === "canceled") && (
          <Button variant="secondary" onClick={() => download(`/fiscal/notas/${n.id}/xml`).catch(handleApiError)}>
            <Download className="size-4" /> XML
          </Button>
        )}
        {can("fiscal.emit") && ok && (
          <>
            <Button variant="secondary" onClick={() => setModal("cce")}>
              Carta de correção
            </Button>
            <Button variant="danger" onClick={() => setModal("cancel")}>
              Cancelar NF-e
            </Button>
          </>
        )}
        {can("fiscal.emit") && ["rejected", "error"].includes(n.status) && (
          <Button onClick={() => act.mutate({ path: "reenviar" })} loading={act.isPending}>
            <RotateCw className="size-4" /> Corrigir e reenviar
          </Button>
        )}
      </div>

      <Card title="Retorno da SEFAZ">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          {[
            ["Chave de acesso", <span className="font-mono break-all">{n.chave || "—"}</span>],
            ["Protocolo", n.protocolo || "—"],
            ["cStat", n.cstat || "—"],
            ["Mensagem", n.message || (["queued", "processing"].includes(n.status) ? "Aguardando retorno…" : "—")],
            ["Autorizada em", dateTime(n.authorized_at)],
            ["Cartas de correção", n.cce_count],
          ].map(([k, v], i) => (
            <div key={i}>
              <dt className="text-xs font-semibold tracking-wide text-muted uppercase">{k}</dt>
              <dd className="mt-0.5 font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Modal open={modal !== null} onOpenChange={(o) => !o && setModal(null)} title={modal === "cancel" ? "Cancelar NF-e" : "Carta de correção"} description={modal === "cancel" ? "O cancelamento é definitivo. Informe a justificativa (mín. 15 caracteres)." : "Corrija dados que não alteram valores, impostos ou partes da operação."}>
        <div className="space-y-4">
          <Textarea
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            minLength={15}
            maxLength={1000}
            aria-label="Texto"
            placeholder={modal === "cancel" ? "Ex.: Nota emitida com valor incorreto, será emitida uma nova." : "Ex.: Corrigir a cor do veículo informada para PRATA."}
          />
          <Button
            className="w-full"
            variant={modal === "cancel" ? "danger" : "primary"}
            disabled={text.trim().length < 15}
            loading={act.isPending}
            onClick={() => act.mutate(modal === "cancel" ? { path: "cancelar", body: { justificativa: text } } : { path: "carta-correcao", body: { texto: text } })}
          >
            Confirmar
          </Button>
        </div>
      </Modal>
    </div>
  );
}
