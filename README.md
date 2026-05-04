# Banco Ágil - Intelligent Banking Agent

Sistema de atendimento bancário fictício com agentes especializados para triagem, crédito, entrevista financeira e câmbio.

O projeto foi desenvolvido como desafio técnico para demonstrar arquitetura backend, orquestração de agentes, uso controlado de LLMs, integração com APIs externas, persistência em CSV e exposição de uma API HTTP segura com FastAPI.

A proposta central é simples: usar IA onde ela agrega valor, mas manter regras críticas sob controle determinístico.

---

## Visão geral

O Banco Ágil simula uma jornada de atendimento bancário conversacional.

O usuário pode:

- autenticar-se com CPF e data de nascimento;
- cadastrar-se como novo cliente;
- consultar seu limite de crédito;
- solicitar aumento de limite;
- passar por uma entrevista financeira para recalcular score;
- consultar cotação de moedas;
- manter uma sessão conversacional por meio da API.

A aplicação usa LangGraph para orquestrar o fluxo entre agentes, FastAPI para expor a API, Pydantic para contratos e validações, repositories CSV para persistência local e providers externos para LLM e câmbio.

---

## Ideia principal

O projeto foi desenhado com uma separação clara entre:

- orquestração conversacional;
- regras de negócio;
- persistência;
- integrações externas;
- contratos públicos da API.

A LLM não é tratada como fonte de verdade. Ela é usada apenas para tarefas controladas, como classificação de intenção. As decisões críticas continuam em código determinístico.

Exemplos:

- autenticação é feita por `AuthService`;
- aprovação de crédito é feita por `CreditService`;
- cálculo de score é feito por `ScoreService`;
- escrita em CSV é feita apenas por repositories;
- roteamento sensível passa por `StateGuard`;
- output de LLM é validado antes de ser aceito.

---

## Funcionalidades implementadas

- Autenticação por CPF e data de nascimento.
- Cadastro de novos clientes com validação de nome e data.
- Consulta de limite de crédito.
- Solicitação de aumento de limite.
- Avaliação determinística de aprovação ou rejeição.
- Entrevista financeira para recálculo de score.
- Atualização de score em CSV.
- Cotação de moeda via provider externo.
- Classificação de intenção com LLM controlada.
- Fallback entre Grok e OpenAI.
- Orquestração com LangGraph.
- API HTTP com FastAPI.
- Endpoints de inspeção de CSV para ambiente local.
- Sessões conversacionais em memória.
- Testes automatizados sem dependência de rede real.
- Proteção contra exposição de estado interno na API.

---

## Arquitetura

Fluxo de alto nível:

```txt
FastAPI
  -> SessionService
  -> LangGraph
  -> Nodes
  -> Services
  -> Repositories / Providers
  -> CSV / APIs externas
```

Responsabilidades principais:

```txt
API
  Recebe requests, valida contratos públicos e devolve respostas seguras.

SessionService
  Mantém o estado conversacional em memória durante a execução da aplicação.

LangGraph
  Orquestra o fluxo entre os nós de atendimento.

Nodes
  Coordenam o fluxo, mas não implementam regra de negócio crítica.

Services
  Contêm regras determinísticas de autenticação, crédito, score e normalização.

Repositories
  Leem e escrevem arquivos CSV de forma controlada.

Providers
  Encapsulam chamadas externas, como LLMs e API de cotação.

Schemas
  Definem os contratos internos e públicos usando Pydantic.
```

---

## Agentes do sistema

O fluxo foi organizado em agentes especializados.

### Agente de Triagem

Responsável por conduzir a autenticação inicial do cliente.

Ele coleta:

- CPF;
- data de nascimento.

A autenticação não é feita por LLM. Ela é validada de forma determinística contra os dados disponíveis no CSV de clientes.

### Agente de Crédito

Responsável por:

- consultar limite atual;
- receber solicitação de aumento de limite;
- chamar o serviço de crédito;
- apresentar aprovação ou rejeição.

A aprovação não é decidida pelo agente. A decisão vem do `CreditService`.

### Agente de Entrevista de Crédito

