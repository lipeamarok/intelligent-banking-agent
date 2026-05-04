# Frontend Banco Agil

Frontend em Vite + React + TypeScript com Tailwind CSS para consumir a API do backend Banco Agil como thin client.

## Scripts

- npm run dev
- npm run build
- npm run preview

## Ambiente

Crie .env local a partir de .env.example e configure apenas:

- VITE_API_BASE_URL

Nenhuma chave de API deve existir no frontend.

## Escopo

- cliente fino: sem regra de negocio critica no frontend
- integracao com backend via /api/v1 (chat, sessao e health)
- estado visual da conversa e metadados publicos de sessao
- tratamento de erros com envelope padronizado da API
- painel de apoio para endpoints admin em ambiente local
