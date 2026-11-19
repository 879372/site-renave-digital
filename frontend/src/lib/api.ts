/**
 * Cliente da API.
 * - Access token só em memória (nunca localStorage).
 * - Refresh em cookie httpOnly; renovação automática única (single-flight) ao receber 401.
 * - Cabeçalho X-Organization com a empresa ativa.
 */

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

export async function refreshAccess(): Promise<string | null> {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
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
  const url = new URL(`/api${path}`, window.location.origin);
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

  const response = await fetch(url, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, credentials: "same-origin" });

  if (response.status === 401 && opts.auth !== false && !retried) {
    const token = await refreshAccess();
    if (token) return api<T>(path, opts, true);
    onSessionExpired();
  }
  if (!response.ok) {
    let payload: any = null;
    try {
      payload = await response.json();
    } catch {
      /* corpo vazio */
    }
    throw new ApiError(response.status, payload);
  }
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
