import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, KeyRound, Mail, ShieldOff, UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link, useParams } from "wouter";

import { Badge, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner } from "@/components/ui";
import { date, dateTime, document, ROLE_LABEL } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

import { adminApi } from "../api";
import { useAdmin } from "../auth";
import { DATE_FILTERS, OrgCell, ResourceTable, STATUS_OPTIONS } from "../components";

type UserRow = {
  id: string;
  email: string;
  full_name: string;
  cpf: string;
  phone: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  marketing_opt_in: boolean;
  legal_version: string;
  terms_accepted_at: string | null;
  last_login: string | null;
  date_joined: string;
  anonymized_at: string | null;
  organizations_count: number;
};

const userColumns = [
  {
    header: "Usuário",
    cell: (u: UserRow) => (
      <Link href={`/usuarios/${u.id}`} className="block">
        <span className="block font-semibold text-blue hover:underline">{u.full_name}</span>
        <span className="text-xs text-muted">{u.email}</span>
      </Link>
    ),
  },
  { header: "CPF", cell: (u: UserRow) => <span className="font-mono text-xs">{u.cpf ? document(u.cpf) : "—"}</span> },
  { header: "Empresas", cell: (u: UserRow) => u.organizations_count, className: "text-right" },
  { header: "2FA", cell: (u: UserRow) => (u.totp_enabled ? <Badge tone="green">Ativo</Badge> : <Badge>Não</Badge>) },
  { header: "Último acesso", cell: (u: UserRow) => dateTime(u.last_login), className: "whitespace-nowrap" },
  {
    header: "Situação",
    cell: (u: UserRow) => (
      <div className="flex flex-wrap gap-1">
        {u.anonymized_at ? <Badge tone="gray">Excluído (LGPD)</Badge> : u.is_active ? <Badge tone="green">Ativo</Badge> : <Badge tone="red">Bloqueado</Badge>}
        {u.is_superuser ? <Badge tone="blue">Admin geral</Badge> : u.is_staff ? <Badge tone="blue">Equipe</Badge> : null}
      </div>
    ),
  },
];

export function UsuariosPage() {
  return (
    <>
      <PageHeader title="Usuários" description="Todos os usuários das empresas clientes." />
      <ResourceTable<UserRow>
        endpoint="/users"
        searchPlaceholder="Nome, e-mail, CPF ou telefone"
        filters={[{ name: "is_active", label: "Situação", options: STATUS_OPTIONS.active }, ...DATE_FILTERS]}
        columns={userColumns}
      />
    </>
  );
}

