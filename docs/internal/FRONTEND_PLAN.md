# Plano de Frontend - Banco Ágil

## 1. Objetivo do documento

Este documento define a estratégia de frontend do projeto Banco Ágil antes da implementação.

Ele serve como base para:

* orientar a CLI durante a execução;
* evitar decisões improvisadas de UI, estado e integração;
* garantir alinhamento com a arquitetura já construída no backend;
* validar cada etapa do frontend sem misturar escopo;
* manter o frontend como camada fina, sem regra de negócio crítica.

O backend já possui API funcional, orquestração com LangGraph, sessões conversacionais, providers de LLM e câmbio, testes automatizados e smokes reais controlados. O frontend deve consumir essa API, apresentar uma experiência clara de atendimento e respeitar os limites arquiteturais já definidos.

## 2. Objetivo do frontend

Criar uma interface web simples, profissional e funcional para demonstrar a jornada conversacional do Banco Ágil.

A interface deve permitir que o avaliador:

* iniciar uma sessão;
* conversar com o agente bancário;
* autenticar-se pelo fluxo de CPF e data de nascimento;
* consultar limite;
* solicitar aumento de limite;
* responder entrevista financeira quando aplicável;
* consultar cotação de moeda;
* visualizar estado básico da sessão;
* reiniciar conversa;
* identificar erros controlados sem exposição de detalhes internos.

O frontend não deve tentar reproduzir a lógica do backend. Ele apenas envia mensagens, exibe respostas e organiza a experiência do usuário.

## 3. Princípios de frontend

### 3.1 Frontend como thin client

O frontend deve ser uma camada fina.

Ele pode:

* chamar endpoints da API;
* manter estado visual da conversa;
* armazenar `session_id` localmente;
* exibir mensagens do usuário e do assistente;
* mostrar metadados públicos, como estado e agente atual;
* tratar loading e erro de rede;
* oferecer atalhos visuais para fluxos comuns.

Ele não pode:

* autenticar cliente por conta própria;
* calcular score;
* aprovar ou rejeitar crédito;
* escrever CSV;
* chamar providers externos diretamente;
* chamar Grok, OpenAI, SearchApi ou SerpApi;
* decidir transições críticas;
* expor GraphState interno;
* armazenar chaves de API no browser.

### 3.2 API como fonte da verdade

Toda decisão relevante vem do backend.

O frontend deve tratar a API como fonte da verdade para:

* estado público da conversa;
* agente atual;
* resposta do assistente;
* fim ou continuidade da sessão;
* erros recuperáveis;
* ações sugeridas.

### 3.3 Experiência acima de complexidade

O objetivo não é criar um internet banking completo. O objetivo é demonstrar com clareza o funcionamento do agente.

A interface deve ser:

* limpa;
* responsiva;
* fácil de entender;
* rápida para demonstrar;
* sem excesso de telas;
* sem dependências visuais desnecessárias.

## 4. Stack proposta

### 4.1 Framework

Recomendação principal:

```txt
React + Vite + TypeScript
```

Motivo:

* simples para SPA;
* rápido de configurar;
* bom para desafio técnico;
* evita complexidade de SSR desnecessária;
* integra bem com Tailwind;
* facilita deploy futuro em Vercel ou similar.

Alternativa aceitável:

```txt
Next.js + TypeScript
```

Mas, para este projeto, Next.js pode ser mais pesado do que o necessário, porque o frontend será uma aplicação client-side consumindo uma API FastAPI.

Decisão recomendada:

```txt
Usar Vite + React + TypeScript.
```

### 4.2 Estilização

Recomendação:

```txt
Tailwind CSS
```

Motivo:

* produtividade alta;
* visual consistente;
* fácil criar layout responsivo;
* reduz necessidade de CSS manual extenso;
* já estava previsto na visão inicial do projeto.

### 4.3 Estado local

Recomendação:

```txt
Zustand
```

Uso:

* armazenar `session_id`;
* armazenar lista de mensagens;
* armazenar estado público atual;
* armazenar loading/error;
* persistir sessão no `localStorage`, se fizer sentido.

Alternativa:

* `useState` e `useReducer` seriam suficientes para uma versão mínima.

Decisão recomendada:

```txt
Usar Zustand apenas se o estado começar a passar de 2 ou 3 componentes.
Para MVP, pode começar com React state e migrar para store se necessário.
```

### 4.4 Cliente HTTP

Recomendação:

```txt
fetch nativo
```

Motivo:

* suficiente para poucos endpoints;
* evita dependência desnecessária;
* mantém frontend simples;
* fácil criar wrapper próprio.

Não há necessidade inicial de Axios.

### 4.5 Formulários

Para o MVP, usar input controlado simples com React.

Não usar React Hook Form nesta fase, salvo se o frontend evoluir para múltiplos formulários estruturados.

### 4.6 Testes de frontend

Recomendação inicial:

```txt
Vitest + React Testing Library
```

Escopo inicial de testes:

* renderização do chat;
* envio de mensagem;
* tratamento de loading;
* tratamento de erro;
* persistência de session_id;
* reset de sessão;
* chamada correta dos endpoints.

Não criar E2E com Playwright na primeira fase, salvo se sobrar tempo.

## 5. Variáveis de ambiente do frontend

O frontend deve conhecer apenas a URL pública da API.

Exemplo:

```txt
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

O frontend não deve receber:

```txt
XAI_API_KEY
OPENAI_API_KEY
EXCHANGE_API_KEY
SEARCHAPI_API_KEY
SERPAPI_API_KEY
```

Essas chaves pertencem exclusivamente ao backend.

## 6. Contratos da API consumidos pelo frontend

### 6.1 Health

```txt
GET /api/v1/health
```

Uso no frontend:

* verificar se backend está online;
* exibir status discreto na tela;
* não bloquear a aplicação se falhar, mas informar indisponibilidade.

### 6.2 Chat

```txt
POST /api/v1/chat
```

Request:

```json
{
  "session_id": "string ou null",
  "message": "texto do usuário"
}
```

Response:

```json
{
  "session_id": "uuid",
  "reply": "resposta pública do agente",
  "agent": "triage | credit | credit_interview | exchange | system",
  "state": "estado público",
  "ended": false,
  "trace_id": "uuid",
  "metadata": {
    "recoverable": false,
    "retry_available": false,
    "suggested_action": "none | retry | reset | reauthenticate | continue"
  }
}
```

Uso no frontend:

* enviar mensagem do usuário;
* exibir resposta do agente;
* atualizar `session_id`;
* atualizar estado público;
* exibir erro recuperável quando necessário;
* exibir botão de tentar novamente ou resetar quando sugerido pela API.

### 6.3 Reset de sessão

```txt
POST /api/v1/sessions/reset
```

Uso no frontend:

* iniciar nova conversa;
* limpar mensagens locais;
* substituir `session_id`.

### 6.4 Resume de sessão

```txt
GET /api/v1/sessions/{session_id}
```

Uso no frontend:

* validar sessão persistida no localStorage;
* recuperar estado público básico;
* recuperar mensagens recentes se disponíveis.

## 7. Estrutura de pastas sugerida

```txt
frontend/
  package.json
  index.html
  vite.config.ts
  tsconfig.json
  .env.example

  src/
    main.tsx
    App.tsx

    api/
      client.ts
      chatApi.ts
      sessionApi.ts
      healthApi.ts
      types.ts

    components/
      layout/
        AppShell.tsx
        Header.tsx
        StatusBadge.tsx

      chat/
        ChatWindow.tsx
        MessageList.tsx
        MessageBubble.tsx
        ChatInput.tsx
        AgentBadge.tsx
        TypingIndicator.tsx
        EmptyState.tsx

      session/
        SessionPanel.tsx
        ResetSessionButton.tsx

      feedback/
        ErrorBanner.tsx
        LoadingOverlay.tsx

    hooks/
      useChat.ts
      useSession.ts
      useHealth.ts

    store/
      chatStore.ts

    lib/
      formatters.ts
      constants.ts

    styles/
      index.css

    tests/
      chat.test.tsx
      api.test.ts
