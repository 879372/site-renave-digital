import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link, useLocation, useSearch } from "wouter";
import { z } from "zod";

import { Logo } from "@/components/AppShell";
import { CompanyFields } from "@/components/CompanyFields";
import { LegalFooter } from "@/components/LegalFooter";
import { Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { maskDocument, maskPhone, onlyDigits } from "@/lib/format";
import { handleApiError } from "@/lib/forms";

function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_1.1fr]">
      <aside className="relative hidden overflow-hidden bg-navy p-12 text-white lg:flex lg:flex-col">
        <Logo light />
        <div className="my-auto max-w-md">
          <p className="mb-4 flex items-center gap-2 text-xs font-bold tracking-[0.16em] text-yellow uppercase">
            <span className="h-0.5 w-6 bg-yellow" /> Sua revenda conectada
          </p>
          <h2 className="font-display text-5xl leading-[1.05] font-bold text-white">
            Sua loja.
            <br />
            Tudo em
            <br />
            <span className="text-yellow">um só lugar.</span>
          </h2>
          <ul className="mt-8 space-y-3 text-[#c7d0ed]">
            {["Consultas veiculares completas", "Estoque RENAVE e comunicação de venda", "Emissão de NF-e de veículos"].map((t) => (
              <li key={t} className="flex items-center gap-3">
                <CheckCircle2 className="size-5 text-yellow" aria-hidden /> {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="flex items-center gap-2 text-xs text-[#c7d0ed]">
          <ShieldCheck className="size-4" aria-hidden /> Conexão protegida, dados cifrados e verificação em duas etapas.
        </p>
      </aside>
      <main className="flex items-center justify-center bg-white px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <h1 className="text-3xl font-bold">{title}</h1>
          {subtitle && <p className="mt-2 text-muted">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          <LegalFooter className="mt-10 justify-center" />
        </div>
      </main>
    </div>
  );
}

const loginSchema = z.object({ email: z.string().email("Informe um e-mail válido."), password: z.string().min(1, "Informe a senha.") });

export function LoginPage() {
  const { signIn } = useAuth();
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) });

  const submit = form.handleSubmit(async (values) => {
    try {
      const r = await api("/auth/login", { body: values, auth: false });
      if (r.mfa_required) setMfaToken(r.mfa_token);
      else await signIn(r.access);
    } catch (e) {
      handleApiError(e);
    }
  });

  const submitMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await api("/auth/login/mfa", { body: { mfa_token: mfaToken, code }, auth: false });
      await signIn(r.access);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  if (mfaToken) {
    return (
      <AuthLayout title="Verificação em duas etapas" subtitle="Digite o código de 6 dígitos do seu aplicativo autenticador ou um código de recuperação.">
        <form onSubmit={submitMfa} className="space-y-5">
          <Field label="Código" htmlFor="code">
            <Input id="code" inputMode="numeric" autoComplete="one-time-code" autoFocus value={code} onChange={(e) => setCode(e.target.value)} className="text-center text-2xl tracking-[0.4em]" maxLength={14} placeholder="000000" />
          </Field>
          <Button type="submit" className="w-full" loading={loading}>
            Confirmar e entrar
          </Button>
          <button type="button" className="w-full text-sm text-muted hover:text-ink" onClick={() => setMfaToken(null)}>
            Voltar
          </button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Entrar na plataforma"
      subtitle={
        <>
          Ainda não tem conta?{" "}
          <Link href="/cadastro" className="font-semibold text-blue">
            Cadastre sua loja
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label="E-mail" htmlFor="email" error={form.formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" autoFocus placeholder="voce@sualoja.com.br" aria-invalid={!!form.formState.errors.email} {...form.register("email")} />
        </Field>
        <Field label="Senha" htmlFor="password" error={form.formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" placeholder="Sua senha" aria-invalid={!!form.formState.errors.password} {...form.register("password")} />
        </Field>
        <div className="text-right">
          <Link href="/esqueci-senha" className="text-sm font-semibold text-blue">
            Esqueci minha senha
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Entrar
        </Button>
      </form>
    </AuthLayout>
  );
}

const registerSchema = z.object({
  full_name: z.string().min(3, "Informe seu nome completo."),
  email: z.string().email("E-mail inválido."),
  phone: z.string().refine((v) => onlyDigits(v).length >= 10, "Informe o telefone com DDD."),
  cpf: z.string().refine((v) => onlyDigits(v).length === 11, "CPF inválido."),
  password: z
    .string()
    .min(10, "Use pelo menos 10 caracteres.")
    .refine((v) => /[A-Za-z]/.test(v) && /\d/.test(v), "Combine letras e números."),
  password_confirm: z.string().min(1, "Repita a senha."),
  cnpj: z.string().min(14, "CNPJ inválido."),
  legal_name: z.string().min(3, "Informe a razão social."),
  trade_name: z.string().optional(),
  kind: z.enum(["revenda", "concessionaria", "despachante", "contador"]),
  uf: z.string().length(2, "Selecione a UF."),
  city: z.string().min(2, "Informe a cidade."),
  accept_terms: z.literal(true, { errorMap: () => ({ message: "É preciso aceitar os termos." }) }),
  marketing_opt_in: z.boolean().optional(),
}).refine((v) => v.password === v.password_confirm, { path: ["password_confirm"], message: "As senhas não conferem." });
type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { signIn } = useAuth();
  const [step, setStep] = useState(1);
  const form = useForm<RegisterValues>({ resolver: zodResolver(registerSchema), defaultValues: { kind: "revenda", uf: "" } });
  const { register, formState, setValue, trigger } = form;
  const e = formState.errors;

  const next = async () => {
    const ok = await trigger(["full_name", "email", "phone", "cpf", "password", "password_confirm"]);
    const { password, password_confirm } = form.getValues();
    if (password !== password_confirm) {
      form.setError("password_confirm", { message: "As senhas não conferem." });
      return;
    }
    if (ok) setStep(2);
  };

  const submit = form.handleSubmit(async (values) => {
    try {
      const r = await api("/auth/register", { body: values, auth: false });
      await signIn(r.access);
      toast.success("Conta criada! Bem-vindo ao RENAVE DIGITAL.");
    } catch (err) {
      handleApiError(err, form.setError);
      const fields = Object.keys((err as any)?.fields ?? {});
      if (fields.some((f) => ["full_name", "email", "phone", "cpf", "password", "password_confirm"].includes(f))) setStep(1);
    }
  });

  return (
    <AuthLayout
      title="Cadastre sua loja"
      subtitle={
        <>
          Já tem conta?{" "}
          <Link href="/entrar" className="font-semibold text-blue">
            Entrar
          </Link>
        </>
      }
    >
      <ol className="mb-6 flex gap-2 text-xs font-semibold" aria-label="Etapas">
        {["Seus dados", "Sua empresa"].map((label, i) => (
          <li key={label} className={`flex-1 border-t-4 pt-2 ${step > i ? "border-blue text-blue" : "border-line text-muted"}`}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {step === 1 ? (
          <div key="step-1" className="space-y-4">
            <Field label="Nome completo" htmlFor="full_name" error={e.full_name?.message}>
              <Input id="full_name" autoComplete="name" placeholder="Como está no seu documento" {...register("full_name")} aria-invalid={!!e.full_name} />
            </Field>
            <Field label="E-mail" htmlFor="email" error={e.email?.message}>
              <Input id="email" type="email" autoComplete="email" placeholder="voce@sualoja.com.br" {...register("email")} aria-invalid={!!e.email} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="CPF" htmlFor="cpf" error={e.cpf?.message}>
                <Input id="cpf" inputMode="numeric" placeholder="000.000.000-00" {...register("cpf", { onChange: (ev) => setValue("cpf", maskDocument(ev.target.value).slice(0, 14)) })} aria-invalid={!!e.cpf} />
              </Field>
              <Field label="Celular" htmlFor="phone" error={e.phone?.message}>
                <Input id="phone" type="tel" autoComplete="tel" placeholder="(84) 99999-9999" {...register("phone", { onChange: (ev) => setValue("phone", maskPhone(ev.target.value)) })} aria-invalid={!!e.phone} />
              </Field>
            </div>
            <Field label="Senha" htmlFor="password" error={e.password?.message} hint="Mínimo de 10 caracteres, com letras e números.">
              <Input id="password" type="password" autoComplete="new-password" placeholder="Crie uma senha forte" {...register("password")} aria-invalid={!!e.password} />
            </Field>
            <Field label="Confirme a senha" htmlFor="password_confirm" error={e.password_confirm?.message}>
              <Input id="password_confirm" type="password" autoComplete="new-password" placeholder="Digite a senha novamente" {...register("password_confirm")} aria-invalid={!!e.password_confirm} />
            </Field>
            <Button type="button" className="w-full" onClick={next}>
              Continuar
            </Button>
          </div>
        ) : (
          <div key="step-2" className="space-y-4">
            <CompanyFields form={form} />
            <label className="flex items-start gap-3 text-sm text-muted">
              <input type="checkbox" className="mt-1 size-4 accent-blue" {...register("accept_terms")} />
              <span>
                Li e aceito os{" "}
                <a href="/termos-de-uso" target="_blank" rel="noopener" className="font-semibold text-blue underline">
                  Termos de Uso
                </a>{" "}
                e a{" "}
                <a href="/politica-de-privacidade" target="_blank" rel="noopener" className="font-semibold text-blue underline">
                  Política de Privacidade
                </a>
                .
              </span>
            </label>
            {e.accept_terms && <p className="text-sm text-red">{e.accept_terms.message}</p>}
            <label className="flex items-start gap-3 text-sm text-muted">
              <input type="checkbox" className="mt-1 size-4 accent-blue" {...register("marketing_opt_in")} />
              <span>Quero receber novidades e ofertas do RENAVE DIGITAL (opcional).</span>
            </label>
            <div className="flex gap-3">
              <Button type="button" variant="secondary" onClick={() => setStep(1)}>
                Voltar
              </Button>
              <Button type="submit" className="flex-1" loading={formState.isSubmitting}>
                Criar conta
              </Button>
            </div>
          </div>
        )}
      </form>
    </AuthLayout>
  );
}

export function ForgotPage() {
  const [sent, setSent] = useState(false);
  const form = useForm<{ email: string }>();
  const submit = form.handleSubmit(async (values) => {
    try {
      await api("/auth/password/reset", { body: values, auth: false });
      setSent(true);
    } catch (e) {
      handleApiError(e);
    }
  });
  return (
    <AuthLayout title="Recuperar acesso" subtitle="Enviaremos um link para você criar uma nova senha.">
      {sent ? (
        <div className="rounded-xl bg-green-50 p-4 text-green">Se houver uma conta com este e-mail, você receberá o link em instantes.</div>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          <Field label="E-mail" htmlFor="email">
            <Input id="email" type="email" required autoComplete="email" placeholder="voce@sualoja.com.br" {...form.register("email")} />
          </Field>
          <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
            Enviar link
          </Button>
        </form>
      )}
      <Link href="/entrar" className="mt-6 block text-center text-sm font-semibold text-blue">
        Voltar para o login
      </Link>
    </AuthLayout>
  );
}

export function ResetPage() {
  const params = new URLSearchParams(useSearch());
  const [, navigate] = useLocation();
  const form = useForm<{ new_password: string; new_password_confirm: string }>();
  const submit = form.handleSubmit(async ({ new_password, new_password_confirm }) => {
    if (new_password !== new_password_confirm) {
      form.setError("new_password_confirm", { message: "As senhas não conferem." });
      return;
    }
    try {
      await api("/auth/password/reset/confirm", { body: { uid: params.get("uid"), token: params.get("token"), new_password, new_password_confirm }, auth: false });
      toast.success("Senha alterada. Entre com a nova senha.");
      navigate("/entrar");
    } catch (e) {
      handleApiError(e, form.setError);
    }
  });
  return (
    <AuthLayout title="Criar nova senha">
      <form onSubmit={submit} className="space-y-5">
        <Field label="Nova senha" htmlFor="np" error={form.formState.errors.new_password?.message} hint="Mínimo de 10 caracteres, com letras e números.">
          <Input id="np" type="password" required minLength={10} autoComplete="new-password" placeholder="Crie uma senha forte" {...form.register("new_password")} />
        </Field>
        <Field label="Confirme a nova senha" htmlFor="npc" error={form.formState.errors.new_password_confirm?.message}>
          <Input id="npc" type="password" required autoComplete="new-password" placeholder="Digite a senha novamente" {...form.register("new_password_confirm")} />
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Salvar senha
        </Button>
      </form>
    </AuthLayout>
  );
}

export function InvitePage() {
  const token = new URLSearchParams(useSearch()).get("token");
  const { status, reload, setOrganization } = useAuth();
  const [, navigate] = useLocation();
  const [loading, setLoading] = useState(false);

  if (status !== "authenticated") {
    return (
      <AuthLayout title="Você recebeu um convite" subtitle="Entre ou crie sua conta com o mesmo e-mail do convite e abra o link novamente.">
        <div className="flex gap-3">
          <Link href="/entrar" className="flex-1">
            <Button className="w-full">Entrar</Button>
          </Link>
          <Link href="/cadastro" className="flex-1">
            <Button variant="secondary" className="w-full">
              Criar conta
            </Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  const accept = async () => {
    setLoading(true);
    try {
      const r = await api("/organizations/invitations/accept", { body: { token } });
      await reload();
      setOrganization(r.organization);
      toast.success("Convite aceito!");
      navigate("/");
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="text-2xl font-bold">Aceitar convite</h1>
      <p className="mt-2 text-muted">Você terá acesso à empresa que enviou o convite.</p>
      <Button className="mt-6" onClick={accept} loading={loading}>
        Aceitar e continuar
      </Button>
    </div>
  );
}
