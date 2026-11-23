import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Ban, CheckCircle2, PlusCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link, useParams } from "wouter";

import { Badge, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner, Stat } from "@/components/ui";
import { date, dateTime, document, maskMoney, money, parseMoney, ROLE_LABEL, UFS } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { adminApi } from "../api";
import { DATE_FILTERS, ResourceTable, STATUS_OPTIONS } from "../components";
import { ConsultasTable } from "./operacoes";

type OrgRow = {
  id: string;
  cnpj: string;
  legal_name: string;
  trade_name: string;
  kind: string;
  uf: string;
  city: string;
  is_active: boolean;
  balance_cents: number;
  members_count: number;
  owner: { name: string; email: string } | null;
  created_at: string;
};

const KIND: Record<string, string> = { revenda: "Revenda", concessionaria: "Concessionária", despachante: "Despachante", contador: "Contador" };

export function EmpresasPage() {
  return (
    <>
      <PageHeader title="Empresas" description="Todas as empresas cadastradas na plataforma." />
      <ResourceTable<OrgRow>
        endpoint="/organizations"
        searchPlaceholder="Razão social, fantasia, CNPJ ou cidade"
        filters={[
          { name: "is_active", label: "Situação", options: STATUS_OPTIONS.active },
          { name: "kind", label: "Tipo", options: [["", "Todos"], ...Object.entries(KIND)] },
          { name: "uf", label: "UF", options: [["", "Todas"], ...UFS.map((u) => [u, u] as [string, string])] },
          ...DATE_FILTERS,
        ]}
        columns={[
          {
            header: "Empresa",
            cell: (o) => (
              <Link href={`/empresas/${o.id}`} className="block">
                <span className="block font-semibold text-brand hover:underline">{o.trade_name || o.legal_name}</span>
                <span className="font-mono text-xs text-muted">{document(o.cnpj)}</span>
              </Link>
            ),
          },
          { header: "Responsável", cell: (o) => (o.owner ? <><span className="block">{o.owner.name}</span><span className="text-xs text-muted">{o.owner.email}</span></> : "—") },
          { header: "Tipo", cell: (o) => KIND[o.kind] ?? o.kind },
          { header: "Local", cell: (o) => [o.city, o.uf].filter(Boolean).join("/") || "—" },
          { header: "Membros", cell: (o) => o.members_count, className: "text-right" },
          { header: "Saldo", cell: (o) => money(o.balance_cents), className: "text-right whitespace-nowrap" },
          { header: "Situação", cell: (o) => (o.is_active ? <Badge tone="green">Ativa</Badge> : <Badge tone="red">Inativa</Badge>) },
          { header: "Cadastro", cell: (o) => date(o.created_at), className: "whitespace-nowrap" },
        ]}
      />
    </>
  );
}

type Member = { id: string; user_id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string };
type OrgDetail = Record<string, any> & {
  id: string;
  cnpj: string;
  legal_name: string;
  trade_name: string;
  is_active: boolean;
  balance_cents: number;
  members: Member[];
  certificates: any[];
  counts: { consultas_30d: number; spent_30d: number; stock: number; notas: number; clients: number };
};

