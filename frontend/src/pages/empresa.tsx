import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { KeyRound, Plus, Trash2, Upload, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { useSearch } from "wouter";

import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, document, maskDocument, onlyDigits, ROLE_LABEL, UFS } from "@/lib/format";
import { handleApiError } from "@/lib/forms";
import { lookupAddress, lookupCompany, maskCep } from "@/lib/lookup";
import { AddCompanyModal } from "@/components/AddCompanyModal";
import { ask } from "@/components/confirm";

const TABS = [
  ["dados", "Dados da empresa"],
  ["equipe", "Equipe"],
  ["certificados", "Certificados digitais"],
  ["fiscal", "Configuração fiscal"],
] as const;

function Dados() {
  const { organization, can, reload } = useAuth();
  const q = useQuery({ queryKey: ["org", organization?.id], queryFn: () => api("/organizations/current") });
  const form = useForm<Record<string, any>>();
  useEffect(() => {
    if (q.data) form.reset(q.data);
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const e = form.formState.errors as Record<string, { message?: string }>;
  const disabled = !can("org.manage");
  const submit = form.handleSubmit(async (v) => {
    try {
      await api("/organizations/current", { method: "PATCH", body: v });
      toast.success("Dados atualizados.");
      reload();
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  if (q.isLoading) return <Spinner />;
  const PH: Record<string, string> = {
    legal_name: "Razão social", trade_name: "Nome fantasia", state_registration: "Inscrição estadual", email: "contato@sualoja.com.br",
    phone: "(84) 99999-9999", street: "Rua, avenida…", number: "Nº", complement: "Sala, loja…", district: "Bairro", city: "Cidade", city_ibge: "Preenchido pelo CEP",
  };
  const f = (name: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <Field label={label} htmlFor={name} error={e[name]?.message}>
      <Input id={name} disabled={disabled} placeholder={PH[name]} {...form.register(name)} {...props} />
    </Field>
  );
  const fillFromCnpj = async () => {
    const info = await lookupCompany(q.data.cnpj);
    if (!info) return toast.error("Não encontramos dados públicos para este CNPJ.");
    (["legal_name", "trade_name", "zip_code", "street", "number", "complement", "district", "city", "city_ibge", "uf"] as const).forEach((k) => info[k] && form.setValue(k, info[k], { shouldDirty: true }));
    toast.success("Dados preenchidos a partir da Receita Federal. Confira e salve.");
  };
  return (
    <Card
      title="Dados cadastrais e fiscais"
      description="Usados na emissão de notas e nas operações RENAVE."
      action={
        !disabled && (
          <Button size="sm" variant="secondary" type="button" onClick={fillFromCnpj}>
            Preencher pelo CNPJ
          </Button>
        )
      }
    >
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3">
        <Field label="CNPJ" htmlFor="cnpj">
          <Input id="cnpj" value={document(q.data.cnpj)} disabled />
        </Field>
        <div className="sm:col-span-2">{f("legal_name", "Razão social")}</div>
        {f("trade_name", "Nome fantasia")}
        {f("state_registration", "Inscrição estadual")}
        <Field label="Regime tributário" htmlFor="tax_regime">
          <Select id="tax_regime" disabled={disabled} {...form.register("tax_regime")}>
            <option value="">—</option>
            <option value="1">Simples Nacional</option>
            <option value="4">MEI</option>
            <option value="2">Simples — excesso de sublimite</option>
            <option value="3">Regime normal</option>
          </Select>
        </Field>
        {f("email", "E-mail", { type: "email" })}
        {f("phone", "Telefone", { type: "tel" })}
        <Field label="CEP" htmlFor="zip_code" hint="Preenche endereço e IBGE.">
          <Input
            id="zip_code"
            inputMode="numeric"
            placeholder="00000-000"
            disabled={disabled}
            {...form.register("zip_code", {
              onChange: async (ev) => {
                const v = maskCep(ev.target.value);
                form.setValue("zip_code", v);
                const a = await lookupAddress(v);
                if (a) {
                  form.setValue("street", a.street);
                  form.setValue("district", a.district);
                  form.setValue("city", a.city);
                  form.setValue("city_ibge", a.city_ibge);
                  form.setValue("uf", a.uf);
                }
              },
            })}
          />
        </Field>
        <div className="sm:col-span-2">{f("street", "Logradouro")}</div>
        {f("number", "Número")}
        {f("complement", "Complemento")}
        {f("district", "Bairro")}
        {f("city", "Cidade")}
        {f("city_ibge", "Código IBGE", { inputMode: "numeric", maxLength: 7 })}
        <Field label="UF" htmlFor="uf">
          <Select id="uf" disabled={disabled} {...form.register("uf")}>
            {UFS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-3">
          <input type="checkbox" className="size-4 accent-brand" disabled={disabled} {...form.register("mfa_required")} />
          Exigir verificação em duas etapas de todos os membros
        </label>
        {!disabled && (
          <div className="sm:col-span-3">
            <Button type="submit" loading={form.formState.isSubmitting}>
              Salvar alterações
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

function Equipe() {
  const { organization, can, user } = useAuth();
  const qc = useQueryClient();
  const org = organization?.id;
  const members = useQuery({ queryKey: ["members", org], queryFn: () => api<Page<any>>("/organizations/members") });
  const invites = useQuery({ queryKey: ["invites", org], queryFn: () => api<Page<any>>("/organizations/invitations"), enabled: can("members.manage") });
  const [open, setOpen] = useState(false);
  const form = useForm<{ email: string; role: string }>({ defaultValues: { role: "operator" } });
  const invite = form.handleSubmit(async (v) => {
    try {
      await api("/organizations/invitations", { body: v });
      toast.success("Convite enviado por e-mail.");
      qc.invalidateQueries({ queryKey: ["invites", org] });
      setOpen(false);
      form.reset();
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => api(`/organizations/members/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", org] }),
    onError: (e) => handleApiError(e),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/organizations/members/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", org] }),
    onError: (e) => handleApiError(e),
  });
  const manage = can("members.manage");
  return (
    <>
      <Card
        title="Membros"
        action={
          manage && (
            <Button size="sm" onClick={() => setOpen(true)}>
              <UserPlus className="size-4" /> Convidar
            </Button>
          )
        }
      >
        {members.isLoading ? (
          <Spinner />
        ) : (
          <Table head={["Nome", "E-mail", "Papel", "2FA", ""]}>
            {members.data?.results.map((m) => (
              <tr key={m.id}>
                <td className="px-5 py-3 font-semibold">{m.full_name}</td>
                <td className="px-5 py-3 text-muted">{m.email}</td>
                <td className="px-5 py-3">
                  {manage && m.role !== "owner" && m.email !== user?.email ? (
                    <Select value={m.role} onChange={(e) => update.mutate({ id: m.id, body: { role: e.target.value } })} className="h-9 w-44">
                      {["admin", "operator", "finance", "vendedor", "viewer"].map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    ROLE_LABEL[m.role]
                  )}
                </td>
                <td className="px-5 py-3">{m.totp_enabled ? <Badge tone="green">Ativo</Badge> : <Badge tone="yellow">Desativado</Badge>}</td>
                <td className="px-5 py-3 text-right">
                  {manage && m.role !== "owner" && m.email !== user?.email && (
                    <Button size="sm" variant="ghost" aria-label="Remover" onClick={() => void ask(`Remover ${m.full_name}?`).then((ok) => ok && remove.mutate(m.id))}>
                      <Trash2 className="size-4 text-red" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {manage && !!invites.data?.results.length && (
        <Card title="Convites pendentes" className="mt-6">
          <ul className="divide-y divide-line text-sm">
            {invites.data.results.map((i) => (
              <li key={i.id} className="flex justify-between py-2">
                <span>{i.email}</span>
                <span className="text-muted">
                  {ROLE_LABEL[i.role]} · expira {date(i.expires_at)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Convidar para a equipe">
        <form onSubmit={invite} className="space-y-4">
          <Field label="E-mail" htmlFor="inv-email" error={form.formState.errors.email?.message}>
            <Input id="inv-email" type="email" required placeholder="pessoa@sualoja.com.br" {...form.register("email")} />
          </Field>
          <Field label="Papel" htmlFor="inv-role">
            <Select id="inv-role" {...form.register("role")}>
              <option value="admin">Administrador — tudo, exceto titularidade</option>
              <option value="operator">Operador — consultas, RENAVE, notas</option>
              <option value="finance">Financeiro — carteira, plano e notas</option>
              <option value="vendedor">Vendedor — atendimento e vendas</option>
              <option value="viewer">Somente leitura</option>
            </Select>
          </Field>
          <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
            Enviar convite
          </Button>
        </form>
      </Modal>
    </>
  );
}

function Clientes() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const org = organization?.id;
  const q = useQuery({ queryKey: ["clients", org], queryFn: () => api<Page<any>>("/organizations/clients", { params: { is_active: "true" } }) });
  const [open, setOpen] = useState(false);
  const form = useForm<{ document: string; name: string; email: string; phone: string }>();
  const submit = form.handleSubmit(async (v) => {
    try {
      await api("/organizations/clients", { body: v });
      toast.success("Cliente cadastrado. Envie o certificado A1 dele na aba Certificados.");
      qc.invalidateQueries({ queryKey: ["clients", org] });
      qc.invalidateQueries({ queryKey: ["clients-choices", org] });
      setOpen(false);
      form.reset();
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  return (
    <>
      <Card
        title="Clientes atendidos"
        description="Para despachantes e contadores que operam o RENAVE em nome de lojas."
        action={
          can("clients.manage") && (
            <Button size="sm" onClick={() => setOpen(true)}>
              <Plus className="size-4" /> Novo cliente
            </Button>
          )
        }
      >
        {q.isLoading ? (
          <Spinner />
        ) : !q.data?.results.length ? (
          <Empty title="Nenhum cliente cadastrado" icon={<Users />} />
        ) : (
          <Table head={["Nome", "Documento", "Contato", "Certificado"]}>
            {q.data.results.map((c) => (
              <tr key={c.id}>
                <td className="px-5 py-3 font-semibold">{c.name}</td>
                <td className="px-5 py-3 font-mono">{document(c.document)}</td>
                <td className="px-5 py-3 text-muted">{c.email || c.phone || "—"}</td>
                <td className="px-5 py-3">{c.has_certificate ? <Badge tone="green">Enviado</Badge> : <Badge tone="yellow">Pendente</Badge>}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Novo cliente">
        <form onSubmit={submit} className="space-y-4">
          <Field label="CPF/CNPJ" htmlFor="c-doc" error={form.formState.errors.document?.message}>
            <Input id="c-doc" required placeholder="CPF ou CNPJ do cliente" {...form.register("document", { onChange: (e) => form.setValue("document", maskDocument(e.target.value)) })} />
          </Field>
          <Field label="Nome / razão social" htmlFor="c-name" error={form.formState.errors.name?.message}>
            <Input id="c-name" required placeholder="Nome ou razão social" {...form.register("name")} />
          </Field>
          <Field label="E-mail" htmlFor="c-email">
            <Input id="c-email" type="email" placeholder="cliente@email.com" {...form.register("email")} />
          </Field>
          <Field label="Telefone" htmlFor="c-phone">
            <Input id="c-phone" type="tel" placeholder="(84) 99999-9999" {...form.register("phone")} />
          </Field>
          <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
            Cadastrar
          </Button>
        </form>
      </Modal>
    </>
  );
}

function Certificados() {
  const { organization, can } = useAuth();
  const qc = useQueryClient();
  const org = organization?.id;
  const certs = useQuery({ queryKey: ["certificates", org], queryFn: () => api<Page<any>>("/vault/certificates") });
  const clients = useQuery({ queryKey: ["clients-choices", org], queryFn: () => api<any[]>("/organizations/clients/choices") });
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [client, setClient] = useState("");
  const upload = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("password", password);
      if (client) fd.append("client_id", client);
      return api("/vault/certificates", { form: fd });
    },
    onSuccess: () => {
      toast.success("Certificado validado e guardado com criptografia.");
      setFile(null);
      setPassword("");
      qc.invalidateQueries({ queryKey: ["certificates", org] });
      qc.invalidateQueries({ queryKey: ["clients", org] });
    },
    onError: (e) => handleApiError(e),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/vault/certificates/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["certificates", org] }),
    onError: (e) => handleApiError(e),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <Card title="Certificados ativos">
        {certs.isLoading ? (
          <Spinner />
        ) : !certs.data?.results.length ? (
          <Empty title="Nenhum certificado" icon={<KeyRound />}>
            O certificado A1 é necessário para operar o RENAVE e emitir NF-e.
          </Empty>
        ) : (
          <Table head={["Titular", "Documento", "Validade", "RENAVE", ""]}>
            {certs.data.results.map((c) => (
              <tr key={c.id}>
                <td className="px-5 py-3">
                  <p className="font-semibold">{c.holder_name}</p>
                  <p className="text-xs text-muted">{c.client_name ?? "Própria empresa"}</p>
                </td>
                <td className="px-5 py-3 font-mono">{document(c.holder_document)}</td>
                <td className="px-5 py-3">
                  {date(c.not_after)} <Badge tone={c.days_to_expire < 30 ? "red" : c.days_to_expire < 60 ? "yellow" : "green"}>{c.days_to_expire} dias</Badge>
                </td>
                <td className="px-5 py-3">{c.renave_ready ? <Badge tone="green">Pronto</Badge> : c.renave_error ? <Badge tone="red">{c.renave_error}</Badge> : <Badge tone="yellow">Preparando</Badge>}</td>
                <td className="px-5 py-3 text-right">
                  {can("vault.manage") && (
                    <Button size="sm" variant="ghost" aria-label="Desativar" onClick={() => void ask("Desativar este certificado?").then((ok) => ok && remove.mutate(c.id))}>
                      <Trash2 className="size-4 text-red" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {can("vault.manage") && (
        <Card title="Enviar certificado A1" description="Arquivo .pfx ou .p12. O arquivo e a senha são cifrados e nunca são exibidos novamente.">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              upload.mutate();
            }}
          >
            {!!clients.data?.length && (
            <Field label="Titular" htmlFor="cert-client">
              <Select id="cert-client" value={client} onChange={(e) => setClient(e.target.value)}>
                <option value="">Minha empresa</option>
                {clients.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            )}
            <Field label="Arquivo do certificado" htmlFor="cert-file">
              <Input id="cert-file" type="file" accept=".pfx,.p12" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="pt-2" />
            </Field>
            <Field label="Senha do certificado" htmlFor="cert-pass">
              <Input id="cert-pass" type="password" autoComplete="off" placeholder="Senha definida na emissão do certificado" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Button type="submit" className="w-full" disabled={!file || !password} loading={upload.isPending}>
              <Upload className="size-4" /> Validar e enviar
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}

function Fiscal() {
  const { organization, can } = useAuth();
  const q = useQuery({ queryKey: ["fiscal-settings", organization?.id], queryFn: () => api("/fiscal/settings") });
  const form = useForm<Record<string, any>>();
  useEffect(() => {
    if (q.data) form.reset(q.data);
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const disabled = !can("fiscal.configure");
  const submit = form.handleSubmit(async (v) => {
    try {
      await api("/fiscal/settings", { method: "PATCH", body: { ...v, serie: Number(v.serie), next_number: Number(onlyDigits(String(v.next_number))) } });
      toast.success("Configuração fiscal salva.");
    } catch (err) {
      handleApiError(err, form.setError);
    }
  });
  if (q.isLoading) return <Spinner />;
  const PH: Record<string, string> = {
    serie: "1", next_number: "1", ncm_padrao: "87032310", natureza_venda: "Venda de veículo usado", natureza_compra: "Compra de veículo usado",
    icms_csosn: "102", cfop_venda_estadual: "5102", cfop_venda_interestadual: "6102", cfop_compra_estadual: "1102", cfop_compra_interestadual: "2102",
    pis_cst: "49", cofins_cst: "49",
  };
  const f = (name: string, label: string) => (
    <Field label={label} htmlFor={name}>
      <Input id={name} disabled={disabled} placeholder={PH[name]} {...form.register(name)} />
    </Field>
  );
  return (
    <Card title="Parâmetros da NF-e" description="Confira estes valores com o contador da empresa antes de emitir em produção.">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3">
        {f("serie", "Série")}
        {f("next_number", "Próximo número")}
        {f("ncm_padrao", "NCM padrão")}
        {f("natureza_venda", "Natureza da operação — venda")}
        {f("natureza_compra", "Natureza da operação — compra")}
        {f("icms_csosn", "CSOSN (Simples)")}
        {f("cfop_venda_estadual", "CFOP venda estadual")}
        {f("cfop_venda_interestadual", "CFOP venda interestadual")}
        {f("cfop_compra_estadual", "CFOP compra estadual")}
        {f("cfop_compra_interestadual", "CFOP compra interestadual")}
        {f("pis_cst", "CST PIS")}
        {f("cofins_cst", "CST COFINS")}
        <Field label="Informações complementares padrão" htmlFor="ic" className="sm:col-span-3">
          <Textarea id="ic" rows={3} disabled={disabled} placeholder="Texto que sai em todas as notas (ex.: regime especial, observações do contador)" {...form.register("informacao_complementar")} />
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-3">
          <input type="checkbox" className="size-4 accent-brand" disabled={disabled} {...form.register("enviar_chave_renave")} />
          Enviar automaticamente a chave da NF-e ao RENAVE quando a nota estiver ligada a um veículo do estoque
        </label>
        {!disabled && (
          <div className="sm:col-span-3">
            <Button type="submit" loading={form.formState.isSubmitting}>
              Salvar
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

export function EmpresaPage() {
  const initial = new URLSearchParams(useSearch()).get("aba") ?? "dados";
  const [tab, setTab] = useState<string>(TABS.some(([k]) => k === initial) ? initial : "dados");
  const [adding, setAdding] = useState(false);
  return (
    <>
      <PageHeader
        title="Empresa"
        description="Dados, equipe, clientes, certificados digitais e configuração fiscal."
        action={
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Adicionar outra empresa
          </Button>
        }
      />
      <AddCompanyModal open={adding} onOpenChange={setAdding} />
      <div className="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-white p-1 ring-1 ring-line" role="tablist">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={clsx("rounded-lg px-4 py-2 text-sm font-semibold whitespace-nowrap", tab === key ? "bg-graphite text-white" : "text-muted hover:text-ink")}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "dados" && <Dados />}
      {tab === "equipe" && <Equipe />}
      {tab === "clientes" && <Clientes />}
      {tab === "certificados" && <Certificados />}
      {tab === "fiscal" && <Fiscal />}
    </>
  );
}
