import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { connectivity } from "@/lib/connectivity";

import { adminApi, adminRefresh, adminSession, type AdminUser } from "./api";

type State = {
  status: "loading" | "anonymous" | "authenticated";
  user: AdminUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<State | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<State["status"]>("loading");
  const [user, setUser] = useState<AdminUser | null>(null);

  const clear = useCallback(() => {
    adminSession.set(null);
    setUser(null);
    setStatus("anonymous");
    qc.removeQueries({ queryKey: ["admin"] });
  }, [qc]);

  const statusRef = useRef(status);
  statusRef.current = status;
  const bootstrap = useCallback(async () => {
    const data = await adminRefresh();
    await connectivity.settle();
    if (data) {
      setUser(data.user);
      setStatus("authenticated");
    } else if (!connectivity.unavailable()) clear();
  }, [clear]);

  useEffect(() => {
    adminSession.onExpired(clear);
    void bootstrap();
    return connectivity.onRecover(() => {
      if (statusRef.current === "loading") void bootstrap();
    });
  }, [bootstrap, clear]);

  const value = useMemo<State>(
    () => ({
      status,
      user,
      async signIn(email, password) {
        const r = await adminApi<{ access: string; user: AdminUser }>("/auth/login", { body: { email, password }, auth: false });
        adminSession.set(r.access);
        setUser(r.user);
        setStatus("authenticated");
      },
      async signOut() {
        try {
          await adminApi("/auth/logout", { method: "POST", auth: false });
        } finally {
          clear();
        }
      },
    }),
    [status, user, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAdmin() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAdmin fora do AdminAuthProvider");
  return ctx;
}
