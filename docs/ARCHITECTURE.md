# Banco Ágil - System Architecture

**Version:** 1.0
**Reference Documents:** PROJECT.md, REQUIREMENTS.md
**Status:** Finalized for V1 Implementation
**Purpose:** Define the technical architecture, component boundaries, data flow, orchestration strategy, persistence strategy, LLM strategy, security controls, and implementation structure for the Banco Ágil Intelligent Banking Agent system.

---

## 1. Architecture Objective

The objective of this architecture is to implement a conversational banking service using specialized AI agents without allowing the LLM to own business-critical decisions.

The system must provide:

* Explicit agent orchestration through LangGraph.
* Deterministic business services.
* CSV-based persistence with safe write strategy.
* Dual-provider LLM strategy using Grok as primary and OpenAI as fallback.
* React-based frontend with no business logic.
* Structured observability for traceability and assisted operation.
* Clear evolution path toward production-grade enterprise integration.

The core architectural position is:

```txt
LangGraph orchestrates the conversation.
Services own business decisions.
Repositories own persistence.
LLMs assist with language, not authority.
```

---

## 2. High-Level System View

```txt
┌──────────────────────────────────────────────┐
│              React Frontend                  │
│     Chat UI | Session UX | Error Display     │
└───────────────────────┬──────────────────────┘
                        │ HTTP/JSON
                        ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI API                            │
│ /api/v1/chat | /api/v1/health | /api/v1/sessions/reset │
└───────────────────────┬────────────────────────────────┘
                        │ Validated Request
                        ▼
┌──────────────────────────────────────────────┐
│             LangGraph Orchestrator           │
│      State Graph | Nodes | Conditional Edges │
└───────────────────────┬──────────────────────┘
                        │ Calls
                        ▼
┌──────────────────────────────────────────────┐
│                 Agent Layer                  │
│ Triage | Credit | Interview | Exchange       │
└───────────────────────┬──────────────────────┘
                        │ Uses
                        ▼
┌──────────────────────────────────────────────┐
│             Deterministic Services           │
│ Auth | Credit | Score | Exchange | Intent    │
│ Normalizer | Session | StateGuard            │
└───────────────────────┬──────────────────────┘
                        │ Reads/Writes
                        ▼
┌──────────────────────────────────────────────┐
│             Repository Layer                 │
│ CustomerCSV | ScoreLimitCSV | RequestCSV     │
└───────────────────────┬──────────────────────┘
                        │ File Lock + Atomic Writes
                        ▼
┌──────────────────────────────────────────────┐
│                  CSV Files                   │
│ clientes.csv | score_limite.csv | requests   │
└──────────────────────────────────────────────┘
```

---

## 3. Architectural Principles

### 3.1 Separation of Concerns

Each layer has one responsibility:

* Frontend renders interaction.
* API validates HTTP contracts.
* Graph orchestrates state transitions.
* Agents coordinate domain-specific conversations.
* Services execute deterministic rules.
* Repositories access data.
* LLM providers support language tasks only.

No layer may bypass the layer below it for convenience.

---

### 3.2 Deterministic Core

The following operations must never depend on raw LLM output:

* Authentication.
* Authentication attempt counting.
* Session blocking.
* Credit score calculation.
* Credit approval or rejection.
* CSV writes.
* State transition authorization.

---

### 3.3 Explicit State Over Implicit Conversation Memory

The system must not rely on the LLM remembering previous conversation details.

All relevant runtime state must live in `GraphState`.

`SessionState` is a conceptual alias only and must not become a separate competing implementation model.

The LLM receives only a compact structured context derived from `GraphState`, never unlimited raw chat history.

---

### 3.4 Framework With Boundaries

LangGraph is used because the problem is stateful and cyclic.

LangGraph is not used as a place to hide business logic.

Nodes coordinate work. Services decide outcomes.

---

## 3.5 Architecture Invariants

The following rules must never be violated:

1. GraphState is the single source of truth for runtime decisions
2. Conversational memory is optional and must never override structured state
3. Business logic must remain deterministic and service-owned
4. LLMs must not perform critical decisions
5. Repository layer must isolate persistence completely
6. State transitions must always pass through StateGuard
7. Fallback behavior must not change business outcomes
8. System must prefer safe failure over inconsistent behavior

Violation of these invariants indicates architectural regression

---

## 4. Runtime Components

## 4.1 Frontend

Technology:

* React
* TypeScript
* TailwindCSS
* Vercel deployment

Responsibilities:

