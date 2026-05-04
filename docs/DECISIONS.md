# Banco Ágil - Architecture Decision Records

**Version:** 1.0
**Reference Documents:** PROJECT.md, REQUIREMENTS.md, ARCHITECTURE.md, STATE_MACHINE.md
**Status:** Finalized for V1 Implementation
**Purpose:** Record the key technical decisions behind the Banco Ágil Intelligent Banking Agent system, including context, rationale, trade-offs, rejected alternatives, and consequences.

---

## 1. Purpose of This Document

This document explains why the system is designed the way it is.

It exists to prevent undocumented architectural drift during implementation. Any relevant technical change that contradicts or materially alters these decisions must be recorded here as a new ADR or as an update to an existing ADR.

This document is also part of the technical defense for the project. It demonstrates that the architecture was designed intentionally, not assembled through framework-driven improvisation.

---

## 2. Decision Principles

All decisions must follow these principles:

1. Business-critical rules must be deterministic.
2. LLMs may assist with language, but must not own financial decisions.
3. State must be explicit and testable.
4. Architecture must remain explainable under interview pressure.
5. Complexity must be justified by challenge requirements or target-role alignment.
6. CSV is the required persistence format for the challenge, but must be isolated behind repositories.
7. The system must be demo-friendly without pretending to be production banking infrastructure.
8. Documentation must guide implementation, not merely describe it afterward.

---

## ADR-001 - Use LangGraph for Agent Orchestration

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Architecture / Agent Orchestration

### Context

The challenge requires multiple specialized AI agents:

* Triage Agent
* Credit Agent
* Credit Interview Agent
* Exchange Agent

The flow is stateful and cyclic. For example, a rejected credit request may send the customer to a credit interview, then return them to the credit flow for a new analysis.

The target role also explicitly values experience with agent frameworks such as LangGraph, CrewAI, Agno, or OpenAI Agents SDK.

### Decision

Use **LangGraph** as the orchestration layer for agent state transitions.

LangGraph will manage:

* Node execution.
* Conditional edges.
* Session state propagation.
* Cyclic flows.
* Explicit state transitions.
* Checkpointing through `MemorySaver` in V1.

### Rationale

LangGraph fits this challenge because the system is closer to a deterministic state machine than to a group of autonomous agents.

It provides enough structure to model controlled handoffs while keeping routing inspectable and testable.

### Alternatives Considered

#### CrewAI

Rejected for V1.

CrewAI is stronger for autonomous task collaboration, but this project needs strict business-rule control, authentication gates, and deterministic transitions.

Risk: agents could appear too autonomous for a banking workflow.

#### Custom State Machine Only

Rejected as the primary approach.

A custom state machine would provide maximum control, but would miss an opportunity to align the project with the target role's agent-framework requirements.

#### OpenAI Agents SDK

Rejected for V1.

Useful, but the current flow benefits more from explicit graph-based state routing.

### Consequences

Positive:

* Strong alignment with target role.
* Explicit state graph.
* Cyclic flow support.
* Easier technical explanation.
* Better observability of agent transitions.

Negative:

* Additional dependency.
* Requires discipline to avoid putting business logic inside graph nodes.

### Guardrail

LangGraph must orchestrate the flow, not own business decisions.

Business logic remains in deterministic services.

---

## ADR-002 - Keep Business Logic in Deterministic Services

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Domain Logic / Safety

### Context

The system handles banking-adjacent flows such as authentication, credit score calculation, and credit limit approval.

These flows must be predictable and testable.

LLMs are probabilistic and may hallucinate, misclassify, or follow malicious user instructions.

### Decision

All business-critical decisions must be implemented in deterministic backend services.

This applies to:

* Authentication.
* Authentication attempt counting.
* Session blocking.
* Credit score calculation.
* Credit limit approval or rejection.
* CSV persistence.
* State transition authorization.

### Rationale

The LLM should assist with language and interpretation, but not decide financial outcomes.

This keeps the system auditable, testable, and safe.

### Alternatives Considered

#### LLM-driven decision-making

Rejected.

It would reduce implementation effort but introduce unacceptable risk for authentication and credit decisions.

#### Hybrid service + LLM decision

Rejected for core financial decisions.

Even if LLM output were checked afterward, it would create unnecessary ambiguity about authority.

### Consequences

Positive:

