/** Cliente da API administrativa: sessão separada da do lojista (token e cookie próprios). */
import { ApiError } from "@/lib/api";

let accessToken: string | null = null;
let refreshing: Promise<{ access: string; user: AdminUser } | null> | null = null;
let onExpired: () => void = () => {};

export type AdminUser = { id: string; email: string; full_name: string; is_superuser: boolean };

export const adminSession = {
  set(token: string | null) {
    accessToken = token;
  },
  onExpired(fn: () => void) {
    onExpired = fn;
  },
};

export async function adminRefresh(): Promise<{ access: string; user: AdminUser } | null> {
  if (!refreshing) {
    refreshing = fetch("/api/admin/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(async (r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((data) => {
        accessToken = data?.access ?? null;
        return data;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Options = { method?: string; body?: unknown; params?: Record<string, string | number | undefined | null>; auth?: boolean };

export async function adminApi<T = any>(path: string, opts: Options = {}, retried = false): Promise<T> {
  const url = new URL(`/api/admin${path}`, window.location.origin);
  Object.entries(opts.params ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const response = await fetch(url, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, credentials: "same-origin" });
  if (response.status === 401 && opts.auth !== false && !retried) {
    if (await adminRefresh()) return adminApi<T>(path, opts, true);
    onExpired();
  }
  if (!response.ok) {
    let payload: any = null;
    try {
      payload = await response.json();
    } catch {
      /* vazio */
    }
    throw new ApiError(response.status, payload);
  }
  if (response.status === 204 || response.status === 202) return undefined as T;
  return response.json();
}

export type Paged<T> = { count: number; next: string | null; previous: string | null; results: T[] };
