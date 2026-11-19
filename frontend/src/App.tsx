import { lazy, Suspense, useState, type ComponentType } from "react";
import { Redirect, Route, Switch, useLocation } from "wouter";

import { AppShell } from "./components/AppShell";
import { NotFoundPage } from "./components/StatusScreen";
import { Button, Modal, Spinner } from "./components/ui";
import { api } from "./lib/api";
import { useAuth } from "./lib/auth";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const page = <M extends Record<string, any>>(loader: () => Promise<M>, name: keyof M & string) =>
  lazy(() => loader().then((m) => ({ default: m[name] as ComponentType<any> })));

const Login = page(() => import("./pages/auth"), "LoginPage");
const Register = page(() => import("./pages/auth"), "RegisterPage");
const Forgot = page(() => import("./pages/auth"), "ForgotPage");
const Reset = page(() => import("./pages/auth"), "ResetPage");
const Invite = page(() => import("./pages/auth"), "InvitePage");
const Dashboard = page(() => import("./pages/dashboard"), "DashboardPage");
const Consultas = page(() => import("./pages/consultas"), "ConsultasPage");
const ConsultaDetail = page(() => import("./pages/consultas"), "ConsultaDetailPage");
const Estoque = page(() => import("./pages/estoque"), "EstoquePage");
const EstoqueDetail = page(() => import("./pages/estoque"), "EstoqueDetailPage");
const Comunicacao = page(() => import("./pages/comunicacao"), "ComunicacaoPage");
const Notas = page(() => import("./pages/notas"), "NotasPage");
const NotaDetail = page(() => import("./pages/notas"), "NotaDetailPage");
const Carteira = page(() => import("./pages/carteira"), "CarteiraPage");
const Empresa = page(() => import("./pages/empresa"), "EmpresaPage");
const Perfil = page(() => import("./pages/perfil"), "PerfilPage");
const Auditoria = page(() => import("./pages/auditoria"), "AuditoriaPage");
const Terms = page(() => import("./pages/legal"), "TermsPage");
const Admin = page(() => import("./admin/AdminApp"), "AdminApp");
const Privacy = page(() => import("./pages/legal"), "PrivacyPage");

/** Rotas que existem para quem está logado: sem sessão, mandam para o login em vez do 404. */
const PRIVATE_ROUTES = /^\/(consultas|estoque|comunicacao-venda|notas|carteira|empresa|perfil|auditoria)(\/|$)/;

function LegalGate() {
  const { user, legalVersion, reload } = useAuth();
  const [loading, setLoading] = useState(false);
  if (!user || !legalVersion || user.legal_version === legalVersion) return null;
  const accept = async () => {
    setLoading(true);
    try {
      await api("/auth/legal/accept", { method: "POST" });
      await reload();
    } finally {
      setLoading(false);
    }
  };
  return (
    <Modal open onOpenChange={() => {}} title="Atualizamos nossos termos" description="Para continuar usando a plataforma, leia e aceite a nova versão dos documentos.">
      <ul className="mb-5 space-y-2 text-sm">
        <li>
          <a href="/termos-de-uso" target="_blank" rel="noopener" className="font-semibold text-blue">
            Termos de Uso
          </a>
        </li>
        <li>
          <a href="/politica-de-privacidade" target="_blank" rel="noopener" className="font-semibold text-blue">
            Política de Privacidade
          </a>
        </li>
      </ul>
      <Button className="w-full" onClick={accept} loading={loading}>
        Li e aceito
      </Button>
    </Modal>
  );
}

export function App() {
  const { status, organization } = useAuth();
  const [location] = useLocation();

  if (location === "/admin" || location.startsWith("/admin/")) {
    return (
      <Route path="/admin" nest>
        <Suspense fallback={<Spinner />}>
          <Admin />
        </Suspense>
      </Route>
    );
  }

  if (location === "/termos-de-uso" || location === "/politica-de-privacidade") {
    return <Suspense fallback={<Spinner />}>{location === "/termos-de-uso" ? <Terms /> : <Privacy />}</Suspense>;
  }

  if (status === "loading") return <Spinner label="Abrindo sua sessão…" />;

  if (status === "anonymous") {
    return (
      <Suspense fallback={<Spinner />}>
        <Switch>
          <Route path="/cadastro" component={Register} />
          <Route path="/esqueci-senha" component={Forgot} />
          <Route path="/redefinir-senha" component={Reset} />
          <Route path="/convite" component={Invite} />
          <Route path="/entrar" component={Login} />
          <Route>{location === "/" || PRIVATE_ROUTES.test(location) ? <Redirect to="/entrar" /> : <NotFoundPage homeLabel="Ir para o login" />}</Route>
        </Switch>
      </Suspense>
    );
  }

  if (!organization) {
    return (
      <Suspense fallback={<Spinner />}>
        <Switch>
          <Route path="/convite" component={Invite} />
          <Route>
            <div className="mx-auto max-w-md p-10 text-center">
              <h1 className="text-2xl font-bold">Nenhuma empresa vinculada</h1>
              <p className="mt-2 text-muted">Peça ao responsável pela empresa um convite de acesso.</p>
            </div>
          </Route>
        </Switch>
      </Suspense>
    );
  }

  return (
    <AppShell>
      <LegalGate />
      <Suspense fallback={<Spinner />}>
        <Switch>
          <Route path="/" component={Dashboard} />
          <Route path="/consultas" component={Consultas} />
          <Route path="/consultas/:id" component={ConsultaDetail} />
          <Route path="/estoque" component={Estoque} />
          <Route path="/estoque/:id" component={EstoqueDetail} />
          <Route path="/comunicacao-venda" component={Comunicacao} />
          <Route path="/notas" component={Notas} />
          <Route path="/notas/:id" component={NotaDetail} />
          <Route path="/carteira" component={Carteira} />
          <Route path="/empresa" component={Empresa} />
          <Route path="/perfil" component={Perfil} />
          <Route path="/auditoria" component={Auditoria} />
          <Route path="/convite" component={Invite} />
          <Route path="/entrar">
            <Redirect to="/" />
          </Route>
          <Route path="/cadastro">
            <Redirect to="/" />
          </Route>
          <Route>
            <NotFoundPage embedded />
          </Route>
        </Switch>
      </Suspense>
    </AppShell>
  );
}
