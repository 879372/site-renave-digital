# app-renave-digital

Aplicação web da plataforma REVENDA DIGITAL (https://app.revendadigital.kaibez.com.br): consultas veiculares, estoque RENAVE, comunicação de venda, NF-e de veículos e painel administrativo (`/admin`).

React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query.

## Rodar localmente

```bash
npm install
npm run dev
```

Abre em http://localhost:5180. As chamadas para `/api` são repassadas para a API Django em `http://localhost:8010` (mude com a variável `API_URL`).

## Scripts

| Comando | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento |
| `npm run typecheck` | Checagem de tipos |
| `npm run build` | Build de produção em `dist/` |

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `src/pages/` | Telas do lojista (painel, consultas, estoque, comunicação, notas, carteira, empresa, perfil, documentos legais) |
| `src/admin/` | Painel administrativo, com login e sessão próprios |
| `src/components/` | Componentes compartilhados |
| `src/lib/` | Cliente da API, sessão, formatação, consultas de CNPJ/CEP e dados legais |

## Deploy

O `vercel.json` publica `dist/` como SPA (todas as rotas, exceto `/api` e `/assets`, caem no `index.html`).

**Variável de ambiente na Vercel:** `VITE_API_URL=https://api.revendadigital.kaibez.com.br` (vale no build; refaça o deploy depois de criar). Com ela, o navegador chama a API direto. O cookie de sessão `SameSite=Strict` continua funcionando porque `app.` e `api.` são o mesmo site (`kaibez.com.br`).

Sem a variável, o app chama `/api` no próprio domínio e o `rewrite` do `vercel.json` repassa para a API (também usado no desenvolvimento, pelo proxy do Vite).

Antes de publicar, preencha os dados do controlador em `src/lib/legal.ts`.
