# site-renave-digital

Site institucional do RENAVE DIGITAL (https://renavedigital.kaibez.com.br), desenvolvido com HTML, CSS e JavaScript.

A plataforma fica em repositórios próprios:

- App (React): https://github.com/879372/app-renave-digital
- API (Django): https://github.com/879372/api-renave-digital

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
- `dist/og-image.jpg`: imagem de compartilhamento (WhatsApp e redes sociais).
- `dist/robots.txt` e `dist/sitemap.xml`: indexação no Google.
- `dist/google215e8a812ba11f3e.html`: verificação do Google Search Console (não remover).

O formulário prepara uma mensagem para atendimento pelo WhatsApp. O envio deve ser confirmado pelo visitante no WhatsApp.

## Publicação na Vercel

O arquivo `vercel.json` define `dist` como diretório de publicação. A raiz do projeto deve ser a raiz deste repositório. O site é estático e não precisa de comando de build.