Responsável por coletar dados financeiros quando uma solicitação de aumento é rejeitada.

A entrevista coleta:

- renda mensal;
- tipo de emprego;
- despesas fixas mensais;
- número de dependentes;
- existência de dívidas ativas.

Depois disso, o score é recalculado por `ScoreService` e persistido por repository.

### Agente de Câmbio

Responsável por consultar cotação de moedas usando um provider externo injetado.

A implementação atual suporta SearchApi como provider inicial e mantém SerpApi como alternativa.

---

## Uso controlado de LLM

A LLM é usada apenas para classificação de intenção.

Exemplo de intenções aceitas:

- `credit_limit`
- `credit_increase`
- `credit_interview`
- `exchange_quote`
- `end_conversation`
- `unknown`

Mesmo nesse caso, a saída da LLM passa por validação rígida contra o enum `Intent`.

Outputs como `credit_node`, frases explicativas, respostas longas ou valores desconhecidos são rejeitados e tratados como `unknown`.

A LLM não pode:

- autenticar cliente;
- aprovar crédito;
- calcular score;
- escrever CSV;
- decidir transição crítica sem validação;
- fabricar resposta de API externa;
- expor detalhes internos do sistema.

---

## Persistência

A V1 usa arquivos CSV como fonte de dados.

Arquivos esperados:

```txt
backend/app/data/clientes.csv
backend/app/data/score_limite.csv
backend/app/data/solicitacoes_aumento_limite.csv
```

Contrato canônico de `score_limite.csv`:

```txt
score_minimo,score_maximo,limite_maximo_permitido
```

Para criar ou restaurar os CSVs locais determinísticos:

```bash
cd backend
python scripts/seed_data.py
python scripts/seed_data.py --reset
```

Os dados do seed são fictícios e apenas para ambiente local controlado.

O acesso a CSV é isolado nos repositories.

A escrita usa estratégia segura com arquivo temporário e substituição atômica, evitando que services ou nodes escrevam diretamente em disco.

---

## API

A API é exposta com FastAPI.

Endpoints principais:

```txt
GET  /api/v1/health
POST /api/v1/chat
POST /api/v1/sessions/reset
GET  /api/v1/sessions/{session_id}

# Admin — apenas APP_ENV=local
GET  /api/v1/admin/csv/{table}
POST /api/v1/admin/csv/{table}/reset
```

Os endpoints `/api/v1/admin/csv` permitem inspecionar e resetar os CSVs em ambiente local. São bloqueados com HTTP 403 em qualquer ambiente não-local.

### Health

```http
GET /api/v1/health
```

Retorna o status básico da API sem chamar providers externos.

---

## Documentacao para avaliacao tecnica

Leitura recomendada para avaliacao do projeto:

- `docs/ARCHITECTURE.md`
- `docs/STATE_MACHINE.md`
- `docs/DECISIONS.md`
- `docs/API_CONTRACT.md`
- `docs/SECURITY.md`

Documentos complementares (apoio interno e plano de execucao):

- `docs/internal/TEST_PLAN.md`
- `docs/internal/FRONTEND_PLAN.md`
- `docs/internal/DEMO_FLOW.md`
- `docs/AI_RUNTIME_GRAPH.md`

### Chat

```http
POST /api/v1/chat
```

Exemplo de request:

```json
{
  "session_id": null,
  "message": "quero consultar meu limite"
}
```

Exemplo de response:

```json
{
  "session_id": "uuid-da-sessao",
  "reply": "Mensagem pública do agente",
  "agent": "triage",
  "state": "ASKING_CPF",
  "ended": false,
  "trace_id": "uuid-do-trace",
  "metadata": {
    "recoverable": false,
    "retry_available": false,
    "suggested_action": "none",
    "last_action_summary": "ASKED_FOR_CPF",
    "adherence_flag": false
  }
}
```

A resposta pública não expõe:

- `GraphState` completo;
- `current_customer`;
- `authenticated_cpf`;
- prompts;
- raw output de LLM;
- dados internos de provider;
- stack trace.

### Reset de sessão

```http
POST /api/v1/sessions/reset
```

