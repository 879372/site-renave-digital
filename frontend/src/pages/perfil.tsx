import QRCode from "qrcode";
import { Download, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Badge, Button, Card, Field, Input, Modal, PageHeader } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { maskPhone } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

function Dados() {
  const { user, reload } = useAuth();
  const form = useForm({ defaultValues: { full_name: user?.full_name ?? "", phone: user?.phone ?? "" } });
  const submit = form.handleSubmit(async (v) => {
    try {
      await api("/auth/me", { method: "PATCH", body: v });
      await reload();
      toast.success("Perfil atualizado.");
    } catch (e) {
      handleApiError(e, form.setError);
    }
  });
  return (
    <Card title="Seus dados">
      <form onSubmit={submit} className="space-y-4">
        <Field label="E-mail" htmlFor="email">
          <Input id="email" value={user?.email} disabled />
        </Field>
        <Field label="Nome completo" htmlFor="full_name">
          <Input id="full_name" placeholder="Seu nome completo" {...form.register("full_name", { required: true })} />
        </Field>
        <Field label="Celular" htmlFor="phone">
          <Input id="phone" type="tel" placeholder="(84) 99999-9999" {...form.register("phone", { onChange: (e) => form.setValue("phone", maskPhone(e.target.value)) })} />
        </Field>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Salvar
        </Button>
      </form>
    </Card>
  );
}

function Senha() {
  const form = useForm<{ current_password: string; new_password: string; new_password_confirm: string }>();
  const submit = form.handleSubmit(async (v) => {
    if (v.new_password !== v.new_password_confirm) {
      form.setError("new_password_confirm", { message: "As senhas não conferem." });
      return;
    }
    try {
      await api("/auth/password/change", { body: v });
      form.reset();
      toast.success("Senha alterada.");
    } catch (e) {
      handleApiError(e, form.setError);
    }
  });
  return (
    <Card title="Alterar senha">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Senha atual" htmlFor="cp" error={form.formState.errors.current_password?.message}>
          <Input id="cp" type="password" autoComplete="current-password" placeholder="Sua senha atual" {...form.register("current_password", { required: true })} />
        </Field>
        <Field label="Nova senha" htmlFor="np" error={form.formState.errors.new_password?.message} hint="Mínimo de 10 caracteres, com letras e números.">
          <Input id="np" type="password" autoComplete="new-password" placeholder="Crie uma senha forte" {...form.register("new_password", { required: true, minLength: 10 })} />
        </Field>
        <Field label="Confirme a nova senha" htmlFor="npc" error={form.formState.errors.new_password_confirm?.message}>
          <Input id="npc" type="password" autoComplete="new-password" placeholder="Digite a nova senha novamente" {...form.register("new_password_confirm", { required: true })} />
        </Field>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Alterar senha
        </Button>
      </form>
    </Card>
  );
}