```

Para MVP, essa estrutura pode ser reduzida. O importante é separar:

* API client;
* componentes visuais;
* estado de chat;
* tipos públicos;
* hooks de integração.

## 8. Modelo de dados no frontend

### 8.1 Mensagem local

```ts
type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  agent?: "triage" | "credit" | "credit_interview" | "exchange" | "system";
  state?: string;
};
```

### 8.2 Estado local do chat

```ts
type ChatViewState = {
  sessionId: string | null;
  messages: ChatMessage[];
  currentAgent: string | null;
  currentState: string | null;
  ended: boolean;
  loading: boolean;
  error: string | null;
  traceId: string | null;
};
```

### 8.3 Regras do estado local

* A mensagem do usuário entra imediatamente na lista.
* A resposta do backend entra como mensagem do assistente.
* Se a API retornar erro controlado, exibir `ErrorBanner`.
* Se o erro for recuperável, oferecer botão de retry.
* Se a API sugerir reset, oferecer botão de nova sessão.
* Nunca armazenar GraphState completo.
* Nunca armazenar dados sensíveis além do necessário para UI.

## 9. UI/UX proposta

### 9.1 Tela principal

Layout recomendado:

```txt
Header
  Nome do produto
  Status da API
  Botão resetar sessão

Main
  Painel do chat
  Painel lateral de sessão

Footer discreto
  trace_id atual ou ambiente local