* Strong testability.
* Lower hallucination risk.
* Easier debugging.
* Clearer technical defense.

Negative:

* More explicit service code required.
* Less “magical” agent behavior.

### Guardrail

If a behavior affects money, identity, persistence, or state authorization, it belongs in a service, not in the LLM.

---

## ADR-003 - Use Grok as Primary LLM and OpenAI as Fallback

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** LLM Provider Strategy / Resilience

### Context

The project needs LLM capabilities for:

* Intent classification.
* Natural language response generation.
* Simple user input interpretation.
* Natural language bridging between flows.

The user has more available API credits for Grok, but a single-provider dependency would create a point of failure.

### Decision

Use a dual-provider strategy:

```txt
Primary provider: Grok / xAI
Fallback provider: OpenAI
```

Configuration:

```txt
XAI_URL=https://api.x.ai/v1/chat/completions
OPENAI_URL=https://api.openai.com/v1/chat/completions
PRIMARY_MODEL=grok-4-1-fast
FALLBACK_MODEL=gpt-5.1
XAI_API_KEY=<secret>
OPENAI_API_KEY=<secret>
```

API keys must be loaded only from environment variables.

Canonical naming:

* The canonical environment variable for xAI/Grok is `XAI_API_KEY`, following xAI documentation.
* `GROK_API_KEY` may appear as a legacy alias in old notes, but must not be the canonical variable.

### Rationale

This gives the project:

* Cost efficiency through primary use of Grok.
* Resilience through OpenAI fallback.
* Better alignment with consulting expectations around availability.
* A clean abstraction point for future provider changes.

### Alternatives Considered

#### Grok only

Rejected.

Cheaper for this user, but creates a single point of failure.

#### OpenAI only

Rejected.

Technically viable, but less aligned with available credits.

#### Provider chosen manually at runtime

Rejected for V1.

Adds unnecessary operational burden.

### Consequences

Positive:

* Better availability.
* Clear provider abstraction.
* Demonstrates resilience thinking.

Negative:

* Additional implementation complexity.
* Two sets of provider errors to normalize.
* Token and latency observability become more important.

### Guardrail

Fallback is infrastructure behavior. It must not change business outcomes.

Agents and services must not know which provider was used.

---

## ADR-004 - Use Structured LLM Context Instead of Full Chat History

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** LLM Safety / Cost Control

### Context

The system needs enough context for natural responses, but sending the full chat history increases:

* Token cost.
* Latency.
* Privacy risk.
* Hallucination risk.
* Prompt injection surface.

### Decision

LLM calls must receive a compact structured context derived from `GraphState`.

The system may include only the last 2-3 conversational turns for UX continuity.

Priority order:

1. `GraphState` as authority.
2. Structured context.
3. Short conversational memory.

### Rationale

The LLM does not need full conversation history to classify intent or format responses.

State is more reliable than memory.

### Alternatives Considered

#### Full chat history

Rejected.

Too expensive and noisy for this workflow.

#### No conversational memory

Rejected.

Would make transitions less natural and could harm UX.

### Consequences

Positive:

* Lower token cost.
* Better provider fallback consistency.
* Lower hallucination risk.
* Better control over sensitive data.

Negative:

* Slightly less conversational richness.

### Guardrail

Conversational memory must never override structured state.

---

## ADR-005 - Use React + TypeScript + Tailwind Instead of Streamlit

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Frontend / Demo Strategy

### Context

The challenge suggests Streamlit as a possible UI option, but does not require Streamlit exclusively.

The evaluator experience matters. A deployed web interface reduces friction because the evaluator can test the application without cloning the repository and running it locally.

### Decision

Use a React + TypeScript + Tailwind frontend deployed on Vercel.

The frontend will be a thin chat interface.

### Rationale

React provides:

* Better demo experience.
* Better separation between frontend and backend.
* Better alignment with production-like delivery.
* More professional evaluator experience.

### Alternatives Considered

#### Streamlit

Rejected as the primary UI.

It is faster for local prototypes but less representative of a production-facing web interface.

#### Next.js

Not required for V1.

SSR and routing complexity are unnecessary for a single chat interface.

### Consequences

Positive:

* Public web demo.
* More realistic frontend/backend split.
* Clearer API contract.

Negative:

* More setup than Streamlit.
* Requires deployment of two components.

### Guardrail

No business logic may exist in the frontend.

The frontend only renders chat state and calls backend APIs.

