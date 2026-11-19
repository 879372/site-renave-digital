import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, RefreshCw, Send, XCircle } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { api, cursorOf, download, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, maskDocument, maskMoney, money, parseMoney, plate, UFS } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { lookupAddress, maskCep } from "@/lib/lookup";

type Comunicacao = {
  id: string;
  protocolo: string;
  situacao: number | null;
  situacao_display: string | null;
  placa: string;
  comprador_nome: string;
  valor_cents: number;
  data_venda: string;
  message: string;
  price_cents: number;
  created_at: string;
};

const TONE: Record<number, "green" | "yellow" | "red" | "blue" | "gray"> = { 1: "yellow", 2: "green", 3: "green", 4: "gray", 5: "red", 6: "gray", 7: "red", 8: "red" };

type Form = Record<string, string> & { comprador_solicitante?: any };

function NovaModal({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const form = useForm<Form>({ defaultValues: { vendedor_tipo: "F", comprador_tipo: "F", crv_via: "1", data_venda: new Date().toISOString().slice(0, 10) } });
  const { register, setValue, formState } = form;
  const e = formState.errors as Record<string, { message?: string }>;
  const doc = (name: string) => register(name, { required: "Obrigatório", onChange: (ev) => setValue(name, maskDocument(ev.target.value)) });

  const submit = form.handleSubmit(async (v) => {
    const body = {
      ...v,
      valor_cents: parseMoney(v.valor),
      ano_fabricacao: Number(v.ano_fabricacao),
      ano_modelo: Number(v.ano_modelo),
      crv_via: Number(v.crv_via),
      cidade_comprador: Number(v.cidade_comprador),
      cidade_venda: Number(v.cidade_venda),
      comprador_solicitante: !!v.comprador_solicitante,
    };
    try {
      await api("/comunicacao-venda/", { body });
      toast.success("Comunicação cadastrada. Confira os dados e transmita.");
      qc.invalidateQueries({ queryKey: ["comunicacoes"] });
      onOpenChange(false);
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });

  const PH: Record<string, string> = {
    renavam: "00000000000", ano_fabricacao: "2020", ano_modelo: "2021", crv_numero: "Número do CRV", crv_codigo_seguranca: "Código de segurança",
    crv_via: "1", crv_data_emissao: "", vendedor_nome: "Nome completo / razão social", comprador_nome: "Nome completo / razão social",
    cep: "00000-000", logradouro: "Rua, avenida…", numero: "Nº", complemento: "Apto, sala…", bairro: "Bairro",
    cidade_comprador: "Preenchido pelo CEP", data_venda: "", cidade_venda: "Código IBGE da cidade da venda",
  };
  const F = ({ name, label, ...rest }: { name: string; label: string } & React.InputHTMLAttributes<HTMLInputElement>) => (
    // chamada como função (não como componente) para não remontar o input a cada render
    <Field label={label} htmlFor={name} error={e[name]?.message}>
      <Input id={name} placeholder={PH[name] || undefined} {...register(name, { required: rest.required === false ? false : "Obrigatório" })} {...rest} required={undefined} />
    </Field>
  );

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Nova comunicação de venda" description="A comunicação fica salva como rascunho e só é enviada ao órgão de trânsito quando você transmitir." wide>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-bold">Veículo</legend>
          <Field label="Placa" htmlFor="placa" error={e.placa?.message}>
            <Input id="placa" placeholder="ABC1D23" className="font-mono uppercase" {...register("placa", { required: "Obrigatório", onChange: (ev) => setValue("placa", plate(ev.target.value)) })} />
          </Field>
          {F({ name: "renavam", label: "RENAVAM", inputMode: "numeric", maxLength: 11 })}
          <div className="grid grid-cols-2 gap-3">
            {F({ name: "ano_fabricacao", label: "Ano fab.", inputMode: "numeric", maxLength: 4 })}
            {F({ name: "ano_modelo", label: "Ano mod.", inputMode: "numeric", maxLength: 4 })}
          </div>
          {F({ name: "crv_numero", label: "Número do CRV" })}
          {F({ name: "crv_codigo_seguranca", label: "Código de segurança", autoComplete: "off" })}
          <div className="grid grid-cols-2 gap-3">
            {F({ name: "crv_via", label: "Via", inputMode: "numeric" })}
            <Field label="UF do CRV" htmlFor="crv_uf" error={e.crv_uf?.message}>
              <Select id="crv_uf" {...register("crv_uf", { required: "Obrigatório" })}>
                <option value="">—</option>
                {UFS.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </Select>
            </Field>
          </div>
          {F({ name: "crv_data_emissao", label: "Emissão do CRV", type: "date" })}
        </fieldset>

        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-bold">Vendedor</legend>
          <Field label="Tipo" htmlFor="vendedor_tipo">
            <Select id="vendedor_tipo" {...register("vendedor_tipo")}>
              <option value="F">Pessoa física</option>
              <option value="J">Pessoa jurídica</option>
            </Select>
          </Field>
          <Field label="CPF/CNPJ" htmlFor="vendedor_documento" error={e.vendedor_documento?.message}>
            <Input id="vendedor_documento" placeholder="CPF ou CNPJ" {...doc("vendedor_documento")} />
          </Field>
          {F({ name: "vendedor_nome", label: "Nome" })}
        </fieldset>

        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-bold">Comprador</legend>
          <Field label="Tipo" htmlFor="comprador_tipo">
            <Select id="comprador_tipo" {...register("comprador_tipo")}>
              <option value="F">Pessoa física</option>
              <option value="J">Pessoa jurídica</option>
            </Select>
          </Field>
          <Field label="CPF/CNPJ" htmlFor="comprador_documento" error={e.comprador_documento?.message}>
            <Input id="comprador_documento" placeholder="CPF ou CNPJ" {...doc("comprador_documento")} />
          </Field>
          {F({ name: "comprador_nome", label: "Nome" })}
          <Field label="CEP" htmlFor="cep" error={e.cep?.message} hint="Preenche endereço e cidade.">
            <Input
              id="cep"
              inputMode="numeric"
              placeholder="00000-000"
              {...register("cep", {
                required: "Obrigatório",
                onChange: async (ev) => {
                  const v = maskCep(ev.target.value);
                  setValue("cep", v);
                  const a = await lookupAddress(v);
                  if (a) {
                    setValue("logradouro", a.street);
                    setValue("bairro", a.district);
                    setValue("cidade_comprador", a.city_ibge);
                    if (!form.getValues("cidade_venda")) setValue("cidade_venda", a.city_ibge);
                  }
                },
              })}
            />
          </Field>
          {F({ name: "logradouro", label: "Logradouro" })}
          <div className="grid grid-cols-2 gap-3">
            {F({ name: "numero", label: "Número" })}
            {F({ name: "complemento", label: "Compl.", required: false })}
          </div>
          {F({ name: "bairro", label: "Bairro" })}
          {F({ name: "cidade_comprador", label: "Cidade (código IBGE)", inputMode: "numeric", maxLength: 7 })}
        </fieldset>

        <fieldset className="grid gap-4 rounded-xl border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-sm font-bold">Venda</legend>
          {F({ name: "data_venda", label: "Data da venda", type: "date" })}
          <Field label="Valor (R$)" htmlFor="valor" error={e.valor_cents?.message}>
            <Input id="valor" inputMode="decimal" placeholder="0,00" {...register("valor", { required: "Obrigatório", onChange: (ev) => setValue("valor", maskMoney(ev.target.value)) })} />
          </Field>
          {F({ name: "cidade_venda", label: "Cidade da venda (IBGE)", inputMode: "numeric", maxLength: 7 })}
          <label className="flex items-center gap-2 text-sm sm:col-span-3">
            <input type="checkbox" className="size-4 accent-blue" {...register("comprador_solicitante")} /> O comprador é quem está solicitando a comunicação
          </label>
        </fieldset>

        <div className="flex justify-end">
          <Button type="submit" loading={formState.isSubmitting}>
            Cadastrar comunicação
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function CancelModal({ item, onClose }: { item: Comunicacao; onClose: () => void }) {
  const qc = useQueryClient();
  const motivos = useQuery({ queryKey: ["motivos", item.id], queryFn: () => api<{ id_motivo_cancelamento: string; nome: string }[]>(`/comunicacao-venda/${item.id}/motivos`) });
  const [motivo, setMotivo] = useState("");
  const cancel = useMutation({
    mutationFn: () => api(`/comunicacao-venda/${item.id}/cancelar`, { body: { id_motivo_cancelamento: motivo } }),
    onSuccess: () => {
      toast.success("Comunicação cancelada.");
      qc.invalidateQueries({ queryKey: ["comunicacoes"] });
      onClose();
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`Cancelar comunicação ${plate(item.placa)}`}>
      {motivos.isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          <Field label="Motivo" htmlFor="motivo">
            <Select id="motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)}>
              <option value="">Selecione…</option>
              {motivos.data?.map((m) => (
                <option key={m.id_motivo_cancelamento} value={m.id_motivo_cancelamento}>
                  {m.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Button variant="danger" className="w-full" disabled={!motivo} loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Confirmar cancelamento
          </Button>
        </div>
      )}
    </Modal>
  );
}

export function ComunicacaoPage() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [canceling, setCanceling] = useState<Comunicacao | null>(null);
  const [search, setSearch] = useState("");
  const q = useInfiniteQuery({
    queryKey: ["comunicacoes", organization?.id, search],
    queryFn: ({ pageParam }) => api<Page<Comunicacao>>("/comunicacao-venda/", { params: { cursor: pageParam, search } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (l) => cursorOf(l.next),
  });
  const act = useMutation({
    mutationFn: ({ id, path }: { id: string; path: string }) => api(`/comunicacao-venda/${id}/${path}`, { method: "POST" }),
    onSuccess: (_, v) => {
      toast.success(v.path === "transmitir" ? "Comunicação transmitida ao órgão de trânsito." : "Situação atualizada.");
      qc.invalidateQueries({ queryKey: ["comunicacoes"] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
    },
    onError: (e) => handleApiError(e),
  });
  const rows = q.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Detran / Senatran"
        title="Comunicação de venda"
        description="Comunique eletronicamente a venda do veículo (art. 134 do CTB) sem ir ao Detran."
        action={
          can("comunicacao.operate") && (
            <Button onClick={() => setOpen(true)}>
              <Plus className="size-4" /> Nova comunicação
            </Button>
          )
        }
      />
      <Card title="Comunicações" action={<Input placeholder="Buscar placa…" value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 w-44" />}>
        {q.isLoading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <Empty title="Nenhuma comunicação" icon={<Send />} />
        ) : (
          <>
            <Table head={["Placa", "Comprador", "Venda", "Valor", "Protocolo", "Situação", ""]}>
              {rows.map((c) => (
                <tr key={c.id} className="align-top">
                  <td className="px-5 py-3 font-mono font-semibold">{plate(c.placa)}</td>
                  <td className="px-5 py-3">{c.comprador_nome}</td>
                  <td className="px-5 py-3">{date(c.data_venda)}</td>
                  <td className="px-5 py-3">{money(c.valor_cents)}</td>
                  <td className="px-5 py-3 font-mono text-muted">{c.protocolo}</td>
                  <td className="px-5 py-3">
                    <Badge tone={TONE[c.situacao ?? 1]}>{c.situacao_display ?? "—"}</Badge>
                    {c.message && <p className="mt-1 max-w-56 text-xs text-muted">{c.message}</p>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      {can("comunicacao.operate") && (c.situacao === 1 || c.situacao === 5) && (
                        <Button size="sm" onClick={() => act.mutate({ id: c.id, path: "transmitir" })} loading={act.isPending && act.variables?.id === c.id}>
                          Transmitir
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" aria-label="Atualizar situação" onClick={() => act.mutate({ id: c.id, path: "refresh" })}>
                        <RefreshCw className="size-4" />
                      </Button>
                      {(c.situacao === 2 || c.situacao === 3) && (
                        <Button size="sm" variant="ghost" aria-label="Baixar comprovante" onClick={() => download(`/comunicacao-venda/${c.id}/comprovante`).catch(handleApiError)}>
                          <Download className="size-4" />
                        </Button>
                      )}
                      {can("comunicacao.operate") && c.situacao === 2 && (
                        <Button size="sm" variant="ghost" aria-label="Cancelar" onClick={() => setCanceling(c)}>
                          <XCircle className="size-4 text-red" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
            {q.hasNextPage && (
              <div className="mt-4 text-center">
                <Button variant="secondary" size="sm" onClick={() => q.fetchNextPage()}>
                  Carregar mais
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
      <NovaModal open={open} onOpenChange={setOpen} />
      {canceling && <CancelModal item={canceling} onClose={() => setCanceling(null)} />}
    </>
  );
}