```

### 9.2 Chat

A área principal deve parecer um atendimento bancário conversacional.

Elementos:

* bolha do usuário alinhada à direita;
* bolha do assistente alinhada à esquerda;
* badge do agente atual;
* loading enquanto aguarda resposta;
* estado público atual em área discreta;
* mensagem inicial explicando o que o usuário pode fazer.

### 9.3 Painel lateral

O painel lateral pode exibir:

* `session_id` abreviado;
* agente atual;
* estado atual;
* se a sessão terminou;
* último `trace_id`;
* botão para resetar sessão;
* exemplos de mensagens.

### 9.4 Sugestões rápidas

Adicionar botões de exemplo pode acelerar a demonstração:

* Consultar limite
* Aumentar limite
* Cotação do dólar
* Encerrar conversa

Esses botões apenas preenchem ou enviam mensagens. Eles não executam regra local.

### 9.5 Estados visuais

A UI deve tratar:

* backend online;
* backend offline;
* carregando resposta;
* erro de validação;
* erro recuperável;
* serviço indisponível;
* sessão encerrada;
* sessão resetada.

## 10. Ordem de implementação sugerida

### Fase F1: Setup do frontend

Objetivo:

* criar projeto Vite React TypeScript;
* configurar Tailwind;
* criar `.env.example` com `VITE_API_BASE_URL`;
* criar layout inicial;
* garantir build e lint básicos.

Entregáveis:

* estrutura `frontend/`;
* `AppShell` simples;
* tela inicial estática.

Validação:

* `npm install`;
* `npm run dev`;
* `npm run build`.

### Fase F2: API client e tipos

Objetivo:

* criar tipos TypeScript para contratos públicos;
* criar `client.ts` com fetch wrapper;
* criar `chatApi.ts`, `sessionApi.ts`, `healthApi.ts`.

Entregáveis:

* chamadas isoladas;
* tratamento de erro padrão;
* base URL via env.

Validação:

* testes unitários do client com fetch mockado;
* nenhum acoplamento com GraphState interno.

### Fase F3: Chat MVP

Objetivo:

* criar tela de chat funcional;
* enviar mensagem para `/chat`;
* exibir resposta;
* guardar `session_id`.

Entregáveis:

* `ChatWindow`;
* `MessageList`;
* `MessageBubble`;
* `ChatInput`;
* estado local mínimo.

Validação:

* enviar mensagem e receber resposta do backend local;
* loading funciona;
* erro básico funciona.

### Fase F4: Sessão e reset

Objetivo:

* persistir `session_id` em localStorage;
* retomar sessão com endpoint de resume;
* resetar sessão.

Entregáveis:

* `useSession`;
* `SessionPanel`;
* `ResetSessionButton`.

Validação:

* recarregar página mantém sessão se válida;
* reset limpa mensagens locais e cria nova sessão.

### Fase F5: UX de demonstração

Objetivo:

* melhorar experiência visual;
* adicionar badges de agente e estado;
* adicionar sugestões rápidas;
* exibir trace_id de forma discreta.

Entregáveis:

* layout polido;
* estados de loading e erro;
* empty state com instruções.

Validação:

* fluxo demo roda sem instrução externa complexa;
* avaliador entende o sistema em poucos minutos.

### Fase F6: Testes e hardening

Objetivo:

* cobrir componentes críticos;
* garantir que frontend não expõe dados internos;
* validar erro de API.

Entregáveis:

* testes com Vitest e React Testing Library;
* testes do API client;
* testes básicos de ChatWindow.

Validação:

* `npm test`, se configurado;
* `npm run build`;
* fluxo manual com backend local.

## 11. Critérios de aceite do frontend

O frontend só deve ser considerado pronto quando:

* iniciar localmente sem erro;
* conectar no backend via `VITE_API_BASE_URL`;
* criar sessão;
* enviar mensagens;
* exibir respostas do agente;
* reaproveitar `session_id`;
* resetar sessão;
* mostrar loading;
* mostrar erros controlados;
* não expor GraphState completo;
* não possuir chaves de API no bundle;
* não chamar LLM ou provider externo diretamente;
* build de produção funcionar.

## 12. Fora de escopo da primeira versão

Não implementar agora:

* login de usuário real;
* área administrativa;
* dashboard financeiro;
* gráficos complexos;
* autenticação JWT;
* upload de CSV;
* edição de dados de clientes;
* deploy frontend;
* WebSocket;
* streaming de resposta;
* tema escuro complexo;
* múltiplas conversas salvas em banco.

## 13. Riscos e cuidados

### 13.1 Risco de duplicar regra de negócio

O frontend pode cair na tentação de interpretar fluxo por conta própria. Isso deve ser evitado.

Regra:

```txt
Se é decisão de negócio, fica no backend.
```

### 13.2 Risco de expor internals

O frontend deve confiar nos contratos públicos.

Não criar campos, logs ou painéis que mostrem:

* `GraphState` completo;
* `current_customer`;
* `authenticated_cpf`;
* prompts;
* payloads completos de provider;
* chaves ou headers.

### 13.3 Risco de UX confusa

Como o backend é conversacional, a UI precisa deixar claro o próximo passo.

A resposta do agente deve ser o elemento principal. Badges e estados ajudam, mas não devem competir com a conversa.

### 13.4 Risco de acoplar ao ambiente local

A URL da API deve vir de env:

```txt
VITE_API_BASE_URL
```

Não hardcodar `localhost:8000` dentro dos componentes.

## 14. Estratégia de validação manual

Antes de considerar o frontend pronto, executar:

1. Backend rodando com `uvicorn app.main:app --reload`.
2. Frontend rodando com `npm run dev`.
3. Abrir tela inicial.
4. Confirmar status da API.
5. Criar sessão.
6. Enviar CPF válido.
7. Enviar data válida.
8. Consultar limite.
9. Solicitar aumento.
10. Testar resposta de erro com mensagem vazia.
11. Resetar sessão.
12. Recarregar página e validar comportamento de sessão.

## 15. Resultado esperado da primeira entrega frontend

A primeira entrega de frontend deve ser uma SPA simples e bem acabada, não um produto bancário completo.

Ela deve demonstrar:

* capacidade de integrar com API real;
* entendimento de contratos públicos;
* experiência conversacional limpa;
* separação correta entre UI e backend;
* cuidado com segurança e exposição de dados;
* maturidade na organização do código.

O objetivo é facilitar a avaliação do backend e tornar o sistema demonstrável por uma interface amigável.

Perfeito. Sua observação faz sentido.

O documento ficou bom na parte técnica, mas a camada de **produto visual** ainda estava genérica demais. E isso importa, porque o frontend não será só um consumidor de API. Ele também será a vitrine do projeto.

Minha posição é a seguinte:

```txt id="1kxkm9"
- Na V1, o frontend não deve ter múltiplas telas de negócio.
- Ele deve ter um dashboard principal único, muito bem resolvido.
- Não deve existir navegação manual entre agentes.
- Os agentes são uma responsabilidade do backend e aparecem no frontend apenas como contexto visual.
- A UI deve parecer um produto real, não um protótipo acadêmico.
```

Abaixo está o complemento que eu adicionaria ao documento, já em formato pronto para virar seção oficial.

## 16. Direção visual do frontend

### 16.1 Visão geral da interface

A interface do Banco Ágil deve transmitir três ideias ao mesmo tempo:

* clareza de uso;
* credibilidade de produto financeiro;
* sensação de sistema moderno orientado por IA.

A proposta visual não deve seguir a estética de banco tradicional pesado, nem a estética exageradamente futurista. O ideal é um meio-termo entre:

* dashboard SaaS moderno;
* console de operação elegante;
* chat profissional com identidade fintech.

A experiência deve passar a impressão de um produto real, organizado e confiável.

## 17. Estrutura de navegação

### 17.1 Quantas páginas existirão

Decisão recomendada para a V1:

```txt id="fo8rnb"
Ter apenas 1 página principal de produto:
- Atendimento
```

Opcionalmente, no futuro, podem existir páginas auxiliares, mas não agora.

Páginas previstas para a primeira versão:

### Página 1: Atendimento

Será a página principal e suficiente para a primeira entrega.

Ela concentrará:

* chat com o agente;
* informações da sessão;
* status da API;
* estado atual da conversa;
* atalhos de demonstração;
* reset de sessão.

### Páginas que NÃO devem existir na V1

Não criar agora:

* uma página por agente;
* uma área administrativa;
* uma tela separada de autenticação;
* uma tela de configurações;
* uma tela de histórico completo;
* uma tela de documentação dentro do app.

Motivo: isso aumentaria complexidade sem melhorar a demonstração do backend.

## 18. Menu lateral e navegação entre agentes

### 18.1 Haverá menu lateral?

Sim.

### 18.2 Haverá navegação manual entre agentes?

Não.

Essa decisão é importante e deve ficar explícita.

Os agentes:

* triage
* credit
* credit_interview
* exchange

não devem aparecer como se fossem módulos navegáveis manualmente pelo usuário.

O usuário não “entra” no agente de crédito clicando num menu. Quem controla isso é o backend.

No frontend, o menu lateral terá papel de:

* identidade visual;
* contexto da sessão;
* atalhos úteis;
* status do sistema;
* orientação da demo.

### 18.3 Estrutura do menu lateral

O menu lateral deve conter blocos fixos, não rotas complexas.

#### Bloco 1: Branding

* Nome do projeto: Banco Ágil
* Subtítulo curto: Intelligent Banking Agent
* Pequeno texto de apoio: atendimento bancário conversacional

#### Bloco 2: Status do sistema

* API online/offline
* provider de câmbio configurado
* sessão ativa/inativa

#### Bloco 3: Sessão

* `session_id` abreviado
* agente atual
* estado atual
* indicador de sessão encerrada ou ativa

#### Bloco 4: Ações rápidas

Botões para preencher ou enviar mensagens de demonstração:

* Consultar limite
* Aumentar limite
* Fazer entrevista
* Cotação do dólar
* Encerrar conversa

Esses botões apenas disparam mensagens para o chat. Eles não navegam entre agentes.

#### Bloco 5: Controle

* botão “Nova sessão”
* botão “Resetar sessão”

## 19. Layout principal

### 19.1 Estrutura geral

A estrutura recomendada da tela é:

```txt id="4wghjw"
Sidebar fixa à esquerda
Header superior discreto
Área principal de chat no centro
Painel contextual compacto dentro da própria página
```

### 19.2 Composição da tela

#### Sidebar à esquerda

Largura sugerida:

```txt id="v7cypf"
260px a 300px
```

Função:

* branding;
* status;
* sessão;
* ações rápidas.

#### Header superior

Função:

* título da sessão atual;
* badge do agente atual;
* badge do estado atual;
* status da API;
* botão de reset.

#### Área principal

É o foco da aplicação.

Deve conter:

* lista de mensagens;
* bolhas do usuário e do agente;
* empty state inicial;
* indicador de carregamento;
* input de envio;
* mensagens de erro controlado.

#### Painel contextual

Não precisa ser uma coluna separada obrigatória.

Pode ser uma área compacta, no topo ou lateral do chat, exibindo:

* agente atual;
* estado atual;
* último trace_id;
* ação sugerida pela API.

## 20. Estilo visual desejado

### 20.1 Referência estética

A interface deve se inspirar em produtos modernos e sóbrios, como:

* Linear
* Vercel Dashboard
* Stripe Dashboard
* interfaces de chat modernas com visual limpo

Não copiar nenhuma interface literalmente.

A referência é de linguagem visual:

* minimalismo;
* contraste elegante;
* tipografia limpa;
* cartões bem espaçados;
* hierarquia clara.

### 20.2 Linguagem visual

A interface deve parecer:

```txt id="4znl27"
moderna
sofisticada
escura
profissional
limpa
```

Evitar:

```txt id="0v8atw"
visual infantil
cores gritantes
efeitos excessivos
cara de template genérico
cara de internet banking antigo
```

## 21. Paleta de cores definida

### 21.1 Tema padrão

Recomendação: tema escuro como padrão.

Motivo:

* valoriza a estética de console moderno;
* destaca melhor o chat;
* combina com a proposta tech/fintech;
* facilita o uso de acentos luminosos discretos.

### 21.2 Paleta principal

#### Background

* `#0B1020`  background principal
* `#12182B`  superfícies e painéis
* `#18213A`  cards em destaque

