/**
 * Onde fica a API.
 *
 * Em produção, VITE_API_URL=https://api.revendadigital.kaibez.com.br faz o navegador chamar a API
 * direto (com cookies de login entre app. e api., que são o mesmo site: kaibez.com.br).
 * Sem a variável, produção usa o domínio público da API; em desenvolvimento o Vite repassa /api.
 */
const configured = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").trim().replace(/\/+$/, "");

export const API_ORIGIN = configured || (import.meta.env.PROD ? "https://api.revendadigital.kaibez.com.br" : window.location.origin);

/** "include" quando a API está em outro domínio, para o cookie de sessão ir junto. */
export const CREDENTIALS: RequestCredentials = API_ORIGIN !== window.location.origin ? "include" : "same-origin";

export function apiUrl(path: string): URL {
  return new URL(path.startsWith("/") ? path : `/${path}`, API_ORIGIN);
}