---

## ADR-006 - Keep CSV as Official Persistence Layer for V1

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Persistence / Challenge Compliance

### Context

The challenge explicitly requires CSV files for:

* `clientes.csv`
* `score_limite.csv`
* `solicitacoes_aumento_limite.csv`

A real production system would use a database, but replacing CSV with SQL immediately would weaken compliance with the challenge.

### Decision

Use CSV as the official persistence layer for V1.

All CSV access must be isolated behind repository classes.

### Rationale

This satisfies the challenge while keeping a clean path to future persistence replacement.

Repositories protect the rest of the system from CSV-specific implementation details.

### Alternatives Considered

#### SQLite as primary persistence

Rejected for V1.

It would be more robust, but could look like avoiding the challenge requirement.

#### PostgreSQL

Rejected for V1.

Overkill for the challenge scope and deployment complexity.

#### In-memory-only storage

Rejected.

Does not satisfy CSV persistence requirements.

### Consequences

Positive:

* Direct compliance with challenge.
* Easy evaluator inspection.
* Simple local execution.

Negative:

* Weak production persistence.
* Concurrency limitations.
* Ephemeral deployment limitations.

### Guardrail

No component except repositories may read or write CSV files.

---

## ADR-007 - Use File Locks and Atomic Writes for CSV Safety

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Persistence Safety

### Context

CSV files do not provide transactional guarantees.

Concurrent writes or process termination during write operations may corrupt files.

### Decision

CSV writes must use:

* File locking.
* Timeout-based lock acquisition.
* Atomic write strategy for full-file updates.
* Temporary files and `os.replace`.
* Temporary file validation before replacement.

Full-file update algorithm:

```txt
1. Acquire lock
2. Read original CSV
3. Apply update in memory
4. Write .tmp file
5. Validate .tmp headers
6. Validate required columns
7. Validate row shape consistency
8. If validation succeeds, replace original file with os.replace
9. If validation fails, delete .tmp file and keep original CSV unchanged
10. Release lock
```

* The system must never replace a valid original CSV with an invalid .tmp file.

### Rationale

This reduces risk while keeping implementation proportional to challenge scope.

---

## ADR-008 - Treat Triage as Hybrid Agent (Auth + Routing)

**Status:** Accepted
**Date:** 2026-05-02
**Decision Type:** Orchestration / Security Boundary

### Context

The challenge defines a Triage Agent that both authenticates users and identifies the request subject for handoff.

To preserve deterministic security while respecting the challenge wording, triage must include two distinct responsibilities with different authority levels.

### Decision

Model Triage Agent as a hybrid with two internal phases:

* Triage Auth (deterministic): collects CPF and birth date, authenticates against `clientes.csv`, manages failed attempts, and blocks on the third consecutive failure.
* Triage Routing (AI controlled): runs only after successful authentication and classifies intent for handoff.

### Rationale

This keeps authentication and access control deterministic while still using IA where it adds value for natural-language routing.

### Guardrails

* IA must not authenticate users.
* IA must not validate CPF/date for access decisions.
* IA must not read CSV repositories directly.
* IA output must be validated against `Intent` enum before routing.
* Authentication gating must remain mandatory before routing to protected domains.

### Consequences

Positive:

* Aligns with challenge framing of specialized IA agents.
* Preserves deterministic security controls.
* Improves explainability of triage responsibilities.

Negative:

* Adds explicit documentation and test scope split between auth and routing.

### Alternatives Considered

#### Async write queue

Rejected for V1.

Useful in higher-concurrency systems, but excessive for this challenge.

#### Real write-ahead log

Rejected for V1.

Too much infrastructure for CSV-based challenge data.

#### Direct writes without lock

Rejected.

Too fragile.

### Consequences

Positive:

* Lower corruption risk.
* Demonstrates engineering maturity.
* Still simple enough to implement.

Negative:

* Slightly more repository complexity.
* Lock contention may still occur.

### Guardrail

The system must prefer safe failure over silent corruption.

If `.tmp` validation fails:

* The original CSV must remain unchanged.
* The `.tmp` file must be discarded.
* The error must be logged with `trace_id`.
* The user must receive a controlled failure message if the operation affects the current flow.

---

## ADR-008 - Provide seed_data.py for Data Reset

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Demo Reliability / Data Recovery

### Context

Free-tier deployment environments may use ephemeral filesystem storage.