* Render chat messages.
* Send user input to `POST /api/v1/chat`.
* Store `session_id` client-side.
* Display loading states.
* Display friendly errors.
* Allow user to reset session.
* Handle idle timeout UX.

Forbidden responsibilities:

* Authentication validation.
* Credit calculation.
* Score calculation.
* Agent routing.
* Direct CSV access.
* LLM provider selection.

Frontend state is UI state only.

---

## 4.2 FastAPI API Layer

Technology:

* FastAPI
* Pydantic v2 request/response models

Endpoints:

```txt
GET /api/v1/health
POST /api/v1/chat
POST /api/v1/sessions/reset
GET /api/v1/sessions/{session_id}
```

Responsibilities:

* Validate HTTP payloads.
* Create or reuse a `session_id`.
* Load current session state.
* Resolve and invoke LangGraph through bootstrap dependencies.
* Reuse cached dependency lifecycle objects when possible.
* Return normalized API response.
* Attach `trace_id` to responses.
* Convert internal errors into safe user-facing errors.
* Encapsulate provider/bootstrap failures without leaking internals.

Forbidden responsibilities:

* Implement business rules directly.
* Read or write CSV directly.
* Call LLM providers directly.
* Contain graph transition logic.
* Expose full `GraphState`, `current_customer`, or authenticated CPF in public responses.

---

## 4.3 LangGraph Orchestration Layer

Responsibilities:

* Maintain graph execution.
* Execute nodes.
* Evaluate conditional edges.
* Apply state transitions.
* Enforce transition structure.
* Emit trace logs for transitions.

LangGraph nodes must be thin orchestration functions.

They may:

* Read and update `GraphState`.
* Call agents.
* Call services through agents.
* Return next state metadata.

They must not:

* Write CSV directly.
* Calculate credit score directly.
* Approve credit directly.
* Trust LLM output without validation.

---

## 4.4 Agent Layer

Agents represent conversational capabilities.

Agents are not autonomous workers. They are bounded domain coordinators.

### Triage Agent

Coordinates:

* Greeting.
* CPF collection.
* Birth date collection.
* Authentication attempt handling.
* Authentication result messaging.
* Post-authentication intent routing preparation.

Operational split:

* Triage Auth (deterministic): greeting, CPF/date collection, authentication against `clientes.csv`, attempt counting, block after third consecutive failure.
* Triage Routing (AI controlled): only after `authenticated=True`, classify topic intent and route to the proper specialized agent.

Uses:

* `AuthService`
* `NormalizerService`
* `StateGuard`

Triage boundaries:

* LLM MUST NOT authenticate users.
* LLM MUST NOT read CSV or decide `authenticated=True`.
* LLM MAY assist only in intent routing after successful authentication.
* LLM output for routing MUST be validated against the `Intent` enum.

---

### Credit Agent

Coordinates:

* Credit limit consultation.
* Desired limit collection.
* Credit increase evaluation.
* Rejection messaging.
* Interview offer.

Uses:

* `CreditService`
* `NormalizerService`

Persistence is coordinated inside deterministic services through repository interfaces.

---

### Credit Interview Agent

Coordinates:

* Structured financial interview.
* Field-by-field collection.
* Score recalculation.
* Score update.
* Return to credit flow.

Uses:

* `ScoreService`
* `NormalizerService`

Customer score persistence must be coordinated through the appropriate service/repository boundary, not directly by the agent.

---

### Exchange Agent

Coordinates:

* Currency detection.
* Quote request.
* API failure recovery.
* User-facing exchange response.

Uses:

* `ExchangeService`
* `NormalizerService`

---

## 4.5 Deterministic Services

Services are stateless whenever possible.

They receive validated inputs and return typed outputs.

### AuthService

Responsibilities:

* Match CPF and birth date against `clientes.csv`.
* Return authentication result.
* Never decide UI messaging directly.

### SessionService

Responsibilities:

* Create session.
* Retrieve session state.
* Update session state.
* Reset session lifecycle for new conversations.
* Keep recent message window bounded.

V1 session state for API flows is stored in-memory only.

Process restarts clear all in-memory sessions.

`SessionService` coordinates lifecycle concerns around API session snapshots and must not introduce business logic.

Production evolution should use Redis or another durable session store.

### StateGuard

Responsibilities:

* Validate whether a state transition is allowed.
* Block protected flows before authentication.
* Reject invalid LLM-influenced transitions.
* Log transition violations.
* Redirect to a safe state.

### IntentService

Responsibilities:

* Classify user intent.
* Use LLM provider when available.
* Use deterministic keyword fallback when LLM fails.
* Return typed intent output.

