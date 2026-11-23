/** Detecta se a página é o site público de uma loja (sem carregar o código do site no app). */
const ROOT_DOMAIN = "revendadigital.kaibez.com.br";

export function storefrontSlug(): string | null {
  const host = window.location.hostname;
  if (host.endsWith(`.${ROOT_DOMAIN}`)) {
    const sub = host.slice(0, -ROOT_DOMAIN.length - 1);
    if (sub && !["app", "www", "api"].includes(sub)) return sub;
  }
  const m = window.location.pathname.match(/^\/loja\/([a-z0-9-]+)/);
  return m ? m[1] : null;
}
