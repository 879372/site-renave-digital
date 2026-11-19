import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, refreshAccess, session } from "./api";
import { connectivity, isConnectionError } from "./connectivity";

export type User = {
  id: string;
  email: string;
  full_name: string;
  cpf: string;
  phone: string;
  email_verified: boolean;
  totp_enabled: boolean;
  legal_version: string;
  marketing_opt_in: boolean;
};

export type OrgRef = { id: string; name: string; cnpj: string; kind: string; role: string; mfa_required: boolean };

type AuthState = {
  status: "loading" | "anonymous" | "authenticated";
  user: User | null;
  organizations: OrgRef[];
  organization: OrgRef | null;
  legalVersion: string;
  setOrganization: (id: string) => void;
  signIn: (access: string) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
  can: (perm: string) => boolean;
};

const PERMS: Record<string, string[]> = {
  owner: ["*"],
  admin: ["org.manage", "members.manage", "vault.manage", "wallet.manage", "audit.view", "consultas.run", "renave.operate", "comunicacao.operate", "fiscal.emit", "fiscal.configure", "clients.manage"],
  operator: ["consultas.run", "renave.operate", "comunicacao.operate", "fiscal.emit", "clients.manage"],
  finance: ["wallet.manage", "fiscal.emit", "audit.view"],
  viewer: [],
};

const ORG_KEY = "rd.org";
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<OrgRef[]>([]);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [legalVersion, setLegalVersion] = useState("");

  const loadMe = useCallback(async () => {
    const me = await api<{ user: User; organizations: OrgRef[]; legal_version: string }>("/auth/me");
    setUser(me.user);
    setLegalVersion(me.legal_version);
    setOrganizations(me.organizations);
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(ORG_KEY);
    } catch {
      /* sem storage */
    }
    const chosen = me.organizations.find((o) => o.id === saved)?.id ?? me.organizations[0]?.id ?? null;
    session.setOrganization(chosen);
    setOrgId(chosen);
    setStatus("authenticated");
  }, []);

  const clear = useCallback(() => {
    session.setAccess(null);
    session.setOrganization(null);
    setUser(null);
    setOrganizations([]);
    setOrgId(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  // Sem rede ou sem servidor não dá para saber se a sessão é válida: fica em "loading"
  // (a tela de conexão aparece por cima) e tenta de novo quando a conexão voltar.
  const statusRef = useRef(status);
  statusRef.current = status;
  const bootstrap = useCallback(async () => {
    const token = await refreshAccess();
    await connectivity.settle();
    if (token) {
      try {
        await loadMe();
      } catch (e) {
        if (!isConnectionError(e)) clear();
      }
    } else if (!connectivity.unavailable()) clear();
  }, [clear, loadMe]);

  useEffect(() => {
    session.onExpired(clear);
    void bootstrap();
    return connectivity.onRecover(() => {
      if (statusRef.current === "loading") void bootstrap();
    });
  }, [bootstrap, clear]);

  const value = useMemo<AuthState>(() => {
    const organization = organizations.find((o) => o.id === orgId) ?? null;
    return {
      status,
      user,
      organizations,
      organization,
      legalVersion,
      setOrganization(id) {
        session.setOrganization(id);
        setOrgId(id);
        try {
          localStorage.setItem(ORG_KEY, id);
        } catch {
          /* sem storage */
        }
        queryClient.clear();
      },
      async signIn(access) {
        session.setAccess(access);
        await loadMe();
      },
      async signOut() {
        try {
          await api("/auth/logout", { method: "POST", auth: false });
        } finally {
          clear();
        }
      },
      reload: loadMe,
      can(perm) {
        if (!organization) return false;
        if (perm === "view") return true;
        const granted = PERMS[organization.role] ?? [];
        return granted.includes("*") || granted.includes(perm);
      },
    };
  }, [status, user, organizations, orgId, legalVersion, loadMe, clear, queryClient]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