### NormalizerService

Responsibilities:

* Normalize common financial and boolean expressions.
* Convert values like `R$ 5.000`, `5000 reais`, `10k`.
* Normalize yes/no debt answers.
* Reject ambiguous values.

### Normalization Boundary

Raw user input must be normalized before reaching deterministic business services.

Rules:

* Graph nodes or agent coordinators may call `NormalizerService`.
* `NormalizerService` converts user-facing inputs into typed values.
* Pydantic schemas validate normalized values.
* `AuthService`, `CreditService`, and `ScoreService` must receive typed and validated inputs.
* Business services must not call LLMs for normalization.
* Pydantic validators must remain deterministic and must not call LLM providers.

Examples:

```txt
"R$ 5.000" -> 5000.0 before CreditService
"12-05-1990" -> "1990-05-12" before AuthService
"sem dívidas" -> false before ScoreService
```

### CreditService

Responsibilities:

* Read current limit.
* Evaluate requested limit against score rules.
* Create formal credit request object.
* Return approval or rejection decision.

### ScoreService

Responsibilities:

* Calculate credit score.
* Apply weights.
* Validate bounds.
* Clip score between 0 and 1000.
* Return score plus decision rationale metadata.

### ExchangeService

Responsibilities:

* Query external exchange API.
* Validate external response.
* Return typed quote result.
* Handle provider failure without crashing the graph.

## 4.6 Bootstrap and Configuration Wiring

Bootstrap is the infrastructure layer that assembles real repositories and providers
from environment variables before graph execution.

Rules:

* Settings must read from process environment variables only.
* Settings must provide a safe summary that never exposes secret values.
* Bootstrap factories may instantiate concrete providers but must not call external APIs during wiring.
* Graph nodes must remain provider-agnostic and depend only on injected `GraphDependencies`.
* Secret values must never be printed by bootstrap scripts.

---

## 5. SessionState Architecture

The canonical implementation shape of runtime state is defined in `STATE_MACHINE.md` as `GraphState`. This section describes architectural responsibilities only and must not introduce alternate field names.

---

## 5.1 Session Persistence Strategy

Session state must persist across multiple requests within the same session.

V1 Strategy:

* Runtime graph state is persisted through LangGraph `MemorySaver`
* `session_id` must identify the graph thread/session
* `SessionService` coordinates session lifecycle, reset, and resume behavior
* State must be updated on every `POST /api/v1/chat` request
* V1 does not enforce backend session TTL expiration

Rules:

* Do not implement a second independent session-state store unless explicitly justified.
* `MemorySaver` is the V1 runtime state mechanism.
* `SessionService` manages lifecycle concerns around the graph state, not a competing source of truth.

Optional Enhancement:

* Provide endpoint:

```txt
GET /api/v1/sessions/{session_id}
```

* Legacy-compatible alias may also be exposed:

```txt
GET /api/v1/sessions/resume/{session_id}
```

Response must follow API_CONTRACT.md and use public-safe fields only:

```json
{
  "session_id": "string",
  "authenticated": true,
  "state": "CREDIT_MENU",
  "ended": false,
  "recent_messages": [],
  "trace_id": "uuid-v4"
}
```

Rules:

* This endpoint must not expose raw `GraphState`.
* This endpoint must not expose CPF in V1.
* `recent_messages` must contain at most the latest 3 turns.

---

## 6. LangGraph Design

## 6.1 Node Design

The graph will be composed of nodes that represent workflow steps, not free autonomous agents.

Planned nodes:

```txt
start_node
triage_node
intent_node
credit_node
credit_interview_node
exchange_node
registration_node
ending_node
```

Each node receives `GraphState` and returns a partial state update.

`SessionState` may be used conceptually in documentation, but the implementation model name for runtime graph state is `GraphState`.

Node output must be validated before graph continuation.

---

## 6.2 Conditional Edges

Conditional edges route based on structured state.

Examples:

```txt
if state.ended == true -> ending_node
if state.is_blocked == true -> ending_node
if state.authenticated == false -> triage_node
if state.intent == credit -> credit_node
if state.intent == exchange -> exchange_node
if state.intent == end -> ending_node
```

Edges must not route based only on raw LLM text.

---

## 6.3 State Guard Integration

Before executing protected nodes, the graph must call `StateGuard.check_entry`.

StateGuard validates in V1:

* Authentication requirement for protected nodes.
* Session blocked status.
* Ended conversation status.
* Auth-attempt limit gate.

Note:

* Full edge-to-edge transition validation exists as `StateGuard.check_transition`, but is not wired in the current V1 runtime path.

Invalid transition behavior:

1. Reject transition.
2. Log violation.
3. Redirect to safe state.
4. Return safe user-facing message.

---

## 6.4 Natural Language Bridging

When moving between domains, the response must explain the transition naturally without exposing internal agents.

Example:

```txt
Como sua solicitação não foi aprovada com o score atual, posso fazer algumas perguntas rápidas para atualizar sua análise de crédito.
```

This prevents abrupt user experience shifts while keeping internal handoff invisible.

---

## 6.5 Agent Circuit Breaker

The system must prevent infinite or low-quality conversational loops.

Rule:

* If intent classification fails 3 consecutive times in the same session:

```txt
unknown_intent_count >= 3
```

Then:

1. Transition to `ending_node`
2. Provide a graceful fallback message
3. Suggest alternative support channel

Example:

```txt
Não consegui entender exatamente o que você precisa.
Você pode tentar reformular sua pergunta ou procurar um canal de atendimento humano.
```

Tracking:

* `unknown_intent_count` must be stored in `GraphState`

Reset condition:

* Counter resets when a valid intent is identified

Rationale:

* Prevents infinite loops
* Demonstrates risk awareness
* Aligns with "War Room" mindset

---

## 7. LLM Architecture

## 7.1 Provider Strategy

The system uses a dual-provider strategy:

```txt
Primary: Grok via xAI API
Fallback: OpenAI
```

Configuration:

```txt
XAI_URL=https://api.x.ai/v1/chat/completions
OPENAI_URL=https://api.openai.com/v1/chat/completions
PRIMARY_MODEL=grok-4-1-fast
FALLBACK_MODEL=gpt-5.1
XAI_API_KEY=<secret>
OPENAI_API_KEY=<secret>
EXCHANGE_API_KEY=<optional-secret>
```

API keys must be loaded through environment variables only.

Canonical naming rule:

* The canonical variable for xAI/Grok authentication is `XAI_API_KEY`.
* `GROK_API_KEY` must not be used as the canonical project variable.

No key may be committed or exposed to frontend.

---

### Infrastructure-Level Resilience

LLM fallback must be treated as an infrastructure concern, not a business logic concern.

Rules:

* Fallback must not alter system behavior or decision flow
* Fallback must not change business outcomes
* Fallback must be transparent to agents and services
* Agents must not be aware of which provider is being used

Rationale:

* Keeps application logic stable regardless of provider behavior
* Prevents coupling between domain logic and LLM provider implementation

---

## 7.2 LLM Provider Interface

The application must define a provider interface similar to:

```python
class LLMProvider(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse:
        ...
```

Concrete implementations:

```txt
GrokProvider
OpenAIProvider
MockLLMProvider
```

A manager coordinates provider fallback:

```txt
LLMManager
  -> try GrokProvider
  -> if failure, try OpenAIProvider
  -> if failure, return controlled failure
```

---

## 7.3 Structured Context Strategy

The LLM must not receive raw unlimited chat history.

Instead, it receives a compact structured context:

```json
{
  "current_state": "IDENTIFYING_INTENT",
  "authenticated": true,
  "current_node": "intent_node",
  "supported_intents": ["credit", "exchange", "end"],
  "last_user_input": "quero aumentar meu limite",
  "constraints": [
    "Do not approve credit",
    "Do not authenticate customers",
    "Return only supported intent labels"
  ]
}
```

Rules:

* Structured context may include derived execution metadata such as `current_node`.
* Derived execution metadata must not be persisted as canonical `GraphState` fields unless defined in `STATE_MACHINE.md`.
* Use `last_user_input`, not `last_user_message`.

Benefits:

* Lower token cost.
* Lower leakage risk.
* Lower hallucination risk.
* Better fallback consistency.

Additional Context:

* The system MAY include the last 2-3 conversational turns for language continuity
* This must not replace structured state
* This must not exceed a predefined token budget

Priority order:

1. GraphState (authoritative)
2. Structured context
3. Short conversational memory

The system MUST NOT depend on conversational memory for business logic decisions

---

## 7.4 Fallback Flow

Fallback flow:

1. Build normalized LLM request from `GraphState`.
2. Try Grok.
3. If Grok fails, log provider error.
4. Try OpenAI with the same structured context.
5. If OpenAI fails, use deterministic keyword fallback.
6. If fallback classifier cannot decide, ask clarification.

The user must not be informed about provider fallback unless the whole operation fails.

---

## 7.5 Allowed LLM Tasks