Cria uma nova sessão ou reseta uma sessão existente.

### Resume de sessão

```http
GET /api/v1/sessions/{session_id}
```

Retorna um resumo público da sessão, incluindo no máximo as últimas três mensagens recentes.

---

## Tutorial de execução e testes

### 1. Entrar na pasta do backend

```bash
cd backend
```

### 2. Criar ambiente virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependências

```bash
python -m pip install -e .[dev]
```

### 4. Configurar variáveis de ambiente

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

No Windows PowerShell, se preferir:

```powershell
Copy-Item .env.example .env
```

Configure as chaves necessárias no `.env` local.

Ao iniciar a API com `uvicorn app.main:app --reload`, o backend carrega
automaticamente o arquivo `backend/.env` em runtime local.
Variáveis não vazias já exportadas no shell prevalecem sobre as do arquivo.
Se uma variável estiver vazia no shell, o valor do `.env` é usado como fallback.

Variáveis principais:

```txt
APP_ENV=local
DATA_DIR=app/data

XAI_API_KEY=
OPENAI_API_KEY=
EXCHANGE_API_KEY=

XAI_URL=https://api.x.ai/v1/chat/completions
OPENAI_URL=https://api.openai.com/v1/chat/completions
PRIMARY_MODEL=grok-4-1-fast
FALLBACK_MODEL=gpt-5.1

EXCHANGE_PROVIDER=searchapi
EXCHANGE_BASE_URL=https://www.searchapi.io/api/v1/search
```

Observação: `XAI_API_KEY` é a variável canônica para xAI/Grok. O projeto não usa `GROK_API_KEY` como variável principal.

### 5. Rodar testes

```bash
python -m pytest
```

A suíte automatizada não faz chamadas reais para LLMs ou APIs externas.

### 5.1 Preparar dados locais (obrigatório para fluxo real)

```bash
python scripts/seed_data.py
```

Para reset completo dos CSVs:

```bash
python scripts/seed_data.py --reset
```

### 6. Subir a API

```bash
uvicorn app.main:app --reload
```

Opção recomendada (detecta processo na porta 8000 e usa a venv correta):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1
```

Para encerrar listener existente da porta 8000 antes de iniciar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1 -KillExisting
```

A API ficará disponível em:

```txt
http://localhost:8000
```

A documentação interativa do FastAPI estará em:

```txt
http://localhost:8000/docs
```

---

## Exemplo rápido com curl

### Health

```bash
curl http://localhost:8000/api/v1/health
```

### Criar sessão

```bash
curl -X POST http://localhost:8000/api/v1/sessions/reset
```

### Enviar mensagem

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"quero consultar meu limite\"}"
```

### Continuar sessão

Use o `session_id` retornado na primeira resposta:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"SEU_SESSION_ID\",\"message\":\"12345678901\"}"
```

---

## Fluxo de demonstração sugerido

Um fluxo simples para demonstrar a aplicação:

1. Chamar `/api/v1/health`.
2. Criar sessão em `/api/v1/sessions/reset`.
3. Enviar CPF pelo `/api/v1/chat`.
4. Enviar data de nascimento.
5. Pedir consulta de limite.
6. Pedir aumento de limite.
7. Informar novo limite desejado.
8. Se rejeitado, aceitar entrevista financeira.
9. Responder perguntas da entrevista.
10. Pedir cotação do dólar.

Os dados exatos de CPF e data devem ser conferidos no arquivo `clientes.csv` usado no ambiente local.

**Fluxo alternativo — Cadastro de novo cliente:**

1. Enviar frases como `"quero me cadastrar"`, `"quero me tornar cliente"` ou `"quero abrir uma conta"`.
2. Informar nome completo (mínimo nome e sobrenome).
3. Informar CPF.
4. Informar data de nascimento.

Regras de validação de entrada aplicadas no cadastro:

- Nome: obrigatoriamente pelo menos duas palavras com letras; entradas puramente numéricas são rejeitadas.
- Data: deve ser válida, no passado, com idade mínima de 16 anos e máxima de 120 anos.

---

## Testes

O projeto possui cobertura automatizada para:

