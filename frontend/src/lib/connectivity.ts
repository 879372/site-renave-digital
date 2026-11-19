/**
 * Estado da conexão: internet do usuário e disponibilidade da API.
 *
 * - "offline": o navegador diz que não há rede (eventos online/offline).
 * - "server": a API não respondeu ou respondeu 502/503/504. Uma falha isolada não basta:
 *   antes de marcar o servidor como fora do ar, confirmamos com /api/health/live.
 *   Enquanto estiver fora, checamos de novo a cada POLL_MS e avisamos quem assinou onRecover.
 */
import { useSyncExternalStore } from "react";

export type Connectivity = { online: boolean; serverDown: boolean };

const POLL_MS = 8_000;
const HEALTH_URL = "/api/health/live";

let state: Connectivity = { online: typeof navigator === "undefined" ? true : navigator.onLine, serverDown: false };
const listeners = new Set<() => void>();
const recoverListeners = new Set<() => void>();
let checking: Promise<boolean> | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function set(next: Partial<Connectivity>) {
  const before = state;
  state = { ...state, ...next };
  if (before.online === state.online && before.serverDown === state.serverDown) return;
  listeners.forEach((l) => l());
  const wasBroken = !before.online || before.serverDown;
  const isHealthy = state.online && !state.serverDown;
  if (wasBroken && isHealthy) recoverListeners.forEach((l) => l());
}

async function healthy(): Promise<boolean> {
  try {
    const r = await fetch(HEALTH_URL, { cache: "no-store", credentials: "omit" });
    return r.ok;
  } catch {
    return false;
  }
}

function schedulePoll() {
  if (pollTimer) return;
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    await checkServer();
  }, POLL_MS);
}

/** Confere a API agora. Devolve true se ela respondeu. */
export function checkServer(): Promise<boolean> {
  if (!checking) {
    checking = healthy()
      .then((ok) => {
        if (!navigator.onLine) {
          set({ online: false });
          return false;
        }
        set({ serverDown: !ok });
        if (!ok) schedulePoll();
        return ok;
      })
      .finally(() => {
        checking = null;
      });
  }
  return checking;
}

export const connectivity = {
  get: () => state,
  /** Pedido falhou por rede ou gateway (502/503/504): confirma antes de mostrar a tela. */
  reportFailure() {
    if (!navigator.onLine) set({ online: false });
    else void checkServer();
  },
  /** Qualquer resposta da API prova que o servidor está de pé. */
  reportSuccess() {
    if (state.serverDown) set({ serverDown: false });
  },
  /** true se o último problema conhecido é de conexão (não de credenciais). */
  unavailable: () => !state.online || state.serverDown || checking !== null,
  /** Aguarda a checagem em andamento, se houver. */
  settle: () => checking ?? Promise.resolve(!state.serverDown),
  onRecover(fn: () => void) {
    recoverListeners.add(fn);
    return () => {
      recoverListeners.delete(fn);
    };
  },
};

if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    set({ online: true });
    if (state.serverDown) void checkServer();
  });
  window.addEventListener("offline", () => set({ online: false }));
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useConnectivity(): Connectivity {
  return useSyncExternalStore(subscribe, connectivity.get, connectivity.get);
}

/** Erro de conexão (sem rede ou servidor indisponível), não de regra de negócio. */
export function isConnectionError(e: unknown): boolean {
  const status = (e as { status?: number } | null)?.status;
  return status === 0 || status === 502 || status === 503 || status === 504;
}