#### Bordas e divisões

* `#26314D`

#### Texto

* `#E8EEF9`  texto principal
* `#A8B3C7`  texto secundário
* `#7B879C`  texto discreto

#### Cor primária

* `#4F7CFF`

Uso:

* botões principais;
* foco;
* links;
* elementos ativos.

#### Cor secundária de destaque

* `#22C7F2`

Uso:

* detalhes de IA;
* glow sutil;
* badges informativos.

#### Cores semânticas

* sucesso: `#22C55E`
* aviso: `#F59E0B`
* erro: `#EF4444`

### 21.3 Gradientes

Usar gradientes leves, não exagerados.

Exemplo de linguagem:

```txt id="se3bwo"
azul profundo para ciano suave
```

Uso permitido:

* header do app;
* botão principal;
* glow de foco;
* destaque de status online.

## 22. Tipografia

### 22.1 Fonte principal

Recomendação:

```txt id="ewn7as"
Inter
```

Alternativa aceitável:

```txt id="wjeqyl"
Manrope
```

Decisão recomendada:

```txt id="gng3sq"
Inter
```

Motivo:

* excelente legibilidade;
* aspecto moderno;
* boa para dashboards;
* boa para textos e labels.

### 22.2 Peso tipográfico

Usar hierarquia simples:

* 600 ou 700 para títulos
* 500 para subtítulos
* 400 para corpo de texto
* 500 para badges e rótulos curtos

## 23. Ícones

### 23.1 Usaremos ícones?

Sim.

### 23.2 Biblioteca recomendada

Decisão recomendada:

```txt id="5kr53n"
react-icons
```

### 23.3 Família visual recomendada

Usar preferencialmente um único conjunto para manter consistência.

Sugestão:

```txt id="whdmc5"
react-icons/fi
```

ou

```txt id="y1v8rb"
react-icons/hi2
```

Decisão mais sóbria:

```txt id="kj217g"
react-icons/fi
```

### 23.4 Regras para ícones

Usar ícones para:

* sessão;
* status;
* reset;
* enviar mensagem;
* online/offline;
* crédito;
* câmbio;
* entrevista;
* erro/alerta.

Não usar emoji em nenhuma parte da interface.

## 24. Animações e efeitos

### 24.1 Haverá animações?

Sim, mas de forma sutil.

### 24.2 Biblioteca de animação

Na V1, **não usar Framer Motion**.

Usar apenas:

* transições CSS via Tailwind;
* hover suave;
* fade simples;
* pulse muito leve para status online/loading.

Motivo:

* reduz complexidade;
* mantém build enxuto;
* evita excesso visual.