Allowed:

* Intent classification.
* Natural language response polishing.
* Simple value extraction if validated afterward.
* Natural transition phrasing.

Forbidden:

* Authentication.
* Credit approval.
* Score calculation.
* CSV mutation.
* Final state transition authority.
* External API success fabrication.

---

## 8. Persistence Architecture

## 8.1 CSV Repository Pattern

CSV access must be isolated behind repository classes.

Repositories:

```txt
CustomerCSVRepository
ScoreLimitCSVRepository
CreditRequestCSVRepository
```

No service, agent, graph node, or API route may access CSV files directly.

---

## 8.2 File Locking

All write operations must acquire a file lock before modifying CSV files.

Rules:

* Locks must be acquired before any write operation
* Locks must be released immediately after operation
* Lock acquisition must have a timeout to prevent indefinite blocking

Limitation:

* File locks may remain orphaned if the process is terminated abruptly

Mitigation:

* Seed/reset script must remove orphan `.lock` files
* System must fail fast if lock cannot be acquired

Rationale:

* Prevents concurrent write corruption
* Accepts controlled failure over silent data corruption

---

## 8.3 Atomic CSV Writes

Full-file updates must use atomic write strategy.

Algorithm:

```txt
1. Acquire exclusive lock
2. Read original CSV
3. Apply update in memory
4. Write complete result to .tmp file
5. Validate .tmp header and required columns
6. Replace original using os.replace(tmp, target)
7. Release lock
```

Used for:

* Updating customer score in `clientes.csv`
* Any future update that rewrites an existing CSV

Append-only operations may append under lock when appropriate.

Used for:

* Adding rows to `solicitacoes_aumento_limite.csv`

---

## 8.4 Write Contention Strategy

Concurrent write attempts to CSV files may lead to contention.

V1 Strategy:

* Use file locking (`portalocker`) to ensure exclusive access during writes
* Fail fast if lock cannot be acquired within a short timeout

Example behavior:

```txt
If lock not acquired within 2 seconds:
    raise CSVWriteTimeoutError
```

Fallback behavior:

* Log contention event
* Return safe error message to user
* Do not retry automatically to avoid duplicate writes

Rationale:

* Simpler and predictable behavior
* Avoids introducing async write queues prematurely
* Keeps system transparent for evaluation

Future Evolution:

* Replace with write queue or message broker only if real concurrency becomes a requirement

---

Additional Responsibility:

* The seed script MUST detect and remove orphan `.lock` files before resetting CSV data

Example behavior:

```txt
If *.lock files exist in data directory:
    remove them before resetting CSV files
```

Rationale:

* Prevents system deadlock after abrupt process termination
* Ensures recoverability in ephemeral environments (e.g., Render free tier)

---

## 8.5 Seed Data Strategy

The project must include `seed_data.py`.

Responsibilities:

* Reset `clientes.csv`.
* Reset `score_limite.csv`.
* Reset `solicitacoes_aumento_limite.csv`.
* Preserve required headers.
* Provide predictable demo state.

This mitigates free-tier deployment filesystem limitations and helps evaluators test the system reliably.

---

## 8.6 Production Persistence Evolution

CSV is acceptable for the challenge but not ideal for production.

Production evolution path:

```txt
CSV Repository Interface
        ↓
SQLite Repository
        ↓
PostgreSQL Repository
        ↓
Audit Tables + Transactions
```

The architecture must keep repositories replaceable so that agents and services do not change when persistence changes.

---

## 9. Data Flow

## 9.1 Chat Request Flow

```txt
User types message
  ↓
React sends POST /api/v1/chat
  ↓
FastAPI validates ChatRequest
  ↓
SessionService loads or creates GraphState through MemorySaver lifecycle coordination
  ↓
LangGraph executes current node
  ↓
StateGuard checks entry for protected nodes
  ↓
Node calls agent
  ↓
Agent calls deterministic service
  ↓
Service calls repository or LLM provider if needed
  ↓
LangGraph returns updated state
  ↓
FastAPI returns ChatResponse
  ↓
React renders assistant reply
```

---

## 9.2 Credit Increase Flow

```txt
Authenticated user requests limit increase
  ↓
IntentNode classifies credit intent
  ↓
CreditNode asks desired limit
  ↓
NormalizerService normalizes amount
  ↓
CreditService validates requested amount
  ↓
CreditService reads customer and score limit data through repository interfaces
  ↓
CreditService approves or rejects
  ↓
CreditService registers evaluated request through CreditRequestRepository
  ↓
CreditNode returns result
```

