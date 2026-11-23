import clsx from "clsx";
import {
  Activity,
  Building2,
  Car,
  CreditCard,
  FileText,
  Layers,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Receipt,
  ReceiptText,
  ScrollText,
  Search,
  Send,
  ShieldCheck,
  Tags,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { lazy, Suspense, useState, type ComponentType, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, Route, Switch, useLocation } from "wouter";

import { NotFoundPage } from "@/components/StatusScreen";
import { Button, Field, Input, Spinner } from "@/components/ui";
import { handleApiError } from "@/lib/forms";

import { AdminAuthProvider, useAdmin } from "./auth";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const page = <M extends Record<string, any>>(loader: () => Promise<M>, name: keyof M & string) =>
  lazy(() => loader().then((m) => ({ default: m[name] as ComponentType<any> })));

const Dashboard = page(() => import("./pages/dashboard"), "AdminDashboard");
const Empresas = page(() => import("./pages/empresas"), "EmpresasPage");
const EmpresaDetail = page(() => import("./pages/empresas"), "EmpresaDetailPage");
const Usuarios = page(() => import("./pages/usuarios"), "UsuariosPage");
const UsuarioDetail = page(() => import("./pages/usuarios"), "UsuarioDetailPage");
const Equipe = page(() => import("./pages/usuarios"), "EquipePage");
const Recargas = page(() => import("./pages/financeiro"), "RecargasPage");
const Extrato = page(() => import("./pages/financeiro"), "ExtratoPage");
const Precos = page(() => import("./pages/financeiro"), "PrecosPage");
const Assinaturas = page(() => import("./pages/assinaturas"), "AssinaturasPage");
const FaturasAdmin = page(() => import("./pages/assinaturas"), "FaturasAdminPage");
const PlanosAdmin = page(() => import("./pages/assinaturas"), "PlanosAdminPage");
const Produtos = page(() => import("./pages/catalogo"), "ProdutosPage");
const Consultas = page(() => import("./pages/operacoes"), "ConsultasAdminPage");
const Notas = page(() => import("./pages/operacoes"), "NotasAdminPage");
const Estoque = page(() => import("./pages/operacoes"), "EstoqueAdminPage");
const Comunicacoes = page(() => import("./pages/operacoes"), "ComunicacoesAdminPage");
const Certificados = page(() => import("./pages/operacoes"), "CertificadosAdminPage");
const Integracoes = page(() => import("./pages/sistema"), "IntegracoesPage");
const Auditoria = page(() => import("./pages/sistema"), "AuditoriaAdminPage");

const NAV: { group: string; items: { href: string; label: string; icon: ComponentType<{ className?: string }>; superuser?: boolean }[] }[] = [
  { group: "Visão geral", items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }] },
  {
    group: "Clientes",
    items: [
      { href: "/empresas", label: "Empresas", icon: Building2 },
      { href: "/usuarios", label: "Usuários", icon: Users },
    ],
  },
  {
    group: "Financeiro",
    items: [
      { href: "/assinaturas", label: "Assinaturas", icon: CreditCard },
      { href: "/faturas", label: "Faturas", icon: ReceiptText },
      { href: "/planos", label: "Planos", icon: Layers },
      { href: "/recargas", label: "Recargas", icon: Wallet },
      { href: "/extrato", label: "Movimentações", icon: Receipt },
      { href: "/precos", label: "Preços de serviços", icon: Tags },
      { href: "/produtos", label: "Produtos de consulta", icon: Package },
    ],
  },
  {
    group: "Operações",
    items: [
      { href: "/consultas", label: "Consultas", icon: Search },
      { href: "/estoque", label: "Estoque RENAVE", icon: Car },
      { href: "/comunicacoes", label: "Comunicações de venda", icon: Send },
      { href: "/notas", label: "Notas fiscais", icon: FileText },
      { href: "/certificados", label: "Certificados", icon: KeyRound },
    ],
  },
  {
    group: "Sistema",
    items: [
      { href: "/integracoes", label: "Integrações", icon: Activity },
      { href: "/auditoria", label: "Auditoria", icon: ScrollText },
      { href: "/equipe", label: "Equipe admin", icon: ShieldCheck, superuser: true },
    ],
  },
];

function AdminLogo() {
  return (
    <span className="flex items-center gap-2.5 leading-none">
      <img src="/simbolo.svg" alt="" width={30} height={30} />
      <span className="text-[15px] font-semibold tracking-tight text-white">
        REVENDA <span className="text-mint">DIGITAL</span>
        <span className="mt-1 block text-[11px] font-medium text-[#a1a1aa]">Painel administrativo</span>
      </span>
    </span>
  );
}

