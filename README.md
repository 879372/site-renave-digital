# Revenda Digital

Gestão para lojas de veículos: estoque, avaliações, vendas, financeiro, CRM, RENAVE e NF-e.

- Site institucional: https://revendadigital.kaibez.com.br
- Plataforma: https://app.revendadigital.kaibez.com.br
- API: https://api.revendadigital.kaibez.com.br

| Pasta | Conteúdo |
|---|---|
| `dist/` | Site institucional estático publicado na Vercel |
| `frontend/` | Plataforma React + Vite ([repositório de produção](https://github.com/879372/app-renave-digital)) |
| `backend/` | API Django + DRF ([repositório de produção](https://github.com/879372/api-renave-digital)) |

Desenvolvimento da plataforma: [docs/desenvolvimento.md](docs/desenvolvimento.md).

## Prévia do site

```sh
python3 -m http.server 4173 --directory dist
```

Abra http://localhost:4173. O site não precisa de instalação de pacotes nem de build.

## Arquivos do site

- `dist/index.html`: apresentação, exemplos interativos, recursos, planos e perguntas frequentes.
- `dist/style.css`: identidade grafite e verde e layout responsivo.
- `dist/app.js`: navegação móvel, abas acessíveis e alternância dos preços mensais/anuais.
- `dist/simbolo.svg`: símbolo compartilhado com a plataforma.
- `dist/og-image.svg`: fonte vetorial da imagem de compartilhamento.
- `dist/og-image.jpg`: imagem de compartilhamento de 1200 × 630 pixels.
- `dist/robots.txt` e `dist/sitemap.xml`: indexação no novo domínio.
- `dist/google215e8a812ba11f3e.html`: verificação do Search Console (preservar).
- `dist/404.html`, `dist/offline.html` e `dist/sw.js`: páginas auxiliares e fallback offline.

Os botões de teste levam ao cadastro da plataforma. Os links de atendimento abrem o WhatsApp; nenhuma mensagem é enviada automaticamente.

## Publicação

O projeto Vercel `site-renave-digital` publica `dist/` a partir da branch `main` deste repositório. A configuração está em `vercel.json`; não há comando de build. O app e a API são publicados separadamente pelos respectivos repositórios de produção.