CSV files may be reset, lost, or left in inconsistent state after deploys or restarts.

File lock artifacts may also remain after abrupt process termination.

### Decision

Provide a `seed_data.py` script.

The script must:

* Reset `clientes.csv`.
* Reset `score_limite.csv`.
* Reset `solicitacoes_aumento_limite.csv`.
* Preserve required headers.
* Remove orphan `.lock` files.

### Rationale

This ensures evaluators can restore the project to a known good state.

### Alternatives Considered

#### Ignore ephemeral filesystem limitation

Rejected.

Would make the demo fragile.

#### Use production database to solve persistence

Rejected for V1.

Would increase scope and weaken CSV compliance.

### Consequences

Positive:

* Predictable demo environment.
* Easier recovery.
* Clear evaluator instructions.

Negative:

* Does not provide durable production persistence.

### Guardrail

README must clearly document that CSV persistence is challenge-oriented, not production-grade.

---

## ADR-009 - Implement StateGuard as Transition Safety Layer

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Security / Orchestration

### Context

LLM-assisted systems may produce invalid outputs or be manipulated by user prompts.

For a banking workflow, a user must not bypass authentication, force a credit approval, or jump into protected flows.

### Decision

Implement `StateGuard` as an explicit transition validation layer.

StateGuard must validate:

* Authentication gate.
* Allowed next states.
* Blocked session status.
* Session expiration.
* Domain cleanup.
* Invalid transition attempts.

### Rationale

StateGuard makes safety enforceable in code, not dependent on prompt instructions.

### Alternatives Considered

#### Prompt-only restrictions

Rejected.

Prompt instructions are not security controls.

#### Let LangGraph edges handle everything

Rejected.

Edges define routing, but a dedicated guard makes safety rules explicit and testable.

### Consequences

Positive:

* Better safety.
* Easier testing.
* Stronger defense against prompt injection.
* Clearer architecture.

Negative:

* Additional implementation layer.

### Guardrail

No protected transition may execute without StateGuard validation.

---

## ADR-010 - Use MemorySaver Checkpointer for V1 Runtime State

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** State Persistence / LangGraph Runtime

### Context

The system must maintain conversation state across multiple `POST /api/v1/chat` requests.

LangGraph supports checkpointers. For V1, durable external state storage would increase complexity.

### Decision

Use LangGraph `MemorySaver` as the V1 runtime checkpointer.

### Rationale

MemorySaver provides enough continuity for local and demo execution while keeping scope controlled.

### Alternatives Considered

#### Redis-backed checkpointer

Rejected for V1.

More production-ready but unnecessary for the challenge.

#### Database-backed checkpointer

Rejected for V1.

Adds operational complexity.

#### No checkpointer

Rejected.

Would make multi-turn conversations unreliable.

### Consequences

Positive:

* Supports multi-turn sessions.
* Simple integration.
* Aligns with LangGraph usage.

Negative:

* State is process-local.
* State is lost on backend restart.

### Guardrail

README must document that runtime session continuity is not durable across redeploys in V1.

---

## ADR-011 - Use Session TTL for Sensitive Runtime State

**Status:** Deferred (Post-V1)
**Date:** 2026-04-30
**Decision Type:** Security / Session Management

### Context

The system stores sensitive session data such as CPF candidate, authenticated CPF, and customer context.

Keeping this data indefinitely in memory is unsafe.

### Decision

Use configurable session TTL in a post-V1 phase.

Target default:

```txt
SESSION_TTL_MINUTES=30
```

When implemented, expired sessions must clear sensitive temporary state and require re-authentication.

### V1 Implementation Note

In V1, backend TTL expiration is intentionally out of scope.

Current behavior:

* Runtime session state is process-local in MemorySaver
* Sessions are lost on backend restart/redeploy
* Missing session handling uses SESSION_NOT_FOUND with reset flow

### Rationale

This reduces exposure of sensitive runtime data.

### Alternatives Considered

#### No expiration

Rejected.

Unsafe and unrealistic for a banking workflow.

#### Very short expiration

Rejected.

Could harm demo usability.

### Consequences

Positive:

* Better security posture.
* Clearer session lifecycle.

Negative:

* User may need to re-authenticate after inactivity.

### Guardrail

Backend is authoritative for session validity. Frontend timeout is only UX support.

---