function AdjustModal({ org, onClose }: { org: OrgDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<"credit" | "debit">("credit");
  const form = useForm<{ amount: string; reason: string }>();
  const submit = form.handleSubmit(async (v) => {
    const cents = parseMoney(v.amount) * (type === "debit" ? -1 : 1);
    try {
      await adminApi(`/organizations/${org.id}/wallet-adjust`, { body: { amount_cents: cents, reason: v.reason } });
      toast.success("Ajuste lançado no extrato da empresa.");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    } catch (e) {
      handleApiError(e, form.setError as any);
    }
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Ajustar saldo" description={`Saldo atual: ${money(org.balance_cents)}. O ajuste fica registrado no extrato e na auditoria.`}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Tipo de ajuste">
          {(["credit", "debit"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={type === t}
              onClick={() => setType(t)}
              className={clsx("rounded-lg border py-2 font-semibold", type === t ? "border-brand bg-brand-50 text-brand" : "border-line")}
            >
              {t === "credit" ? "Creditar" : "Debitar"}
            </button>
          ))}
        </div>
        <Field label="Valor (R$)" htmlFor="adj-amount">
          <Input id="adj-amount" inputMode="decimal" placeholder="0,00" required {...form.register("amount", { onChange: (e) => form.setValue("amount", maskMoney(e.target.value)) })} />
        </Field>
        <Field label="Motivo" htmlFor="adj-reason" error={form.formState.errors.reason?.message}>
          <Input id="adj-reason" placeholder="Ex.: cortesia de boas-vindas, estorno manual de cobrança duplicada" required {...form.register("reason")} />
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Lançar ajuste
        </Button>
      </form>
    </Modal>
  );
}

function DadosTab({ org }: { org: OrgDetail }) {
  const qc = useQueryClient();
  const form = useForm<Record<string, any>>();
  useEffect(() => form.reset(org), [org]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = form.handleSubmit(async (v) => {
    const fields = ["legal_name", "trade_name", "kind", "email", "phone", "state_registration", "tax_regime", "zip_code", "street", "number", "complement", "district", "city", "city_ibge", "uf", "mfa_required"];
    try {
      await adminApi(`/organizations/${org.id}`, { method: "PATCH", body: Object.fromEntries(fields.map((f) => [f, v[f]])) });
      toast.success("Empresa atualizada.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    } catch (e) {
      handleApiError(e, form.setError);
    }
  });
  const f = (name: string, label: string, placeholder = "") => (
    <Field label={label} htmlFor={`org-${name}`}>
      <Input id={`org-${name}`} placeholder={placeholder} {...form.register(name)} />
    </Field>
  );
  return (
    <Card title="Dados cadastrais e fiscais">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3">
        <Field label="CNPJ" htmlFor="org-cnpj">
          <Input id="org-cnpj" value={document(org.cnpj)} disabled />
        </Field>
        {f("legal_name", "Razão social", "Razão social")}
        {f("trade_name", "Nome fantasia", "Nome fantasia")}
        <Field label="Tipo" htmlFor="org-kind">
          <Select id="org-kind" {...form.register("kind")}>
            {Object.entries(KIND).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </Field>
        {f("email", "E-mail", "contato@empresa.com.br")}
        {f("phone", "Telefone", "(84) 99999-9999")}
        {f("state_registration", "Inscrição estadual", "Inscrição estadual")}
        <Field label="Regime tributário" htmlFor="org-regime">
          <Select id="org-regime" {...form.register("tax_regime")}>
            <option value="">—</option>
            <option value="1">Simples Nacional</option>
            <option value="4">MEI</option>
            <option value="2">Simples — excesso de sublimite</option>
            <option value="3">Regime normal</option>
          </Select>
        </Field>
        {f("zip_code", "CEP", "00000000")}
        {f("street", "Logradouro", "Rua, avenida…")}
        {f("number", "Número", "Nº")}
        {f("complement", "Complemento", "Sala, loja…")}
        {f("district", "Bairro", "Bairro")}
        {f("city", "Cidade", "Cidade")}
        {f("city_ibge", "Código IBGE", "0000000")}
        <Field label="UF" htmlFor="org-uf">
          <Select id="org-uf" {...form.register("uf")}>
            <option value="">—</option>
            {UFS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-3">
          <input type="checkbox" className="size-4 accent-brand" {...form.register("mfa_required")} /> Exigir verificação em duas etapas dos membros
        </label>
        <div className="sm:col-span-3">
          <Button type="submit" loading={form.formState.isSubmitting}>
            Salvar
          </Button>
        </div>
      </form>
    </Card>
  );
}

function MembrosTab({ org }: { org: OrgDetail }) {
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => adminApi(`/memberships/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      toast.success("Vínculo atualizado.");
      qc.invalidateQueries({ queryKey: ["admin", "org", org.id] });
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <Card title="Membros">
      <div className="-mx-5 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-muted uppercase">
            <tr className="border-b border-line">
              <th className="px-5 py-2">Usuário</th>
              <th className="px-5 py-2">Papel</th>
              <th className="px-5 py-2">Desde</th>
              <th className="px-5 py-2">Acesso</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {org.members.map((m) => (
              <tr key={m.id}>
                <td className="px-5 py-3">
                  <Link href={`/usuarios/${m.user_id}`} className="font-semibold text-brand hover:underline">
                    {m.full_name}
                  </Link>
                  <span className="block text-xs text-muted">{m.email}</span>
                </td>
                <td className="px-5 py-3">
                  <Select className="h-9 w-44" value={m.role} onChange={(e) => update.mutate({ id: m.id, body: { role: e.target.value } })}>
                    {Object.entries(ROLE_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="px-5 py-3">{date(m.created_at)}</td>
                <td className="px-5 py-3">
                  <Button size="sm" variant={m.is_active ? "secondary" : "primary"} onClick={() => update.mutate({ id: m.id, body: { is_active: !m.is_active } })}>
                    {m.is_active ? "Suspender" : "Reativar"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CarteiraTab({ org }: { org: OrgDetail }) {
  const [adjusting, setAdjusting] = useState(false);
  return (
    <>
      <ResourceTable<any>
        endpoint={`/organizations/${org.id}/ledger`}
        queryKey={`ledger-${org.id}`}
        title={`Extrato · saldo ${money(org.balance_cents)}`}
        action={
          <Button size="sm" onClick={() => setAdjusting(true)}>
            <PlusCircle className="size-4" /> Ajustar saldo
          </Button>
        }
        searchPlaceholder="Buscar na descrição"
        columns={[
          { header: "Data", cell: (e) => dateTime(e.created_at), className: "whitespace-nowrap" },
          { header: "Descrição", cell: (e) => e.description },
          { header: "Tipo", cell: (e) => <Badge tone={e.amount_cents >= 0 ? "green" : "gray"}>{e.kind_display}</Badge> },
          { header: "Valor", cell: (e) => <span className={e.amount_cents >= 0 ? "text-green" : ""}>{money(e.amount_cents)}</span>, className: "text-right whitespace-nowrap" },
          { header: "Saldo", cell: (e) => money(e.balance_after_cents), className: "text-right whitespace-nowrap" },
          { header: "Por", cell: (e) => e.created_by ?? "—" },
        ]}
      />
      {adjusting && <AdjustModal org={org} onClose={() => setAdjusting(false)} />}
    </>
  );
}

const TABS = [
  ["dados", "Dados"],
  ["membros", "Membros"],
  ["carteira", "Carteira"],
  ["consultas", "Consultas"],
  ["certificados", "Certificados"],
] as const;

export function EmpresaDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<string>("dados");
  const { data: org, isLoading } = useQuery({ queryKey: ["admin", "org", id], queryFn: () => adminApi<OrgDetail>(`/organizations/${id}`) });
  const toggle = useMutation({
    mutationFn: () => adminApi(`/organizations/${id}`, { method: "PATCH", body: { is_active: !org?.is_active } }),
    onSuccess: () => {
      toast.success(org?.is_active ? "Empresa desativada. Os membros perdem o acesso a ela." : "Empresa reativada.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => handleApiError(e),
  });

  if (isLoading || !org) return <Spinner />;
  return (
    <div className="space-y-6">
      <Link href="/empresas" className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Empresas
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{org.trade_name || org.legal_name}</h1>
          <p className="text-muted">
            {org.legal_name} · <span className="font-mono">{document(org.cnpj)}</span> · cadastrada em {date(org.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {org.is_active ? <Badge tone="green">Ativa</Badge> : <Badge tone="red">Inativa</Badge>}
          <Button
            variant={org.is_active ? "danger" : "primary"}
            size="sm"
            loading={toggle.isPending}
            onClick={() => (!org.is_active || confirm("Desativar esta empresa? Os membros perdem o acesso a ela.")) && toggle.mutate()}
          >
            {org.is_active ? <Ban className="size-4" /> : <CheckCircle2 className="size-4" />}
            {org.is_active ? "Desativar" : "Reativar"}
          </Button>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Saldo" value={money(org.balance_cents)} />
        <Stat label="Consultas (30 dias)" value={org.counts.consultas_30d} hint={`${money(org.counts.spent_30d)} gastos`} />
        <Stat label="Em estoque" value={org.counts.stock} />
        <Stat label="Notas emitidas" value={org.counts.notas} />
        <Stat label="Clientes atendidos" value={org.counts.clients} />
      </div>
      <div className="flex gap-1 overflow-x-auto rounded-xl bg-white p-1 ring-1 ring-line" role="tablist">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={clsx("rounded-lg px-4 py-2 text-sm font-semibold whitespace-nowrap", tab === k ? "bg-graphite text-white" : "text-muted hover:text-ink")}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "dados" && <DadosTab org={org} />}
      {tab === "membros" && <MembrosTab org={org} />}
      {tab === "carteira" && <CarteiraTab org={org} />}
      {tab === "consultas" && <ConsultasTable organization={org.id} />}
      {tab === "certificados" && (
        <Card title="Certificados ativos">
          {org.certificates.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">Nenhum certificado enviado.</p>
          ) : (
            <ul className="divide-y divide-line text-sm">
              {org.certificates.map((c) => (
                <li key={c.id} className="flex flex-wrap justify-between gap-2 py-3">
                  <span>
                    <strong>{c.holder_name}</strong> · {document(c.holder_document)} {c.client_name && <span className="text-muted">(cliente {c.client_name})</span>}
                  </span>
                  <span>
                    vence {date(c.not_after)} <Badge tone={c.days_to_expire < 30 ? "red" : "green"}>{c.days_to_expire} dias</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