- schemas Pydantic;
- services determinísticos;
- repositories CSV;
- normalização de entrada;
- cálculo de score;
- regras de crédito;
- StateGuard;
- LangGraph nodes e edges;
- fluxo completo mockado;
- providers LLM com HTTP fake;
- providers de câmbio com HTTP fake;
- bootstrap/configuração;
- endpoints FastAPI;
- envelopes de erro;
- privacidade da resposta pública.

Status atual da suíte:

```txt
697 testes passando
```

Comando principal:

```bash
python -m pytest
```

Para saída resumida:

```bash
python -m pytest -q
```

---

## Smokes manuais

Alguns scripts existem para validação manual controlada. Eles não fazem parte da suíte automatizada principal.

### Bootstrap

```bash
python scripts/smoke_bootstrap.py
```

Esse smoke valida presença e header dos CSVs de runtime e, quando as chaves obrigatórias estão presentes, valida também o wiring de dependências sem executar chamadas externas.

### Diagnóstico de runtime

```bash
python scripts/diagnose_runtime.py
```

Diagnóstico HTTP comparando localhost e 127.0.0.1:

```bash
python scripts/diagnose_http_chat.py
```

Esse diagnóstico imprime apenas informações seguras sobre settings, arquivos CSV e disponibilidade do graph de aplicação.

### Cotação real via SearchApi

```bash
python scripts/smoke_searchapi_exchange.py
```

Antes de rodar, configure `EXCHANGE_API_KEY` no ambiente local.

Esse script deve ser usado com cuidado, pois consome quota do provider externo. Ele imprime apenas dados seguros da cotação e não imprime a chave.

---

## Segurança

Principais cuidados adotados:

- `.env` real não deve ser commitado.
- `.env.example` contém apenas placeholders.
- chaves são lidas por variáveis de ambiente.
- providers recebem chave por argumento.
- código não imprime segredos.
- erros públicos não expõem stack trace.
- API não retorna `GraphState` completo.
- API não retorna `current_customer`.
- API não retorna `authenticated_cpf`.
- LLM não toma decisões críticas.
- output de LLM é validado antes de uso.
- CSV é acessado apenas por repositories.
- escrita em CSV usa estratégia segura.

Variáveis sensíveis principais:

```txt
XAI_API_KEY
OPENAI_API_KEY
EXCHANGE_API_KEY
```

---

## Limitações conhecidas

Esta é uma implementação V1 para desafio técnico.

Limitações atuais:

- sessões são mantidas em memória;
- reiniciar o processo apaga sessões;
- persistência principal usa CSV;
- smokes reais de providers externos são manuais;
- não há autenticação HTTP de usuário final na API;
- não há banco relacional;
- não há deploy configurado nesta etapa.

Essas limitações são intencionais para manter o foco no núcleo do desafio: arquitetura, orquestração, regras determinísticas, integração controlada com LLM e API backend.

---

## Estrutura resumida do backend

```txt
backend/
  app/
    api/
      admin.py
      chat.py
      dependencies.py
      health.py
      sessions.py

    bootstrap/
      dependencies.py
      graph.py

    config/
      settings.py

    exchange/
      provider.py
      searchapi_provider.py
      serpapi_provider.py

    graph/
      dependencies.py
      edges.py
      graph_builder.py
      nodes.py
      state.py

    llm/
      grok_provider.py
      intent_classifier.py
      manager.py
      mock_provider.py
      openai_provider.py
      provider.py

    repositories/
      credit_request_repository.py
      customer_repository.py
      score_limit_repository.py

    schemas/
      agent.py
      chat.py
      common.py
      credit.py
      customer.py
      errors.py
      exchange.py
      health.py
      llm.py
      session.py

    services/
      auth_service.py
      credit_service.py
      normalizer_service.py
      score_service.py
      session_service.py
      state_guard.py

    main.py
```

---

## Frontend

O projeto inclui uma interface web construída com React, Vite e TypeScript com Tailwind CSS.

A interface permite:

- autenticar com CPF e data de nascimento;
- cadastrar-se como novo cliente;
- consultar limite de crédito;
- solicitar aumento de limite;
- acompanhar a entrevista financeira passo a passo;
- consultar cotação de moedas;
- visualizar estado da sessão em tempo real no painel lateral;
- inspecionar os dados dos CSVs em tempo real pelo painel de desenvolvimento (`CsvBrowser`), disponível apenas em ambiente local.

### Como rodar o frontend

```bash
cd frontend
npm install
npm run dev
```

A interface ficará disponível em:

```txt
http://localhost:5173
```

O frontend espera o backend disponível em `http://localhost:8000`. A URL base da API pode ser configurada em `frontend/.env`.

---

## Desafios enfrentados e como foram resolvidos

### Controle do fluxo conversacional com múltiplos agentes

O maior desafio foi orquestrar transições entre agentes sem que o cliente perceba a mudança. O LangGraph resolve isso com nós e arestas explícitas, tornando cada transição auditável e testável independentemente.

### LLM como classificador, não como árbitro

O primeiro impulso natural é deixar a LLM decidir o fluxo completo. O problema: LLMs podem alucinar, são lentas e não garantem determinismo. A solução foi restringir a LLM apenas à classificação de intenção, validar a saída contra um enum rígido e rejeitar qualquer output fora do contrato esperado. Todas as regras de negócio críticas (autenticação, aprovação de crédito, cálculo de score) são determinísticas.

### Loops no grafo de estados

Durante a implementação, o agente de câmbio entrava em loop infinito ao pedir o par de moedas: `exchange_node` → `intent_node` → `exchange_node`. Isso ocorria porque `route_after_exchange` retornava `intent_node` em vez de `END` para o estado `ASKED_FOR_CURRENCY`. A correção foi ampliar o conjunto de ações que encerram o turno no roteador `route_after_exchange`.

### Continuidade após encerramento de tópico

Após uma cotação ou aprovação de crédito, o agente perguntava "posso ajudar com mais alguma coisa?". Uma resposta curta como "sim" era reclassificada pela LLM como `END_CONVERSATION` porque o contexto anterior se perdia entre chamadas. A solução foi implementar um mecanismo determinístico de continuidade baseado em `last_action_summary` e `current_state`, sem depender da LLM para detectar continuação de sessão.

### Ordem dos fluxos de crédito

O requisito pede que a entrevista seja oferecida antes de qualquer oferta parcial. A versão inicial oferecia um aumento parcial imediatamente na rejeição. A correção removeu o caminho inicial de oferta parcial do `credit_node`: na primeira rejeição, o agente sempre direciona para a entrevista. A oferta parcial só aparece após o recálculo de score.

### Persistência segura em CSV com concorrência

O CSV de clientes é lido e escrito por um único processo, mas requisições concorrentes poderiam gerar escrita parcial. A solução foi usar `portalocker` com timeout e escrita em arquivo temporário com substituição atômica, evitando corrupção de dados.

---

## Escolhas técnicas e justificativas

### Por que LangGraph?

O fluxo conversacional possui múltiplos estados, agentes especializados e transições condicionais. LangGraph ajuda a representar esse fluxo de forma explícita, testável e controlada.

### Por que CSV?

O desafio pede arquivos CSV como fonte de dados. Por isso, a persistência foi mantida em CSV, mas isolada em repositories para evitar acoplamento com regras de negócio.

### Por que LLM controlada?

LLMs são úteis para interpretar linguagem natural, mas não devem decidir regras críticas de banco. O projeto usa LLM apenas onde faz sentido e valida a saída antes de aplicar qualquer decisão.

### Por que providers injetados?

Providers externos podem falhar, mudar contrato ou exigir chaves. Ao injetá-los por abstração, os testes continuam isolados e o core do sistema permanece independente de APIs específicas.

---

## Critérios de qualidade aplicados

- Arquitetura antes de implementação.
- Testes antes de lógica sensível.
- Separação entre orquestração e regra de negócio.
- Contratos Pydantic para dados estruturados.
- Erros públicos padronizados.
- Providers externos isolados.
- Testes sem rede real.
- Sem segredo hardcoded.
- Sem exposição de estado interno.
- Código simples e auditável.
