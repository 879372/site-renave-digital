/**
 * Cliente da API.
 * - Access token só em memória (nunca localStorage).
 * - Refresh em cookie httpOnly; renovação automática única (single-flight) ao receber 401.
 * - Cabeçalho X-Organization com a empresa ativa.
 * - Falha de rede ou 502/503/504 avisa o estado de conexão (tela de sem internet / servidor fora do ar)
 *   e nunca derruba a sessão: sem servidor, não dá para saber se o login expirou.
 */

import { connectivity } from "./connectivity";
import { apiUrl, CREDENTIALS } from "./endpoint";

const GATEWAY_DOWN = new Set([502, 503, 504]);

export class ApiError extends Error {
  status: number;
  code: string;
  fields?: Record<string, string[] | string>;
  extra: Record<string, unknown>;

  constructor(status: number, body: any) {
    const err = body?.error ?? {};
    super(err.message || "Não foi possível concluir a operação.");
    this.status = status;
    this.code = err.code || "error";
    this.fields = err.fields;
    this.extra = err;
  }

  fieldError(name: string): string | undefined {
    const value = this.fields?.[name];
    return Array.isArray(value) ? value[0] : value;
  }
}

let accessToken: string | null = null;
let organizationId: string | null = null;
let refreshing: Promise<string | null> | null = null;
let onSessionExpired: () => void = () => {};

export const session = {
  setAccess(token: string | null) {
    accessToken = token;
  },
  setOrganization(id: string | null) {
    organizationId = id;
  },
  get organization() {
    return organizationId;
  },
  onExpired(fn: () => void) {
    onSessionExpired = fn;
  },
};

/** fetch que reporta falhas de rede/gateway ao estado de conexão e converte erro de rede em ApiError(0). */
export async function fetchApi(input: URL | string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch {
    connectivity.reportFailure();
    const offline = !navigator.onLine;
    throw new ApiError(0, {
      error: {
        code: offline ? "offline" : "unavailable",
        message: offline ? "Você está sem internet. Verifique sua conexão." : "Não conseguimos falar com o servidor. Tente novamente em instantes.",
      },
    });
  }
  if (GATEWAY_DOWN.has(response.status)) connectivity.reportFailure();
  else connectivity.reportSuccess();
  return response;
}

/** Monta o ApiError de uma resposta não-ok (o corpo pode estar vazio ou não ser JSON). */
export async function errorFrom(response: Response): Promise<ApiError> {
  let payload: any = null;
  try {
    payload = await response.json();
  } catch {
    /* corpo vazio ou HTML do gateway */
  }
  if (!payload?.error && GATEWAY_DOWN.has(response.status)) {
    payload = { error: { code: "unavailable", message: "O servidor está indisponível no momento. Tente novamente em instantes." } };
  }
  return new ApiError(response.status, payload);
}

export async function refreshAccess(): Promise<string | null> {
  if (!refreshing) {
    refreshing = fetchApi(apiUrl("/api/auth/refresh"), { method: "POST", credentials: CREDENTIALS })
      .then(async (r) => (r.ok ? ((await r.json()).access as string) : null))
      .catch(() => null)
      .then((token) => {
        accessToken = token;
        return token;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Options = {
  method?: string;
  body?: unknown;
  form?: FormData;
  params?: Record<string, string | number | undefined | null>;
  raw?: boolean;
  auth?: boolean;
};

export async function api<T = any>(path: string, opts: Options = {}, retried = false): Promise<T> {
  const url = apiUrl(`/api${path}`);
  Object.entries(opts.params ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });

  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (organizationId) headers["X-Organization"] = organizationId;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const response = await fetchApi(url, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, credentials: CREDENTIALS });

  if (response.status === 401 && opts.auth !== false && !retried) {
    const token = await refreshAccess();
    if (token) return api<T>(path, opts, true);
    await connectivity.settle();
    if (!connectivity.unavailable()) onSessionExpired();
  }
  if (!response.ok) throw await errorFrom(response);
  if (opts.raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;
  return response.json();
}

/** Baixa um arquivo autenticado (PDF, XML, ZIP) e abre ou salva. */
export async function download(path: string, open = false) {
  const response = await api<Response>(path, { raw: true });
  const blob = await response.blob();
  const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || "arquivo";
  const href = URL.createObjectURL(blob);
  if (open) {
    window.open(href, "_blank", "noopener");
  } else {
    const a = document.createElement("a");
    a.href = href;
    a.download = name;
    a.click();
  }
  setTimeout(() => URL.revokeObjectURL(href), 30_000);
}

export type Page<T> = { results: T[]; next: string | null; previous: string | null; count?: number };

export function cursorOf(next: string | null): string | undefined {
  if (!next) return undefined;
  return new URL(next).searchParams.get("cursor") ?? undefined;
}