export function UsuarioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { user: me } = useAdmin();
  const { data: u, isLoading } = useQuery({ queryKey: ["admin", "user", id], queryFn: () => adminApi<UserRow & { memberships: any[]; recent_activity: any[] }>(`/users/${id}`) });
  const act = useMutation({
    mutationFn: ({ path, body, method }: { path: string; body?: object; method?: string }) => adminApi(`/users/${id}${path}`, { method: method ?? "POST", body }),
    onSuccess: (_, v) => {
      toast.success(v.path === "/send-password-reset" ? "Link de redefinição enviado por e-mail." : "Usuário atualizado.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => handleApiError(e),
  });

  if (isLoading || !u) return <Spinner />;
  return (
    <div className="space-y-6">
      <Link href={u.is_staff ? "/equipe" : "/usuarios"} className="inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Voltar
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">{u.full_name}</h1>
          <p className="text-muted">
            {u.email} · cadastro em {date(u.date_joined)} · último acesso {dateTime(u.last_login)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => act.mutate({ path: "/send-password-reset" })} disabled={!u.is_active}>
            <Mail className="size-4" /> Enviar redefinição de senha
          </Button>
          {u.totp_enabled && (
            <Button size="sm" variant="secondary" onClick={() => confirm("Desativar o 2FA deste usuário? Ele poderá configurar de novo no perfil.") && act.mutate({ path: "/reset-mfa" })}>
              <ShieldOff className="size-4" /> Redefinir 2FA
            </Button>
          )}
          {u.id !== me?.id && !u.anonymized_at && (
            <Button
              size="sm"
              variant={u.is_active ? "danger" : "primary"}
              onClick={() => (!u.is_active || confirm("Bloquear o acesso deste usuário?")) && act.mutate({ path: "", method: "PATCH", body: { is_active: !u.is_active } })}
            >
              {u.is_active ? "Bloquear acesso" : "Desbloquear"}
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card title="Empresas">
            {u.memberships.length === 0 ? (
              <p className="text-sm text-muted">Sem vínculos com empresas.</p>
            ) : (
              <ul className="divide-y divide-line">
                {u.memberships.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 py-3">
                    <OrgCell org={m.organization} />
                    <span className="text-sm">
                      {ROLE_LABEL[m.role]} {!m.is_active && <Badge tone="red">suspenso</Badge>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Atividade recente">
            {u.recent_activity.length === 0 ? (
              <p className="text-sm text-muted">Nenhuma atividade registrada.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {u.recent_activity.map((e) => (
                  <li key={e.id} className="flex justify-between gap-3">
                    <span className="font-mono text-xs">{e.action}</span>
                    <span className="text-muted">
                      {dateTime(e.created_at)} · {e.ip ?? "—"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <Card title="Dados">
          <dl className="space-y-2 text-sm">
            {[
              ["CPF", u.cpf ? document(u.cpf) : "—"],
              ["Telefone", u.phone || "—"],
              ["Verificação em duas etapas", u.totp_enabled ? "Ativa" : "Desativada"],
              ["Comunicações comerciais", u.marketing_opt_in ? "Aceita" : "Não aceita"],
              ["Termos aceitos", u.terms_accepted_at ? `${dateTime(u.terms_accepted_at)} (v. ${u.legal_version})` : "—"],
              ["Situação", u.anonymized_at ? `Excluído em ${date(u.anonymized_at)}` : u.is_active ? "Ativo" : "Bloqueado"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-line/60 pb-2">
                <dt className="text-muted">{k}</dt>
                <dd className="text-right font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </div>
  );
}

function NewStaffModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const form = useForm<{ email: string; full_name: string; password: string; is_superuser: boolean }>();
  const submit = form.handleSubmit(async (v) => {
    try {
      await adminApi("/users/staff", { body: v });
      toast.success("Membro da equipe criado. Envie a senha por um canal seguro.");
      qc.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    } catch (e) {
      handleApiError(e, form.setError);
    }
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Novo membro da equipe" description="Acessa este painel com e-mail e senha em /admin.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Nome completo" htmlFor="st-name" error={form.formState.errors.full_name?.message}>
          <Input id="st-name" placeholder="Nome da pessoa" required {...form.register("full_name")} />
        </Field>
        <Field label="E-mail" htmlFor="st-email" error={form.formState.errors.email?.message}>
          <Input id="st-email" type="email" placeholder="pessoa@kaiobez.com.br" required {...form.register("email")} />
        </Field>
        <Field label="Senha inicial" htmlFor="st-pass" error={form.formState.errors.password?.message} hint="Mínimo de 10 caracteres, com letras e números.">
          <Input id="st-pass" type="password" autoComplete="new-password" placeholder="Senha forte" required minLength={10} {...form.register("password")} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-blue" {...form.register("is_superuser")} /> Administrador geral (pode gerenciar a equipe)
        </label>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Criar acesso
        </Button>
      </form>
    </Modal>
  );
}

export function EquipePage() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { user: me } = useAdmin();
  const role = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) => adminApi(`/users/${id}/staff-role`, { body: { role: value } }),
    onSuccess: () => {
      toast.success("Acesso atualizado.");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => handleApiError(e),
  });
  return (
    <>
      <PageHeader
        title="Equipe administrativa"
        description="Pessoas com acesso a este painel."
        action={
          <Button onClick={() => setOpen(true)}>
            <UserPlus className="size-4" /> Novo membro
          </Button>
        }
      />
      <ResourceTable<UserRow>
        endpoint="/users"
        queryKey="staff"
        fixedParams={{ staff: "true" }}
        searchPlaceholder="Nome ou e-mail"
        columns={[
          userColumns[0],
          { header: "Último acesso", cell: (u) => dateTime(u.last_login) },
          {
            header: "Acesso",
            cell: (u) =>
              u.id === me?.id ? (
                <Badge tone="blue">{u.is_superuser ? "Administrador geral" : "Equipe"} (você)</Badge>
              ) : (
                <Select className="h-9 w-48" value={u.is_superuser ? "superuser" : "staff"} onChange={(e) => role.mutate({ id: u.id, value: e.target.value })}>
                  <option value="staff">Equipe</option>
                  <option value="superuser">Administrador geral</option>
                  <option value="none">Remover acesso</option>
                </Select>
              ),
          },
          { header: "Situação", cell: (u) => (u.is_active ? <Badge tone="green">Ativo</Badge> : <Badge tone="red">Bloqueado</Badge>) },
          {
            header: "",
            cell: (u) => (
              <Link href={`/usuarios/${u.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-blue">
                <KeyRound className="size-4" /> Gerenciar
              </Link>
            ),
          },
        ]}
      />
      {open && <NewStaffModal onClose={() => setOpen(false)} />}
    </>
  );
}