## ADR-012 - Add Agent Circuit Breaker for Unknown Intent Loops

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Conversation Safety / UX

### Context

Conversational systems may enter loops when intent cannot be classified.

Repeated clarification questions degrade UX and make the system appear broken.

### Decision

Track unknown intent attempts per session.

If intent classification fails three consecutive times, the system transitions to a safe ending state.

### Rationale

This prevents infinite loops and demonstrates assisted-operation risk awareness.

### Alternatives Considered

#### Infinite clarification loop

Rejected.

Poor UX and unsafe behavior.

#### Immediate termination after one unknown intent

Rejected.

Too aggressive.

### Consequences

Positive:

* Better loop control.
* Clear failure behavior.
* Easier testing.

Negative:

* Some valid but unusual requests may terminate early after repeated ambiguity.

### Guardrail

Counter must reset after a valid intent is detected.

---

## ADR-013 - Use Natural Language Bridging Between Domains

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** UX / Conversational Design

### Context

Internal agent transitions must be invisible to the user.

However, abrupt topic changes can feel unnatural.

Example: after credit rejection, immediately asking for income may feel disconnected.

### Decision

Use `system_bridge_message` to preserve natural continuity between domains.

### Rationale

This improves UX while keeping internal handoff mechanics hidden.

### Alternatives Considered

#### Direct agent handoff without transition message

Rejected.

May feel abrupt.

#### Expose agent names to user

Rejected.

Violates invisible handoff requirement.

### Consequences

Positive:

* Better conversation flow.
* Cleaner user experience.
* Maintains abstraction of a single assistant.

Negative:

* Requires careful state handling.

### Guardrail

Bridge messages must not alter business logic.

---

## ADR-014 - Avoid RAG in V1

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Scope Control / Anti-Overengineering

### Context

RAG is useful when agents need to answer from unstructured knowledge bases, policies, manuals, FAQs, or documentation.

The current challenge uses structured CSV data and deterministic business rules.

### Decision

Do not implement RAG in V1.

Document RAG as a future production enhancement.

### Rationale

There is no real document corpus in the challenge.

Adding RAG now would create fake complexity without improving the core solution.

### Alternatives Considered

#### Add RAG with synthetic documents

Rejected.

Would be artificial and distracting.

#### Use RAG for CSV lookup

Rejected.

CSV lookups should be deterministic repositories, not semantic retrieval.

### Consequences

Positive:

* Lower complexity.
* Cleaner challenge focus.
* Better deterministic behavior.

Negative:

* Less demonstration of retrieval architecture in V1.

### Guardrail

If a policy document corpus is introduced later, RAG may be reconsidered.

---

## ADR-015 - Avoid MCP in V1

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Scope Control / Tooling Strategy

### Context

MCP is useful when agents need standardized access to external tools such as CRM, ERP, ticketing systems, document repositories, and enterprise APIs.

The current challenge uses simple explicit integrations:

* CSV repositories.
* External exchange API.

### Decision

Do not implement MCP in V1.

Document MCP as a future enterprise integration strategy.

### Rationale

Direct backend services are simpler, safer, and easier to test for this challenge.

### Alternatives Considered

#### Wrap CSV and exchange API as MCP tools

Rejected.

Would add tool infrastructure without meaningful benefit.

#### Use MCP for all service calls

Rejected.

Would obscure simple deterministic logic.

### Consequences

Positive:

* Lower implementation complexity.
* Clearer service boundaries.
* Easier testing.

Negative:

* Does not demonstrate MCP hands-on in V1.

### Guardrail

MCP must not replace deterministic services if introduced later.

---

## ADR-016 - Use Explicit Error Recovery Instead of error_recovery_node in V1

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** State Machine Simplicity

### Context

A dedicated `error_recovery_node` could centralize error handling, but it would also add an additional orchestration layer.

For V1, failures are limited and can be handled through structured state fields.

### Decision

Do not create a dedicated `error_recovery_node` in V1.

---

Use explicit recovery fields:

```txt
recoverable_error
retry_available
last_error
system_bridge_message
```

### Rationale

This keeps the graph smaller and easier to test.

### Alternatives Considered

#### Dedicated error recovery node

Rejected for V1.

Useful in larger systems, but unnecessary here.

#### No structured error recovery

Rejected.

Would make failures ambiguous.

### Consequences

Positive:

* Smaller graph.
* Explicit recovery behavior.
* Easier implementation.