### 24.3 Jogo de luzes

Sim, mas com moderação.

A proposta é usar:

* glow leve azul/ciano em botões ativos;
* sombra suave em cards;
* borda levemente iluminada em elementos focados;
* status online com ponto pulsante discreto.

Não usar:

* neon exagerado;
* blur excessivo;
* partículas;
* efeitos chamativos demais.

A sensação visual deve ser “premium e controlada”, não “cyberpunk”.

## 25. Componentes visuais essenciais

### 25.1 Header

Deve conter:

* nome da tela;
* estado atual;
* agente atual;
* status da API;
* botão de reset.

### 25.2 Sidebar

Deve conter:

* branding;
* status geral;
* sessão;
* ações rápidas.

### 25.3 MessageBubble

Duas variações:

* usuário: alinhado à direita, fundo primário discreto;
* agente: alinhado à esquerda, fundo de card escuro.

Cada bolha pode mostrar:

* conteúdo;
* hora simplificada;
* badge do agente, quando fizer sentido.

### 25.4 ChatInput

Deve ficar fixo ou pseudo-fixo no rodapé da área de chat.

Precisa ter:

* input de texto;
* botão enviar;
* estado disabled enquanto loading.

### 25.5 StatusBadge

Usado para:

* online/offline;
* agente atual;
* estado público;
* sessão ativa/encerrada.

### 25.6 ErrorBanner

Exibir erro controlado de forma elegante:

* sem stack trace;
* sem ruído técnico;
* com ação sugerida, quando houver.

## 26. Jornada visual do usuário

### Estado 1: Tela inicial

Usuário entra e vê:

* branding;
* status da API;
* chat vazio;
* instrução inicial;
* sugestões rápidas.

### Estado 2: Conversa em andamento

Usuário envia mensagens e vê:

* histórico no centro;
* contexto da sessão na lateral;
* loading entre turno do usuário e resposta da API.

### Estado 3: Erro controlado

Usuário vê:

* banner discreto;
* texto simples;
* opção de retry ou reset.

### Estado 4: Sessão encerrada

Usuário vê:

* estado “encerrada”;
* input desabilitado ou com aviso;
* botão claro de iniciar nova sessão.

## 27. Critérios de qualidade visual

O frontend só será considerado visualmente aprovado se:

* parecer produto real, não protótipo cru;
* tiver hierarquia clara;
* não usar emoji;
* não exagerar em efeito;
* tiver consistência de spacing;
* tiver consistência de ícones;
* tiver boa leitura em desktop;
* funcionar em mobile de forma aceitável;
* destacar o chat como elemento central;
* deixar a navegação intuitiva sem criar múltiplas telas desnecessárias.

## 28. Decisões fechadas de UI/UX

Para eliminar ambiguidade, eu fecharia assim:

```txt id="fx0jfx"
- A V1 terá uma única página principal chamada Atendimento.
- Haverá sidebar à esquerda.
- Não haverá navegação manual entre agentes.
- A estética será dark, moderna, profissional e minimalista.
- A stack visual será Tailwind.
- Os ícones virão de react-icons, preferencialmente Fi.
- Não usaremos emoji.
- Haverá animações leves via CSS/Tailwind.
- Haverá glow sutil azul/ciano, sem exagero.
- A paleta principal será escura com azul e ciano como destaque.
- O foco visual será a conversa, não a navegação.
```

## 29. Minha recomendação final

Eu incorporaria esse complemento ao documento e trataria isso como **decisão fechada**, não apenas inspiração.

A direção que eu recomendo é:

```txt id="pl0gpm"
Banco Ágil Frontend = dashboard único + sidebar contextual + chat central + visual fintech moderno + dark theme + glow sutil + zero navegação artificial entre agentes
```

Esse é o melhor equilíbrio entre:

* boa apresentação;
* fidelidade arquitetural;
* baixo risco de overengineering;
* velocidade de execução.