---

## 9.3 Credit Interview Flow

```txt
Rejected request
  ↓
User accepts interview
  ↓
CreditInterviewNode collects financial fields
  ↓
NormalizerService normalizes each input
  ↓
Pydantic validates structured interview data
  ↓
ScoreService calculates new score
  ↓
A deterministic service coordinates customer score update through CustomerCSVRepository
  ↓
Temporary interview state is cleared
  ↓
User returns to credit flow
```

---

## 9.4 Exchange Flow

```txt
Authenticated user requests currency quote
  ↓
IntentNode detects exchange intent
  ↓
ExchangeNode identifies currency or defaults to USD
  ↓
ExchangeService calls external API
  ↓
External response is validated
  ↓
ExchangeNode returns quote or fallback message
  ↓
Temporary exchange state is cleared
```

Implementation note:

* The external exchange provider must remain behind an injected `ExchangeProvider` abstraction.
* SearchApi and SerpApi are distinct providers and must remain interchangeable behind the same abstraction.
* Graph nodes must never call provider SDKs directly.

Phase 8 note:

* `SearchApiExchangeProvider` is the initial provider implementation due current key availability.
* `SerpApiExchangeProvider` remains available as an adapter option.
* The graph still depends only on `deps.exchange_provider` (injection), never on provider-specific details.
* Automated tests for exchange provider integration must use fake HTTP clients and zero real network calls.

---

## 9.5 Latency and UX Strategy

The system must handle latency introduced by LLM calls and fallback logic.

Sources of latency:

* Primary LLM (Grok)
* Fallback LLM (OpenAI)
* External exchange API

Frontend requirements:

* Show loading indicator during processing
* Avoid blocking UI interactions
* Display progressive feedback if possible

Backend requirements:

* Measure latency per request
* Log provider latency
* Avoid unnecessary LLM calls

Optimization strategies:

* Use deterministic services whenever possible
* Use structured prompts with minimal tokens
* Avoid sending full conversation history

---

### UX Feedback Requirements

The frontend SHOULD provide progressive feedback messages during longer operations.

Examples:

```txt
"Analisando sua solicitação..."
"Consultando seu perfil..."
"Verificando limites disponíveis..."
"Buscando cotação atual..."
```

Rules:

* Messages must reflect the current operation context when possible
* Messages must not expose internal architecture (agents, providers, fallback)
* The system SHOULD update messages if fallback occurs, without explicitly mentioning provider failure
* Long operations (>5 seconds) MUST display visible feedback to avoid perceived system failure

Rationale:

* Prevents user abandonment during LLM fallback latency
* Improves perceived performance without changing backend behavior

---

## 10. Observability Architecture

## 10.1 Trace IDs

Trace ID ownership:

* The FastAPI entry layer is the only component allowed to create a new `trace_id`.
* If a valid `X-Trace-ID` header is provided, the entry layer may reuse it.
* If missing or invalid, the entry layer must create a UUID v4 trace ID.
* Downstream components must only receive and propagate the existing `trace_id`.
* Services, repositories, graph nodes, and LLM providers must not generate a new trace ID for the same request.

Every request must have a `trace_id`.

The same trace ID should be propagated through:

* API layer.
* Graph execution.
* Agents.
* Services.
* Repositories.
* LLM providers.

---

## 10.2 Structured Logs

Required log categories:

* API request received.
* Session loaded or created.
* Graph transition.
* StateGuard decision.
* LLM provider call.
* LLM fallback activation.
* Credit decision.
* Score recalculation.
* CSV write.
* External API failure.

Example:

```json
{
  "level": "INFO",
  "trace_id": "uuid",
  "session_id": "uuid",
  "event": "credit_decision",
  "agent": "credit",
  "score": 720,
  "requested_limit": 8000.0,
  "allowed_limit": 10000.0,
  "decision": "aprovado",
  "decision_rationale": "Requested limit is within allowed score range"
}
```

---

## 10.3 Token and Latency Tracking

When available, LLM logs must include:

* Provider.
* Model.
* Latency in milliseconds.
* Input tokens.
* Output tokens.
* Fallback status.

This supports cost and risk monitoring.

---

## 11. Security Architecture

## 11.1 Authentication Gate

Protected flows require authentication:

* Credit consultation.
* Credit increase request.
* Credit interview.
* Exchange quotation.

The backend is the authority. Frontend checks are not security controls.

---

## 11.2 Session Expiration (Roadmap)

V1 does not enforce backend TTL-based session expiration.

Current V1 behavior:

* Session state is process-local in MemorySaver
* Session state is lost on backend restart/redeploy
* Missing sessions are handled as `SESSION_NOT_FOUND`

Future direction (post-V1):

```txt
SESSION_TTL_MINUTES=30 (or equivalent)
```

When TTL is implemented, expired sessions must clear temporary sensitive state and require re-authentication.

---

## 11.3 Secret Management

Secrets must be environment variables:

```txt
XAI_API_KEY
OPENAI_API_KEY
EXCHANGE_API_KEY
SEARCHAPI_API_KEY (optional)
SERPAPI_API_KEY (optional)
```

Forbidden:

* Hardcoded secrets.
* `.env` committed to repository.
* Sending API keys to frontend.

---

## 11.4 Prompt Injection Defense

Prompt injection defense is handled through architecture:

* LLM cannot call repositories.
* LLM cannot approve credit.
* LLM cannot authenticate users.
* LLM output must be validated.
* StateGuard blocks invalid transitions.

---

## 12. Error Handling Architecture

## 12.1 Error Categories

The system should distinguish:

```txt
ValidationError
AuthenticationError
SessionNotFoundError
StateTransitionError
CSVReadError
CSVWriteError
LLMProviderError
ExternalAPIError
UnknownSystemError
```

---

## 12.2 User-Facing Error Policy

User-facing errors must be clear but not leak internals.

Example:

```txt
Não consegui consultar essa informação agora. Você pode tentar novamente em instantes ou escolher outro atendimento.
```

Internal logs may contain technical detail.

---

## 12.3 Recovery Policy

Recoverable failures should route to safe states.

Examples:

* LLM failure -> deterministic classifier.
* Exchange API failure -> return to intent identification.
* Invalid interview input -> ask field again.
* CSV write failure -> inform temporary issue and log error.
* Session not found -> reset session and restart flow.

---

## 12.4 Failure Mode Strategy

The system must behave predictably under failure conditions.

Failure scenarios:

1. LLM failure (both providers)
2. CSV write failure
3. Exchange API failure
4. Session not found on resume
5. Invalid state transition

Rules:

* Never crash the system
* Always return a controlled response
* Never expose internal errors to user
* Always log full error context internally

Fallback priorities:

1. Deterministic fallback (if possible)
2. Safe message to user
3. Transition to stable state (intent or ending)

The system must prefer degraded behavior over broken behavior.

---

## 13. Backend Folder Structure

```txt
backend/
  pyproject.toml
  pytest.ini
  .env.example

  app/
    __init__.py
    main.py

    api/
      __init__.py
      chat.py
      health.py
      sessions.py

    config/
      __init__.py
      settings.py

    core/
      __init__.py
      errors.py
      state_guard.py
      constants.py

    graph/
      __init__.py
      state.py
      nodes.py
      edges.py
      graph_builder.py

    agents/
      __init__.py
      triage_agent.py
      credit_agent.py
      credit_interview_agent.py
      exchange_agent.py

    services/
      __init__.py
      auth_service.py
      session_service.py
      intent_service.py
      normalizer_service.py
      credit_service.py
      score_service.py
      exchange_service.py

    repositories/
      __init__.py
      base_csv_repository.py
      customer_csv_repository.py
      score_limit_csv_repository.py
      credit_request_csv_repository.py

    llm/
      __init__.py
      provider.py
      manager.py
      grok_provider.py
      openai_provider.py
      mock_provider.py
      prompts.py

    schemas/
      __init__.py
      chat.py
      customer.py
      credit.py
      exchange.py
      session.py
      agent.py
      llm.py

    observability/
      __init__.py
      logger.py
      trace.py

    data/
      clientes.csv
      score_limite.csv
      solicitacoes_aumento_limite.csv

    scripts/
      seed_data.py

    tests/
      unit/
      integration/
```

---

## 14. Frontend Folder Structure

```txt
frontend/
  package.json
  index.html
  .env.example

  src/
    main.tsx
    App.tsx

    components/
      ChatWindow.tsx
      MessageBubble.tsx
      ChatInput.tsx
      SessionStatus.tsx
      ErrorBanner.tsx
      LoadingIndicator.tsx

    services/
      api.ts
      session.ts

    types/
      chat.ts

    styles/
      index.css
```

---

## 15. Dependency Direction Rules

Allowed dependency direction:

```txt
api -> graph -> agents -> services -> repositories
api -> services only for session/bootstrap concerns
services -> repositories
services -> llm only through interfaces when needed
agents -> llm only through IntentService or response formatting service
```