Negative:

* Some recovery behavior is distributed across nodes.

### Guardrail

Recovery behavior must be documented in `STATE_MACHINE.md` and covered by tests.

---

## ADR-017 - Use Backend as Authority for Session State

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Security / Frontend Boundary

### Context

The frontend stores session ID for UX continuity, but it cannot be trusted as a security authority.

Users may refresh, manipulate local storage, or replay requests.

### Decision

Backend is the only authority for:

* Session validity.
* Authentication status.
* State transitions.
* Expiration.
* Blocked sessions.

### Rationale

This avoids trusting client-side state for security-sensitive decisions.

### Alternatives Considered

#### Frontend-managed session state

Rejected.

Unsafe and easy to manipulate.

#### Stateless backend with full state in client

Rejected.

Unacceptable for this workflow.

### Consequences

Positive:

* Better security.
* Cleaner responsibilities.

Negative:

* Backend must maintain runtime state.

### Guardrail

Frontend state is UI state only.

---

## ADR-018 - Use Minimal API Surface for V1

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** API Scope

### Context

The project needs to support a chat-based experience and basic session reset.

A larger API surface could distract from the agent workflow.

### Decision

Expose only:

```txt
GET /api/v1/health
POST /api/v1/chat
POST /api/v1/sessions/reset
```

Optional enhancement:

```txt
GET /api/v1/sessions/resume/{session_id}
```

### Rationale

Minimal API keeps the system easier to test and document.

### Alternatives Considered

#### Separate endpoints for each agent

Rejected.

Would leak internal architecture to the frontend.

#### Full admin API

Rejected for V1.

Out of scope.

### Consequences

Positive:

* Simple frontend integration.
* Clean abstraction.
* Less surface area for bugs.

Negative:

* Less direct inspection of internal flows through HTTP.

### Guardrail

Internal agent names and graph mechanics must not drive the public API design.

---

## ADR-019 - Use Hierarchical Data Normalization

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Input Handling / Data Normalization

### Context

Users may provide values in natural language or informal financial formats.

Examples:

```txt
R$ 5.000
5000 reais
10k
sem dívidas
tenho dívidas
```

* The system must be usable without blindly delegating parsing to the LLM.

### Decision

Use a hierarchical normalization strategy.

Normalization order:

```txt
1. Deterministic parsing with regex and explicit rules
2. Pydantic validation
3. LLM-assisted extraction only when deterministic parsing is insufficient
4. Rejection with clarification when ambiguity remains
```

The LLM may assist with normalization only when its output is validated before use.

### Rationale

This keeps the system predictable, cheaper, faster, and easier to test.

Common formats should not require an LLM call.

### Alternatives Considered

#### LLM-only normalization

Rejected.

It would increase cost, latency, and non-determinism.

#### Regex-only normalization

Rejected as the only strategy.

It is predictable, but may be too rigid for natural conversation.

#### Reject all non-numeric input

Rejected.

It would harm UX and make the assistant feel unnecessarily brittle.

### Consequences

Positive:

* Lower LLM cost.
* Better testability.
* Better UX for common user inputs.
* Lower hallucination risk.

Negative:

* More explicit parsing logic required.
* Some edge cases still require clarification.

### Guardrail

Pydantic validators must remain deterministic.

Allowed inside validators:

* Type coercion
* Range validation
* Enum validation
* Simple deterministic normalization
* Regex-based validation

Forbidden inside validators:

* LLM calls
* HTTP calls
* CSV access
* Repository access
* Business decisions that require external state

If normalization requires LLM assistance, it must happen outside Pydantic validators and its output must be validated afterward.

---

## ADR-020 - Use Structured Logging and Trace Correlation

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Observability / Assisted Operation

### Context

The target role involves risk monitoring, assisted operation, and technical communication during incidents.

The system must make it possible to understand what happened during a conversation without exposing internal details to the end user.

### Decision

Use structured JSON logs with a manually propagated `trace_id`.

The `trace_id` must be created or attached at API entry and propagated through:

* FastAPI route
* SessionService
* LangGraph execution
* Agent nodes
* Services
* Repositories
* LLM provider calls
* External API calls

Recommended format:

```json
{
  "timestamp": "2026-04-30T12:00:00Z",
  "level": "INFO",
  "trace_id": "uuid-v4",
  "session_id": "session-id",
  "event": "credit_decision",
  "component": "CreditService",
  "agent": "credit",
  "from_state": "ASKING_NEW_LIMIT",
  "to_state": "PROCESSING_CREDIT_REQUEST",
  "decision_rationale": "Requested limit is within allowed score range"
}
```

### Rationale

Manual structured tracing is enough for V1 and easier to demonstrate than a full observability stack.

### Alternatives Considered

#### Plain text logs

Rejected.

Harder to search, parse, and correlate.

#### OpenTelemetry

Rejected for V1.

Useful in production, but excessive for this challenge.

#### LangSmith-only tracing

Rejected as the only tracing mechanism.

It may be useful later, but the application should not depend on an external tracing platform to explain its behavior.

### Consequences

Positive:

* Easier debugging.
* Better technical defense.
* Better incident explanation.
* Supports assisted-operation mindset.

Negative:

* Requires discipline to include trace metadata consistently.

### Guardrail

Logs must not expose secrets or full sensitive customer data.

CPF should be masked in logs when possible.

---

## ADR-021 - Use Mocked Providers for Tests

**Status:** Accepted
**Date:** 2026-04-30
**Decision Type:** Testing / Reliability

### Context

The system depends on external services:

* Grok API
* OpenAI API
* Exchange rate API

Tests must not depend on live providers because external APIs introduce cost, latency, instability, and non-determinism.

### Decision

Use mocked providers for unit and integration tests.

Required test doubles:

```txt
MockLLMProvider
FailingLLMProvider
MockExchangeProvider
FailingExchangeProvider
```

The LLM fallback flow must be tested by simulating provider failures, not by calling real APIs.

### Rationale

Tests must be deterministic, fast, and safe to run repeatedly.

External provider behavior should be tested through controlled mocks.

### Alternatives Considered

#### Live API calls in test suite

Rejected.

Too slow, expensive, flaky, and unsafe.

#### Skip provider failure testing

Rejected.

Fallback behavior is a core architectural decision and must be tested.

#### Mock only at HTTP level

Rejected as the only approach.

Provider interfaces should be mockable directly to keep tests simpler and faster.

### Consequences

Positive:

* Fast tests.
* No token cost during tests.
* Reliable CI/local execution.
* Controlled fallback testing.

Negative:

* Does not fully verify real provider behavior.
* Requires separate manual smoke test for real credentials.

### Guardrail

Automated tests must not require real API keys.

---

## ADR-022 - Use SearchApi as Initial Exchange Provider in Phase 8

**Status:** Accepted (Provisional)
**Date:** 2026-05-01
**Decision Type:** External Integration / Exchange Provider

### Context

The challenge requires real-time exchange quotation through an external provider.
At the same time, graph nodes must remain provider-agnostic and tests must not
depend on real network calls.

### Decision

Use `SearchApiExchangeProvider` as the initial exchange provider implementation,
accessed only through an injected `ExchangeProvider` abstraction.

Keep `SerpApiExchangeProvider` available as an interchangeable adapter option.

### Guardrails

* `exchange_node` must continue using `deps.exchange_provider` only.
* Provider SDKs must not be called directly from graph nodes.
* Tests must use HTTP fakes/mocks and must not call real external APIs.
* `EXCHANGE_API_KEY` remains an environment placeholder; no real secrets in repo.

### Future Option

SerpApi remains an available alternative adapter.

Tavily remains a possible future provider option if later selected.

Real provider calls are allowed only in manual smoke tests or local demos.

---

## 3. Rejected Ideas Summary

The following ideas were intentionally rejected for V1:

| Idea                              | Reason Rejected                                                  |
| --------------------------------- | ---------------------------------------------------------------- |
| CrewAI as primary framework       | Less suitable for deterministic cyclic state workflows           |
| Full custom state machine only    | Misses target-role alignment with agent frameworks               |
| SQLite as primary storage         | Could appear to avoid CSV requirement                            |
| PostgreSQL                        | Overkill for challenge scope                                     |
| RAG                               | No real document corpus in V1                                    |
| MCP                               | No complex enterprise tool layer in V1                           |
| Full chat history in LLM context  | Higher cost, latency, and hallucination risk                     |
| Business logic in frontend        | Violates architecture boundary                                   |
| LLM-driven credit decisions       | Unsafe and non-deterministic                                     |
| Dedicated error recovery node     | Unnecessary graph complexity for V1                              |
| Async CSV write queue             | Overengineering for expected challenge concurrency               |
| Streamlit as main UI              | Lower-quality evaluator experience                               |
| LLM-only normalization            | Higher cost and non-deterministic parsing                        |
| Regex-only normalization          | Too rigid for natural user input                                 |
| Plain text logs only              | Poor traceability during debugging                               |
| OpenTelemetry in V1               | Excessive for challenge scope                                    |
| Live LLM calls in automated tests | Flaky, costly, and non-deterministic                             |
| Checksum-based CSV validation     | Unnecessary complexity for V1 after header/column/row validation |
| Unbounded income component in score formula | Challenge suggests `(renda / (despesas+1)) * 30` without a cap. With this formula any income above ~R$17/month with zero expenses already produces 510+ points from income alone, making employment type, dependents, and debt status effectively irrelevant. The formula was refined to a capped hybrid: `income_capacity = min(available/10000, 1)*300` + `income_efficiency = min(ratio, 20)/20*200`. This separates absolute financial capacity from relative efficiency, prevents a moderate income with very low expenses from outscoring a profile with much higher disposable income, and preserves the discriminating power of all components. The challenge explicitly marks the formula as a suggestion. |
| Single-component income score (`min(ratio,20)*25`) | After initial refinement, analysis showed that a household with R$4k income and R$240 expenses (ratio≈16.6, score≈779) could outscore one with R$50k income and R$4k expenses (ratio≈12.5, old score≈772) despite the latter having 12× higher disposable income. The hybrid formula correctly ranks the high-income profile higher (score≈885 vs 779) while still rewarding efficient financial management. |

---

## 4. Decision Review Triggers

An ADR must be reviewed if any of the following happens:

1. The challenge evaluator explicitly requires Streamlit.
2. CSV persistence becomes insufficient for demo reliability.
3. The backend must support real concurrent users.
4. The project gains a real policy/document corpus.
5. The project integrates with real enterprise systems.
6. The project requires durable session state across deployments.
7. LLM provider cost or latency becomes unacceptable.
8. LangGraph introduces unnecessary implementation complexity.
9. Security requirements become stricter than current challenge scope.
10. Frontend starts requiring logic beyond chat rendering.
11. Input normalization starts requiring complex natural language interpretation.
12. Manual trace IDs become insufficient for debugging.
13. Automated tests start depending on real external providers.
14. CSV validation failures occur during normal usage.

---

## 5. Implementation Guardrails

During implementation:

1. No code should violate an accepted ADR.
2. If code contradicts an ADR, either the code is wrong or the ADR must be updated first.
3. Any new framework or dependency must be justified here.
4. Any new endpoint must be justified here.
5. Any movement of business logic into agents, graph nodes, frontend, or LLM prompts is an architectural regression.
6. Any direct CSV access outside repositories is an architectural regression.
7. Any secret hardcoded in source code is a security violation.
8. Any raw LLM output used without validation is a correctness violation.
9. Any automated test that requires real API credentials is a testing regression.
10. Any unmasked sensitive customer data in logs is an observability/security regression.
11. Any ambiguous user input silently converted into a financial value is a correctness regression.
12. Any CSV replacement without prior `.tmp` validation is a persistence safety regression.

---

## 6. Current Decision Baseline

The current architecture baseline is:

```txt
FastAPI backend
LangGraph orchestration
Deterministic services
CSV repositories with locks and atomic writes
Temporary file validation before CSV replacement
Hierarchical input normalization
Grok primary LLM provider
OpenAI fallback provider
Mocked providers for automated tests
Structured JSON logs with trace_id propagation
React + TypeScript + Tailwind frontend
MemorySaver runtime checkpointing
In-memory API SessionService for V1
Dependency lifecycle cache for API graph/bootstrap wiring
Controlled error envelopes for bootstrap/provider unavailability
StateGuard transition safety
No RAG in V1
No MCP in V1
```

### V1 API Hardening Notes

* Session state in API layer is intentionally in-memory for V1 and is lost on process restart.
* API graph dependency resolution uses process-local cache and can be explicitly cleared in tests.
* Graph/bootstrap unavailability must be exposed as controlled API error envelopes, never raw runtime messages.
* Public API responses must not expose `GraphState` internals, including customer objects or authenticated CPF.

This baseline is now the source of truth for Wave 1 implementation planning.