function LoginPage() {
  const { signIn } = useAdmin();
  const form = useForm<{ email: string; password: string }>();
  const submit = form.handleSubmit(async ({ email, password }) => {
    try {
      await signIn(email, password);
    } catch (e) {
      handleApiError(e);
    }
  });
  return (
    <div className="grid min-h-dvh place-items-center bg-ink px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <AdminLogo />
        </div>
        <form onSubmit={submit} className="space-y-5 rounded-xl bg-white p-7 shadow-2xl">
          <div>
            <h1 className="text-2xl font-semibold">Acesso administrativo</h1>
            <p className="mt-1 text-sm text-muted">Área restrita à equipe REVENDA DIGITAL.</p>
          </div>
          <Field label="E-mail" htmlFor="admin-email">
            <Input id="admin-email" type="email" autoComplete="username" placeholder="voce@kaibez.com.br" autoFocus required {...form.register("email")} />
          </Field>
          <Field label="Senha" htmlFor="admin-password">
            <Input id="admin-password" type="password" autoComplete="current-password" placeholder="Sua senha" required {...form.register("password")} />
          </Field>
          <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
            Entrar
          </Button>
        </form>
      </div>
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAdmin();
  const [location] = useLocation();
  const [open, setOpen] = useState(false);
  const nav = (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div className="flex items-center justify-between px-1 pt-1">
        <Link href="/" onClick={() => setOpen(false)}>
          <AdminLogo />
        </Link>
        <button className="rounded-lg p-1 text-white lg:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu">
          <X className="size-5" />
        </button>
      </div>
      <nav className="space-y-5" aria-label="Administração">
        {NAV.map((g) => (
          <div key={g.group}>
            <p className="mb-1 px-3 text-[11px] font-semibold tracking-[0.14em] text-[#8a97c4] uppercase">{g.group}</p>
            {g.items
              .filter((i) => !i.superuser || user?.is_superuser)
              .map(({ href, label, icon: Icon }) => {
                const active = href === "/" ? location === "/" : location.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={clsx(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                      active ? "bg-white/10 text-white" : "text-[#a1a1aa] hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon className={clsx("size-4", active && "text-mint")} />
                    {label}
                  </Link>
                );
              })}
          </div>
        ))}
      </nav>
      <div className="mt-auto rounded-xl bg-white/5 p-3 text-xs text-[#a1a1aa]">
        <p className="truncate font-semibold text-white">{user?.full_name}</p>
        <p className="truncate">{user?.email}</p>
        <p className="mt-1 text-mint">{user?.is_superuser ? "Administrador geral" : "Equipe"}</p>
        <button onClick={() => signOut()} className="mt-3 flex items-center gap-2 font-semibold text-white hover:text-mint">
          <LogOut className="size-4" /> Sair
        </button>
      </div>
    </div>
  );
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[250px_1fr]">
      <aside className="sticky top-0 hidden h-dvh bg-ink lg:block">{nav}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-ink">{nav}</aside>
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur lg:hidden">
          <button className="rounded-lg p-2" onClick={() => setOpen(true)} aria-label="Abrir menu">
            <Menu className="size-5" />
          </button>
          <span className="font-display font-semibold">Painel administrativo</span>
        </header>
        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:py-8">
          <Suspense fallback={<Spinner />}>{children}</Suspense>
        </main>
      </div>
    </div>
  );
}

function Routes() {
  const { status, user } = useAdmin();
  if (status === "loading") return <Spinner label="Abrindo o painel…" />;
  if (status === "anonymous") return <LoginPage />;
  return (
    <Shell>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/empresas" component={Empresas} />
        <Route path="/empresas/:id" component={EmpresaDetail} />
        <Route path="/usuarios" component={Usuarios} />
        <Route path="/usuarios/:id" component={UsuarioDetail} />
        <Route path="/assinaturas" component={Assinaturas} />
        <Route path="/faturas" component={FaturasAdmin} />
        <Route path="/planos" component={PlanosAdmin} />
        <Route path="/recargas" component={Recargas} />
        <Route path="/extrato" component={Extrato} />
        <Route path="/precos" component={Precos} />
        <Route path="/produtos" component={Produtos} />
        <Route path="/consultas" component={Consultas} />
        <Route path="/notas" component={Notas} />
        <Route path="/estoque" component={Estoque} />
        <Route path="/comunicacoes" component={Comunicacoes} />
        <Route path="/certificados" component={Certificados} />
        <Route path="/integracoes" component={Integracoes} />
        <Route path="/auditoria" component={Auditoria} />
        {user?.is_superuser && <Route path="/equipe" component={Equipe} />}
        <Route>
          <NotFoundPage embedded homeLabel="Ir para o painel" />
        </Route>
      </Switch>
    </Shell>
  );
}

export function AdminApp() {
  return (
    <AdminAuthProvider>
      <Routes />
    </AdminAuthProvider>
  );
}