Forbidden:

```txt
repositories -> services
repositories -> agents
repositories -> graph
services -> api
agents -> api
frontend -> repositories
frontend -> graph
llm -> repositories
```

---

## 16. Testing Architecture

## 16.1 Unit Tests

Target:

* Services.
* Repositories.
* Normalizers.
* StateGuard.
* LLMManager fallback.

Unit tests must not depend on live APIs or live LLM providers.

---

## 16.2 Integration Tests

Target:

* Full authentication flow.
* Credit approval flow.
* Credit rejection plus interview flow.
* Exchange fallback flow.
* LangGraph state routing.
* API `/api/v1/chat` behavior.

External APIs and LLM providers must be mocked.

---

## 16.3 Manual Demo Tests

Manual demo tests should verify:

* Public frontend link works.
* Session can authenticate.
* Credit limit can be consulted.
* Credit increase request is recorded.
* Rejected user can complete interview.
* Exchange quote handles success or graceful failure.
* Reset session works.

---

## 17. Deployment Architecture

## 17.1 Frontend Deployment

Target:

```txt
Vercel
```

Required environment variable:

```txt
VITE_API_BASE_URL
```

---

## 17.2 Backend Deployment

Target options:

```txt
Railway
Render
```

Required environment variables:

```txt
XAI_API_KEY
OPENAI_API_KEY
EXCHANGE_API_KEY
SEARCHAPI_API_KEY (optional)
SERPAPI_API_KEY (optional)
PRIMARY_MODEL
FALLBACK_MODEL
SESSION_TTL_MINUTES
```

---

## 17.3 Deployment Limitation

Free-tier deployments may have ephemeral filesystem storage.

Mitigation:

* Provide `seed_data.py`.
* Document limitation in README.
* Keep CSV files versioned with sample data.
* Avoid promising durable production persistence.

---

## 18. Architecture Trade-Offs

## 18.1 LangGraph vs Custom State Machine

Decision: use LangGraph.

Reason:

* Aligns with target role requirements.
* Makes agent transitions explicit.
* Supports cyclic flows naturally.
* Improves explainability of orchestration.

Risk:

* Adds dependency and learning overhead.

Mitigation:

* Keep business logic outside graph nodes.
* Keep graph small.
* Document state machine separately.

---

## 18.2 React vs Streamlit

Decision: use React.

Reason:

* Better evaluator experience through public web deployment.
* Clearer separation between frontend and backend.
* More production-oriented demonstration.

Risk:

* More implementation work than Streamlit.

Mitigation:

* Keep frontend minimal.
* Avoid business logic in frontend.

---

## 18.3 CSV vs SQLite/PostgreSQL

Decision: use CSV for V1.

Reason:

* Required by challenge.
* Simpler to inspect.
* Keeps scope aligned.

Risk:

* Weak persistence and concurrency characteristics.

Mitigation:

* Repository pattern.
* File locks.
* Atomic writes.
* Seed reset script.
* Clear production evolution path.

---

## 18.4 LLM vs Deterministic Classifier

Decision: use LLM with deterministic fallback.

Reason:

* Demonstrates LLM integration.
* Provides natural language flexibility.
* Maintains resilience when provider fails.

Risk:

* Cost, latency, hallucination.

Mitigation:

* Structured context.
* Pydantic validation.
* Provider fallback.
* Keyword classifier fallback.
* StateGuard.

---

## 19. Production Evolution Path

If this system evolved beyond the challenge:

```txt
CSV -> PostgreSQL
In-memory session -> Redis
Structured logs -> OpenTelemetry
Manual deploy -> CI/CD pipeline
Basic external API -> enterprise integration layer
Direct tools -> MCP tool layer
No RAG -> RAG over policies and manuals
Single chat UI -> Operator dashboard + audit console
```

This evolution path must not be implemented in V1 unless the core challenge is already complete.

---

## 20. Architecture Completion Criteria

The architecture is satisfied when:

1. The backend follows layered dependency rules.
2. LangGraph owns orchestration but not business decisions.
3. Services own deterministic rules.
4. Repositories isolate CSV access.
5. File writes are protected with locks and atomic strategy where needed.
6. LLM usage is constrained behind provider interfaces.
7. Fallback from Grok to OpenAI is implemented.
8. Deterministic fallback exists for basic intent classification.
9. StateGuard blocks invalid transitions.
10. React frontend contains no business logic.
11. Logs expose enough metadata for debugging and assisted operation.
12. Tests cover deterministic core and graph routing.
13. README explains architecture and known limitations clearly.