function DoisFatores() {
  const { user, reload } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (setup) QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 200, color: { dark: "#0b1f5c" } }).then(setQr);
  }, [setup]);

  const run = async (fn: () => Promise<void>) => {
    setLoading(true);
    try {
      await fn();
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  };

  if (codes) {
    return (
      <Card title="Guarde seus códigos de recuperação">
        <p className="mb-4 text-sm text-muted">Cada código funciona uma vez, caso você perca o celular. Eles não serão exibidos novamente.</p>
        <ul className="grid grid-cols-2 gap-2 rounded-xl bg-pale p-4 font-mono">
          {codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <Button className="mt-4" onClick={() => setCodes(null)}>
          Já guardei
        </Button>
      </Card>
    );
  }

  return (
    <Card
      title="Verificação em duas etapas"
      action={user?.totp_enabled ? <Badge tone="green">Ativa</Badge> : <Badge tone="yellow">Desativada</Badge>}
      description="Proteja o acesso com um código do aplicativo autenticador (Google Authenticator, Microsoft Authenticator, Authy)."
    >
      {user?.totp_enabled ? (
        <div className="space-y-4">
          <Field label="Senha" htmlFor="pw">
            <Input id="pw" type="password" placeholder="Sua senha" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Código atual" htmlFor="code">
            <Input id="code" inputMode="numeric" placeholder="000000" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Button
            variant="danger"
            loading={loading}
            onClick={() =>
              run(async () => {
                await api("/auth/mfa/disable", { body: { password, code } });
                await reload();
                toast.success("Verificação em duas etapas desativada.");
              })
            }
          >
            Desativar
          </Button>
        </div>
      ) : setup ? (
        <div className="grid gap-6 sm:grid-cols-[200px_1fr]">
          {qr && <img src={qr} alt="QR code para o aplicativo autenticador" width={200} height={200} className="rounded-xl border border-line" />}
          <div className="space-y-4">
            <p className="text-sm text-muted">
              Escaneie o QR code ou digite a chave <code className="rounded bg-pale px-1 font-mono text-ink">{setup.secret}</code> e informe o código gerado.
            </p>
            <Field label="Código de 6 dígitos" htmlFor="code">
              <Input id="code" inputMode="numeric" autoComplete="one-time-code" placeholder="000000" value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <Button
              loading={loading}
              onClick={() =>
                run(async () => {
                  const r = await api("/auth/mfa/enable", { body: { code } });
                  setCodes(r.recovery_codes);
                  setSetup(null);
                  setCode("");
                  await reload();
                })
              }
            >
              Ativar
            </Button>
          </div>
        </div>
      ) : (
        <Button loading={loading} onClick={() => run(async () => setSetup(await api("/auth/mfa/setup", { method: "POST" })))}>
          <ShieldCheck className="size-4" /> Configurar agora
        </Button>
      )}
    </Card>
  );
}

function Privacidade() {
  const { user, reload, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);

  const toggleMarketing = async (value: boolean) => {
    try {
      await api("/auth/me", { method: "PATCH", body: { marketing_opt_in: value } });
      await reload();
      toast.success(value ? "Você passará a receber novidades." : "Você não receberá mais comunicações comerciais.");
    } catch (e) {
      handleApiError(e);
    }
  };

  const remove = async () => {
    setLoading(true);
    try {
      await api("/auth/me/delete", { body: { password, confirmation } });
      toast.success("Sua conta foi excluída.");
      await signOut();
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="Privacidade e dados" description="Seus direitos como titular de dados (LGPD, art. 18).">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-semibold">Baixar meus dados</p>
            <p className="text-sm text-muted">Arquivo com seus dados cadastrais, empresas, consultas e acessos.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => download("/auth/me/export").catch(handleApiError)}>
            <Download className="size-4" /> Baixar
          </Button>
        </div>
        <label className="flex items-start justify-between gap-3 border-t border-line pt-5">
          <span>
            <span className="block font-semibold">Comunicações comerciais</span>
            <span className="text-sm text-muted">Novidades e ofertas por e-mail ou WhatsApp. Você pode mudar quando quiser.</span>
          </span>
          <input type="checkbox" className="mt-1 size-5 accent-blue" checked={!!user?.marketing_opt_in} onChange={(e) => toggleMarketing(e.target.checked)} />
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <div>
            <p className="font-semibold">Excluir minha conta</p>
            <p className="text-sm text-muted">
              Seus dados pessoais serão anonimizados. Documentos fiscais e registros obrigatórios são mantidos pelo prazo legal.{" "}
              <a href="/politica-de-privacidade" target="_blank" rel="noopener" className="text-blue">
                Saiba mais
              </a>
            </p>
          </div>
          <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
            <Trash2 className="size-4" /> Excluir conta
          </Button>
        </div>
      </div>
      <Modal open={open} onOpenChange={setOpen} title="Excluir conta" description="Esta ação não pode ser desfeita. Empresas em que você é o único membro serão desativadas.">
        <div className="space-y-4">
          <Field label="Senha" htmlFor="del-pw">
            <Input id="del-pw" type="password" placeholder="Sua senha" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label='Digite "EXCLUIR" para confirmar' htmlFor="del-confirm">
            <Input id="del-confirm" placeholder="EXCLUIR" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
          </Field>
          <Button variant="danger" className="w-full" disabled={!password || confirmation.trim().toUpperCase() !== "EXCLUIR"} loading={loading} onClick={remove}>
            Excluir definitivamente
          </Button>
        </div>
      </Modal>
    </Card>
  );
}

export function PerfilPage() {
  return (
    <>
      <PageHeader title="Meu perfil" description="Dados de acesso e segurança da sua conta." />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Dados />
          <Senha />
        </div>
        <div className="space-y-6">
          <DoisFatores />
          <Privacidade />
        </div>
      </div>
    </>
  );
}
