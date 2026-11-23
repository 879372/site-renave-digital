# REVENDA DIGITAL

Plataforma de consultas veiculares, estoque RENAVE, comunicação de venda e emissão de NF-e, mais o site institucional.

| Pasta | Conteúdo |
|---|---|
| `dist/` | Site institucional estático (Vercel) |
| `backend/` | API Django + DRF ([arquitetura](docs/arquitetura.md), [integrações](docs/integracoes.md)) |
| `frontend/` | Aplicação React + Vite |

Para rodar a plataforma localmente, veja [docs/desenvolvimento.md](docs/desenvolvimento.md).

## Site institucional

Site desenvolvido com HTML, CSS e JavaScript.

## Executar localmente

```sh
python3 -m http.server 4173 --directory dist
```

Abra http://localhost:4173 no navegador.

## Estrutura

- `dist/index.html`: página e conteúdo do site.
- `dist/style.css`: identidade visual e layout responsivo.
- `dist/app.js`: formulário, seleção de estado e interações.
- `dist/simbolo.svg`: símbolo da marca.

O formulário prepara uma mensagem para atendimento pelo WhatsApp. O envio deve ser confirmado pelo visitante no WhatsApp.

## Publicação na Vercel

O arquivo `vercel.json` define `dist` como diretório de publicação. A raiz do projeto deve ser a raiz deste repositório. O site é estático e não precisa de comando de build.
