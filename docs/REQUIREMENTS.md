# Banco Ágil - Requirements Specification

**Version:** 1.0
**Reference Document:** PROJECT.md
**Status:** Finalized for V1 Implementation
**Purpose:** Define the functional, non-functional, business, data, observability, security, and acceptance requirements for the Banco Ágil Intelligent Banking Agent system.

---

## 1. Document Purpose

This document defines the contractual requirements for the Banco Ágil system.

It exists to prevent implementation drift and uncontrolled AI-generated behavior. Every implementation decision must be traceable to a requirement, business rule, or architectural decision described here or in the related architecture documents.

This document must guide:

* Test planning.
* Domain modeling.
* LangGraph state design.
* FastAPI endpoint design.
* Frontend behavior.
* README documentation.
* Technical defense during evaluation.

---

## 2. Requirement Language

The following terms are used with strict meaning:

* **MUST:** mandatory requirement.
* **MUST NOT:** forbidden behavior.
* **SHOULD:** recommended behavior, unless technically justified otherwise.
* **MAY:** optional enhancement.

---

## 3. System Overview

Banco Ágil is a fictional digital bank that provides customer support through specialized AI agents.

The user interacts with a single conversational interface. Internally, the system routes the conversation through specialized agents:

1. Triage Agent
2. Credit Agent
3. Credit Interview Agent
4. Exchange Agent

The system must authenticate the customer before allowing access to protected flows. Business decisions must be deterministic and implemented through backend services, not delegated to the LLM.

---

## 4. Functional Requirements

## 4.1 Triage and Authentication Requirements

### FR-AUTH-001 - Initial Greeting

The system MUST start the conversation with a clear and respectful greeting.

Acceptance criteria:

* Given a new session
* When the user opens or starts the chat
* Then the system must greet the user
* And ask for the CPF or guide the user toward authentication

---

### FR-AUTH-002 - CPF Collection

The system MUST collect the customer's CPF before any protected operation.

Acceptance criteria:

* Given an unauthenticated session
* When the user asks for credit, interview, or exchange operations
* Then the system must request CPF first
* And must not execute the requested protected operation

---

### FR-AUTH-003 - Birth Date Collection

The system MUST collect the customer's date of birth after receiving CPF.

Acceptance criteria:

* Given the user has informed a CPF
* When the CPF is syntactically acceptable
* Then the system must ask for the birth date

Date input rules:

* The triage flow MUST accept only `DD-MM-YYYY` as input format for birth date.
* The backend MUST normalize `DD-MM-YYYY` to internal `YYYY-MM-DD` before authentication lookup.
* Unsupported formats MUST be rejected with a safe retry prompt.

---

### FR-AUTH-003A - CPF Input Handling Scope

The triage flow MUST treat CPF as a string identifier for lookup in `clientes.csv`.

Acceptance criteria:

* The system MUST accept numeric CPF strings (11 digits) for authentication lookup.
* The system MUST NOT perform real CPF check-digit validation in V1.
* The system MAY remove punctuation and spaces before persisting `cpf_candidate` in runtime state.

---

### FR-AUTH-004 - Customer Authentication Against CSV

The system MUST authenticate the customer by matching CPF and birth date against `clientes.csv`.

Acceptance criteria:

* Given a CPF and birth date
* When both match a record in `clientes.csv`
* Then the system must mark the session as authenticated
* And store the authenticated CPF in session state
* And reset `auth_attempts` to 0 after successful authentication

---

### FR-AUTH-005 - Authentication Failure Handling

The system MUST reject invalid CPF and birth date combinations.

Acceptance criteria:

* Given a CPF and birth date
* When no matching customer exists in `clientes.csv`
* Then the system must increment the failed attempt counter
* And inform the user that authentication failed
* And allow another attempt if the counter is below 3

---

### FR-AUTH-006 - Maximum Authentication Attempts

The system MUST allow at most three failed authentication attempts per session.

Acceptance criteria:

* Given an unauthenticated session
* When the user fails authentication three consecutive times
* Then the system must block the session
* And end the conversation
* And must not allow protected operations in that session

---

### FR-AUTH-007 - Post-Authentication Intent Identification

After successful authentication, the system MUST identify the user's intended topic.

Supported intents:

* Credit limit consultation
* Credit increase request
* Credit interview continuation when applicable
* Currency exchange quotation
* End conversation
* Unknown / clarification needed

Acceptance criteria:

* Given an authenticated session
* When the user describes a need
* Then the system must classify the intent
* And route to the correct agent or ask a clarification question

Turn contract constraints:

* States waiting for user credentials (`ASKING_CPF`, `ASKING_BIRTH_DATE`) MUST finish the current graph invoke.
* A credential-only successful authentication turn MUST finish without executing intent classification in the same invoke.
* Intent classification MUST run only after a subsequent user message.

---

### FR-AUTH-008 - Triage LLM Boundary

The triage flow MUST be deterministic and MUST NOT depend on LLM calls.

Acceptance criteria:

* CPF and birth date handling MUST use deterministic services.
* Authentication success/failure MUST come from `AuthService` + repository lookup.
* No external provider call may be required to complete triage steps.

---

### FR-AUTH-009 - Unknown CPF Handling Before Birth Date

When CPF is not found in `clientes.csv`, the system MUST inform this before asking birth date.

Acceptance criteria:

* Given a CPF that does not exist in the customer base
* When the user submits CPF
* Then the system must inform that CPF was not found
* And guide the user to review the number or indicate they are not yet a customer
* And keep the flow waiting for CPF re-entry (without exposing technical errors)

---

## 4.2 Credit Agent Requirements

### FR-CREDIT-001 - Credit Limit Consultation

The system MUST allow authenticated customers to consult their current credit limit.

Acceptance criteria:

* Given an authenticated customer
* When the user asks for current credit limit
* Then the system must read `limite_credito` from `clientes.csv`
* And present the value clearly to the user

---

### FR-CREDIT-002 - Credit Limit Request Start

The system MUST allow authenticated customers to request a credit limit increase.

Acceptance criteria:

* Given an authenticated customer
* When the user asks to increase credit limit
* Then the system must ask for the desired new limit

---

### FR-CREDIT-003 - Desired Limit Validation

The system MUST validate the requested new credit limit before processing.

Acceptance criteria:

* Given the user informs a desired limit
* When the value is non-normalizable, negative, zero, ambiguous, or greater than 1,000,000 after normalization
* Then the system must reject the input
* And ask the user to provide a valid amount

---

### FR-CREDIT-004 - Credit Request Registration

The system MUST register every valid credit increase request in `solicitacoes_aumento_limite.csv`.

Required columns:

* `cpf_cliente`
* `data_hora_solicitacao`
* `limite_atual`
* `novo_limite_solicitado`
* `status_pedido`

Acceptance criteria:

* Given a valid credit increase request
* When the request is evaluated
* Then the system must append a row to `solicitacoes_aumento_limite.csv`
* And use ISO 8601 timestamp format
* And persist final status as `aprovado` or `rejeitado`

---

### FR-CREDIT-005 - Credit Approval Based on Score Table

The system MUST approve or reject credit increase requests based on `score_limite.csv`.

Acceptance criteria:

* Given an authenticated customer with a current score

* And a requested new limit

* When the requested limit is less than or equal to the maximum allowed limit for the customer's score range

* Then the request must be approved

* Given the requested limit is above the maximum allowed limit

* Then the request must be rejected

---

### FR-CREDIT-006 - Rejection Interview Offer

If a credit increase request is rejected, the system MUST offer the customer the option to complete a credit interview.

Acceptance criteria:

* Given a rejected credit increase request
* When the system informs the rejection
* Then it must explain that the customer may update their score through a credit interview
* And ask whether the customer wants to proceed

---

### FR-CREDIT-007 - Declining Credit Interview

If the customer declines the credit interview, the system MUST return to intent identification or offer to end the conversation.

Acceptance criteria:

* Given a rejected request
* When the user declines the interview
* Then the system must not start the interview
* And must offer another supported operation or closure

---

### FR-CREDIT-008 - Post-Interview Reassessment

After the interview updates the score, the system MUST allow the customer to explicitly re-evaluate the same rejected increase request in the next turn.

Acceptance criteria:

* Given a rejected request that triggered an interview
* And the interview has updated the customer score
* When the user confirms reassessment in the next turn
* Then the system must re-evaluate the same requested limit using the updated score
* And register the new evaluated result in `solicitacoes_aumento_limite.csv`
* And if the request is still rejected, keep the current `limite_credito` unchanged

---

## 4.3 Credit Interview Agent Requirements

### FR-INTERVIEW-001 - Structured Interview Start

The system MUST start a structured credit interview only for authenticated customers.

Acceptance criteria:

* Given an unauthenticated session

* When the user asks for a credit interview

* Then the system must route to authentication first

* Given an authenticated session

* When the user accepts the interview

* Then the system must start collecting financial information

---

### FR-INTERVIEW-002 - Monthly Income Collection

The system MUST collect monthly income.

Acceptance criteria:

* Given the interview has started
* When asking for monthly income
* Then the system must accept numeric or normalizable monetary values from 0 to 1,000,000
* And reject invalid values with a clear retry prompt

---

### FR-INTERVIEW-003 - Employment Type Collection

The system MUST collect employment type.

Supported values:

* `formal`
* `autonomo`
* `desempregado`

Acceptance criteria:

* Given the system asks for employment type

* When the user provides a valid equivalent term

* Then the system must normalize it to one of the supported values

* When the value is unknown

* Then the system must ask the user to choose a valid option

---

### FR-INTERVIEW-004 - Fixed Expenses Collection

The system MUST collect fixed monthly expenses.

Acceptance criteria:

* Given the system asks for expenses

* When the user provides a numeric or normalizable monetary value from 0 to 1,000,000

* Then the system must store the value in interview state

* When the user provides an invalid, ambiguous, or non-normalizable value

* Then the system must reject it and ask again

---

### FR-INTERVIEW-005 - Dependents Collection

The system MUST collect the number of dependents.

Acceptance criteria:

* Given the system asks for dependents

* When the user provides a non-negative integer

* Then the system must store the value

* And the system MAY accept common natural-language equivalents such as `nenhum` when they can be normalized safely

* When the user provides a negative, decimal, or non-numeric value

* Then the system must reject it and ask again

---

### FR-INTERVIEW-006 - Active Debts Collection

The system MUST collect whether the customer has active debts.

Acceptance criteria:

* Given the system asks about active debts

* When the user answers yes/no or equivalent

* Then the system must normalize the answer to a boolean value

* When the answer is ambiguous

* Then the system must ask a clarification question

---

### FR-INTERVIEW-007 - Score Recalculation

The system MUST calculate a new credit score after collecting all interview fields.

Acceptance criteria:

* Given all interview fields are valid
* When the interview is completed
* Then the system must calculate the new score using the deterministic score formula
* And clip the result between 0 and 1000
* And round the result to an integer

---

### FR-INTERVIEW-008 - Customer Score Update

The system MUST update the customer's score in `clientes.csv` after the interview.

Acceptance criteria:

* Given the new score was calculated
* When the update is executed
* Then `clientes.csv` must reflect the new score for the authenticated CPF
* And the original CSV header must be preserved

---

### FR-INTERVIEW-009 - Return to Credit Flow

After updating the score, the system MUST return the user to the credit journey with a clear next step for new analysis.

Acceptance criteria:

* Given the score has been updated
* When the interview finishes
* Then the system must return a clear completion message
* And allow a reassessment confirmation for the same rejected request in the next turn
* And accept contextual confirmation phrases only after safe normalization and validation

---

## 4.4 Exchange Agent Requirements

### FR-EXCHANGE-001 - Exchange Quote Request

The system MUST allow authenticated customers to request currency quotation.

Acceptance criteria:

* Given an authenticated customer
* When the user asks for a currency quote
* Then the system must identify the requested currency or default to USD when not specified

---

### FR-EXCHANGE-002 - External API Integration

The system MUST fetch currency quotation using an external API.

Acceptance criteria:

* Given a valid currency request
* When the external API responds successfully
* Then the system must present the current quote to the user
* And include the currency pair or target currency when available

Configuration note:

* External exchange integration must use an environment-based key such as `EXCHANGE_API_KEY`.
* SearchApi and SerpApi are distinct provider options and must stay behind an injected `ExchangeProvider` abstraction.
* SearchApi is the initial provider choice for bootstrap and smoke validation in current phase.

---

### FR-EXCHANGE-003 - Exchange API Failure Handling

The system MUST handle exchange API failures gracefully.

Acceptance criteria:

* Given the external API is unavailable, times out, or returns invalid data
* When the user requests a quote
* Then the system must not crash
* And must inform the user that the quotation is temporarily unavailable
* And may offer another operation or return to intent identification
* And must never fabricate or guess an exchange rate value

Failure classification:

* External exchange provider failure must be treated as a recoverable error path.

---

## 4.5 Conversation Control Requirements

### FR-CONV-001 - End Conversation From Any State

The system MUST allow the user to end the conversation at any time.

Acceptance criteria:

* Given any conversation state
* When the user asks to end the conversation
* Then the system must transition to `ENDING`
* And then to `ENDED`
* And clear temporary domain-specific state

---

### FR-CONV-002 - Invisible Agent Handoff

The system MUST keep agent transitions invisible to the customer.

Acceptance criteria:

* Given the system routes from one internal agent to another
* When responding to the user
* Then the response must not expose internal implementation details such as node names, graph transitions, or agent handoff mechanics

---

### FR-CONV-003 - Natural Language Bridging

The system MUST use contextual transition messages when moving between different agent domains.

Acceptance criteria:

* Given a credit request was rejected
* When the user accepts the credit interview
* Then the system must explain the transition naturally before asking financial questions

Example:

```txt
Entendi. Para tentar melhorar sua análise de crédito, vou fazer algumas perguntas rápidas sobre sua situação financeira atual.
```

* The system MUST NOT abruptly switch topics without context
* The system MUST NOT mention internal agents, nodes, graphs, or handoff mechanics

---

### FR-CONV-004 - Unknown Intent Handling

The system MUST handle unknown or ambiguous user intent with clarification.

Acceptance criteria:

* Given an authenticated customer
* When the user's message does not match a supported intent
* Then the system must ask a concise clarification question
* And must not invent unsupported capabilities

---

### FR-CONV-005 - Domain State Cleanup

The system MUST clear temporary domain-specific fields when transitioning between unrelated domains.

Examples:

* When leaving credit interview, temporary interview fields must be cleared after score update
* When leaving exchange flow, temporary quote request fields must be cleared
* When ending the conversation, temporary state must be cleared

The system MUST preserve only session-level fields required for authentication, tracing, and conversation control.

---

## 4.6 Registration Agent Requirements

### FR-REGISTRATION-001 - New Customer Identification

When a CPF is not found in `clientes.csv`, the system MUST inform the user and offer the option to register as a new customer.

Acceptance criteria:

* Given a CPF that does not exist in the customer base
* When the user indicates they want to register
* Then the system must transition to `REGISTRATION_ASKING_NAME`
* And must not proceed to authentication with a non-existent CPF

---

### FR-REGISTRATION-002 - Name Collection

The system MUST collect the customer's full name as the first registration step.

Acceptance criteria:

* Given the registration flow has started
* When the system asks for name
* Then the user must provide a non-empty string
* And the system must store the value in `registration_data`

---

### FR-REGISTRATION-003 - CPF Collection in Registration

The system MUST collect the CPF during registration and validate it for format (11 digits).

Acceptance criteria:

* Given the system is collecting registration data
* When the user provides a CPF
* Then the system must accept 11-digit numeric strings
* And reject values that cannot be normalized to 11 digits

---

### FR-REGISTRATION-004 - Birth Date Collection in Registration

The system MUST collect the birth date during registration in `DD-MM-YYYY` format.

Acceptance criteria:

* Given the system is collecting registration data
* When the user provides a birth date
* Then the system must accept only `DD-MM-YYYY` format
* And normalize it to `YYYY-MM-DD` before persisting

---

### FR-REGISTRATION-005 - Account Creation

After collecting all required fields, the system MUST create a new customer record in `clientes.csv`.

Acceptance criteria:

* Given name, CPF, and birth date have been collected and validated
* When registration is completed
* Then the system must append a new row to `clientes.csv` with default `score_atual` and `limite_credito`
* And the new CPF must be unique — existing records must not be overwritten
* And the system must authenticate the session automatically after successful creation
* And the atomic CSV write strategy MUST be used

---

### FR-REGISTRATION-006 - Registration State Cleanup

After registration completes, the system MUST clear `registration_data` from session state.

---

## 5. Non-Functional Requirements

### NFR-ARCH-001 - Backend Architecture

The backend MUST use FastAPI and maintain clear separation between API, graph orchestration, agents, services, repositories, schemas, and observability.

---

### NFR-ARCH-002 - Agent Orchestration

The system MUST use LangGraph to orchestrate the agent workflow and conversation state transitions.

---

### NFR-ARCH-003 - Deterministic Business Logic

Business rules MUST be implemented in deterministic services and MUST NOT depend on LLM output.

Applies to:

* Authentication
* Credit score calculation
* Credit approval/rejection
* CSV persistence
* Session blocking

---

### NFR-ARCH-004 - Frontend Architecture

The frontend MUST be a React + TypeScript + Tailwind SPA or equivalent deployable web application.

The frontend MUST NOT contain banking business logic.

---

### NFR-SEC-001 - Authentication Gate

Protected operations MUST be blocked unless the session is authenticated.

Protected operations:

* Credit limit consultation
* Credit increase request
* Credit interview
* Exchange quote request

---

### NFR-SEC-002 - State Guard

The system MUST validate node entry against the current `GraphState` for all protected nodes.

In V1, `StateGuard.check_entry` is wired for `credit_node`, `credit_interview_node`, and `exchange_node`. Entry violations MUST be rejected, logged, and redirected to a safe state.

Note: transition-level validation (`check_transition`) exists in the codebase but is not wired into the V1 runtime. It is deferred to a future release.

---

### NFR-SEC-003 - Secret Management

API keys and credentials MUST be loaded from environment variables.

Secrets MUST NOT be committed to the repository or exposed to the frontend.

### NFR-SEC-004 - Session TTL

Authenticated sessions SHOULD have a configurable time-to-live.

Default:

```txt
SESSION_TTL_MINUTES=30
```

Rules:

* Expired sessions must be treated as unauthenticated or ended
* Sensitive temporary state must be cleared after expiration
* The frontend may request a session reset after inactivity
* Backend session expiration is authoritative; frontend behavior is only a convenience layer

---

### NFR-LLM-001 - Dual LLM Provider Strategy

The system MUST support Grok as the primary LLM provider and OpenAI as fallback.

Required configuration:

* `XAI_URL`
* `OPENAI_URL`
* `PRIMARY_MODEL`
* `FALLBACK_MODEL`
* `XAI_API_KEY`
* `OPENAI_API_KEY`

Canonical naming rule:

* `XAI_API_KEY` is the canonical variable name for xAI/Grok.
* `GROK_API_KEY` must not be used as the canonical project variable.

---

### NFR-LLM-002 - LLM Provider Fallback

If the primary LLM provider fails, the system MUST attempt the fallback provider.

Fallback triggers:

* Timeout
* Rate limit
* Invalid response
* Provider error
* Network failure

---

### NFR-LLM-003 - LLM Output Validation

All structured LLM outputs MUST be validated with Pydantic before being used.

Invalid outputs MUST be rejected and handled through fallback or clarification.

---

### NFR-LLM-004 - Deterministic Intent Fallback

If both LLM providers fail, the system SHOULD use a deterministic keyword-based classifier for basic intents.

If intent remains ambiguous, the system MUST ask a clarification question.

---

### NFR-LLM-005 - Fallback Context Consistency

When fallback from Grok to OpenAI occurs, the fallback provider MUST receive the same normalized conversation context and system constraints required to complete the current task safely.

Rules:

* The system MUST NOT forward raw unlimited chat history blindly
* The system SHOULD send a compact structured context derived from `GraphState`
* The context MUST include current state, authenticated status, active intent, and the current user message
* Sensitive values must be minimized whenever possible
* Business decisions must remain owned by deterministic services

---

### NFR-DATA-001 - CSV Persistence

CSV files MUST remain the official persistence layer for the challenge.

Required files:

* `clientes.csv`
* `score_limite.csv`
* `solicitacoes_aumento_limite.csv`

---

### NFR-DATA-002 - File Locking

CSV writes MUST use file locking to reduce risk of corruption during concurrent writes.

---

### NFR-DATA-003 - Seed Data Reset

The project MUST provide a `seed_data.py` script to reset CSV files to a known initial state.

---

### NFR-DATA-004 - Atomic CSV Writes

CSV update operations MUST use atomic write strategy when modifying existing files.

Required behavior:

1. Acquire file lock
2. Write updated content to a temporary `.tmp` file
3. Validate that the temporary file contains expected headers
4. Replace the original file using an atomic replace operation
5. Release file lock

Append-only operations may append directly under lock, but full-file updates, such as customer score updates, MUST use the temporary file strategy.

Rationale:

File locks reduce concurrent write corruption, but atomic replacement reduces the risk of partially written CSV files if the process fails during update.

---

### NFR-OBS-001 - Structured Logs

The system MUST emit structured logs for graph transitions, errors, LLM provider usage, and business decisions.

Required log fields when applicable:

* `trace_id`
* `session_id`
* `event`
* `agent`
* `from_state`
* `to_state`
* `intent`
* `provider`
* `fallback_triggered`
* `latency_ms`
* `input_tokens`
* `output_tokens`
* `decision_rationale`

---

### NFR-OBS-002 - Decision Rationale

Credit decisions and score recalculations MUST include internal decision rationale in logs.

The rationale MUST NOT expose sensitive implementation details to the end user.

---

### NFR-TEST-001 - Testability

Core deterministic services MUST be unit tested before API, LangGraph, LLM, or frontend integration.

---

### NFR-DEPLOY-001 - Public Demo

The system SHOULD provide a public frontend URL for evaluator testing.

The README MUST also include local execution instructions.

---

## 6. Business Rules

## 6.1 Authentication Rules

### BR-AUTH-001

CPF and birth date must match the same customer record in `clientes.csv`.

### BR-AUTH-002

Three consecutive authentication failures block and end the session.

### BR-AUTH-003

Blocked sessions cannot execute protected operations.

### BR-AUTH-004

A new session may be created after a blocked session, but the blocked session itself must remain ended.

---

## 6.2 Credit Rules

### BR-CREDIT-001

Credit limit must be read from the authenticated customer record in `clientes.csv`.

### BR-CREDIT-002

Requested credit limit must be greater than zero and less than or equal to 1,000,000.

### BR-CREDIT-003

Credit approval must be based on the customer's score and the score range defined in `score_limite.csv`.

### BR-CREDIT-004

A request is approved when:

```txt
novo_limite_solicitado <= limite_maximo_permitido_para_score
```

### BR-CREDIT-005

A request is rejected when:

```txt
novo_limite_solicitado > limite_maximo_permitido_para_score
```

### BR-CREDIT-006

Every valid request must be persisted with final status `aprovado` or `rejeitado`.

---

## 6.3 Credit Score Rules

### BR-SCORE-001

The score must be calculated using this formula:

```txt
income_score     = min(renda_mensal / (despesas_fixas_mensais + 1), 20.0) * 25.0
raw_score        = income_score + peso_emprego + peso_dependentes + peso_dividas
score            = max(0, min(1000, round(raw_score)))
```

The income component is capped at `20.0 * 25.0 = 500` to prevent a very high
income ratio from dominating the score. Division-by-zero is prevented by using
`despesas_fixas_mensais + 1` as the denominator.

### BR-SCORE-002

Employment weights:

| Employment Type | Weight |
| --------------- | -----: |
| formal          |    300 |
| autonomo        |    200 |
| desempregado    |      0 |

### BR-SCORE-003

Dependent weights:

| Dependents | Weight |
| ---------- | -----: |
| 0          |    100 |
| 1          |     80 |
| 2          |     60 |
| 3 or more  |     30 |

### BR-SCORE-004

Debt weights:

| Has Active Debts | Weight |
| ---------------- | -----: |
| true             |   -100 |
| false            |    100 |

### BR-SCORE-005

Final score must be rounded to an integer and clipped between 0 and 1000.

### BR-SCORE-006

Invalid score inputs:

* Negative income
* Negative expenses
* Negative dependents
* Non-normalizable income
* Non-normalizable expenses
* Non-integer dependents
* Unknown employment type
* Income greater than 1,000,000
* Expenses greater than 1,000,000

The system MAY normalize common financial formats before validation.

Examples:

```txt
"R$ 5.000" -> 5000
"5000 reais" -> 5000
"10k" -> 10000
"10 mil" -> 10000
```

Rules:

* Normalization must happen before service-level validation
* Normalized values must still pass numeric range validation
* Ambiguous values must be rejected with a clarification prompt
* The system must not silently guess uncertain values

---

## 6.4 Exchange Rules

### BR-EXCHANGE-001

USD must be supported as the default quote currency.

### BR-EXCHANGE-002

The system must not fabricate exchange rates.

### BR-EXCHANGE-003

If the external provider fails, the system must provide a failure message and avoid presenting stale or invented values.

---

## 6.5 LLM Rules

### BR-LLM-001

The LLM may classify intent, normalize simple natural language, and generate user-facing text.

### BR-LLM-002

The LLM must not authenticate customers, approve credit, calculate score, write CSV files, or override service decisions.

### BR-LLM-003

The system must never trust raw LLM output without validation.

---

## 6.6 Value Normalization Rules

### BR-NORM-001

The system MAY normalize common user-entered values before validation.

Allowed examples:

```txt
"R$ 3.500,00" -> 3500.00
"3500 reais" -> 3500.00
"10k" -> 10000.00
"sem dívidas" -> false
"tenho dívidas" -> true
```

### BR-NORM-002

Normalization must be deterministic where possible.

The LLM may assist in interpreting natural language values only if the output is validated against a constrained allowed-value set before business use.

The LLM must not calculate score, approve credit, or write CSV data.

### BR-NORM-003

The system MUST reject ambiguous inputs.

Examples:

```txt
"bastante"
"mais ou menos"
"depende"
"alto"
"baixo"
```

### BR-NORM-004

The system MUST ask a clarification question when normalization fails.

### BR-NORM-005

Raw user input may exist only in conversational fields such as `last_user_input` and `recent_messages`.

Domain-specific state must store only normalized and validated values.

Applies to:

* `credit_request`
* `interview_data`
* `exchange_request`

Business services must receive typed normalized values, not raw user text.

---

## 7. Data Requirements

## 7.1 `clientes.csv`

Required columns:

```txt
cpf,data_nascimento,nome,score_atual,limite_credito
```

Rules:

* `cpf` must be stored as string.
* `data_nascimento` must be stored in ISO format: `YYYY-MM-DD`.
* User input must be accepted only as `DD-MM-YYYY`, then normalized to `YYYY-MM-DD` for authentication lookup.

---

### V2 Backlog - New Customer Onboarding Flow (Out of Scope for V1)

The system does not implement account creation yet. This backlog item is intentionally mapped for the next phase.

Required V2 rules:

* Account creation must append new records to existing CSV files without deleting prior rows.
* CPF must be unique: only one active account per CPF.
* Existing customer rows must never be overwritten during new-account creation.
* Creation flow must validate mandatory fields and fail safely on duplicates.
* Writes must preserve CSV header and append order guarantees.
* `score_atual` must be an integer between 0 and 1000.
* `limite_credito` must be a non-negative float.
* The file must preserve headers after updates.
* Customer score updates MUST use atomic CSV write strategy.
* The system MUST NOT update CPF, name, birth date, or credit limit during the credit interview flow.

---

## 7.2 `score_limite.csv`

Required columns:

```txt
score_minimo,score_maximo,limite_maximo_permitido
```

Rules:

* Score ranges must not overlap.
* Score ranges should cover 0 through 1000.
* `limite_maximo_permitido` must be non-negative.
* This file is read-only during normal application flow.

---

## 7.3 `solicitacoes_aumento_limite.csv`

Required columns:

```txt
cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido
```

Rules:

* Writes must be append-only in V1.
* Timestamp must use ISO 8601.
* Status must be `aprovado` or `rejeitado` after evaluation.
* File headers must be preserved.

---

## 8. Agent Traceability Matrix

| Agent | Trigger | Main Responsibility | Allowed Next States |
| --- | --- | --- | --- |
| Triage Agent | New or unauthenticated session | Authenticate customer | `ASKING_CPF`, `ASKING_BIRTH_DATE`, `AUTHENTICATED`, `REGISTRATION_ASKING_NAME`, `ENDED` |
| Registration Agent | CPF not found; user opts for new account | Collect customer data and create account | `REGISTRATION_ASKING_NAME`, `REGISTRATION_ASKING_CPF`, `REGISTRATION_ASKING_BIRTH_DATE`, `AUTHENTICATED`, `ENDED` |
| Intent Node | Authenticated message | Classify intent and route to domain agent | `IDENTIFYING_INTENT`, `SHOWING_CREDIT_LIMIT`, `ASKING_NEW_LIMIT`, `CREDIT_INTERVIEW_IN_PROGRESS`, `EXCHANGE_ASKING_CURRENCY`, `ENDING` |
| Credit Agent | Credit intent | Consult limit and process increase request | `SHOWING_CREDIT_LIMIT`, `ASKING_NEW_LIMIT`, `PROCESSING_CREDIT_REQUEST`, `CREDIT_REQUEST_APPROVED`, `CREDIT_REQUEST_REJECTED`, `OFFERING_CREDIT_INTERVIEW`, `OFFERING_PARTIAL_INCREASE`, `IDENTIFYING_INTENT` |
| Credit Interview Agent | Rejected credit request and user acceptance | Collect financial data and update score | `CREDIT_INTERVIEW_IN_PROGRESS`, `RECALCULATING_SCORE`, `IDENTIFYING_INTENT` |
| Exchange Agent | Exchange intent | Fetch and present currency quotation | `EXCHANGE_ASKING_CURRENCY`, `EXCHANGE_FETCHING_QUOTE`, `EXCHANGE_SHOWING_QUOTE`, `IDENTIFYING_INTENT` |
| End Node | End intent or blocked session | Close conversation | `ENDING`, `ENDED` |

---

## 9. Anti-Hallucination Requirements

### AH-001

The system MUST reduce hallucination risk through architecture, not only prompting.

### AH-002

The system MUST use deterministic services for all financial and identity decisions.

### AH-003

The system MUST validate structured outputs before state mutation.

### AH-004

The system MUST ask clarification when intent or input is ambiguous.

### AH-005

The system MUST NOT invent:

* Customer data
* Credit limits
* Credit approval criteria
* Exchange rates
* CSV records
* Successful tool calls

---

## 10. RAG and MCP Requirements

## 10.1 RAG Requirement Position

RAG MUST NOT be implemented in V1 unless a real document corpus is added.

RAG MAY be introduced in a future version for:

* Credit policies
* Product manuals
* Compliance documents
* Internal FAQs
* Operational playbooks

If implemented in the future:

* Retrieved context must be source-traceable.
* LLM answers must be grounded in retrieved context.
* Deterministic business rules must still override retrieved content.

---

## 10.2 MCP Requirement Position

MCP MUST NOT be implemented in V1 because current integrations are simple and explicitly controlled through backend services.

MCP MAY be introduced in a future enterprise version for controlled access to:

* CRM
* ERP
* Ticketing platforms
* Internal banking APIs
* Document repositories
* Observability systems

If implemented in the future:

* MCP tools must be permission-scoped.
* Tool outputs must be validated.
* Sensitive tools must require authenticated session state.
* Tool calls must be logged with trace IDs.

---

## 11. UI Requirements

### UI-001

The frontend MUST provide a single chat-based interface.

### UI-002

The frontend MUST display user and assistant messages clearly.

### UI-003

The frontend MUST show loading state while waiting for backend response.

### UI-004

The frontend MUST allow the user to reset the session.

### UI-004.1

The frontend SHOULD reset or expire the local session after a configurable inactivity period.

Default:

```txt
CLIENT_SESSION_IDLE_TIMEOUT_MINUTES=30
```

Rules:

* The frontend may call `POST /api/v1/sessions/reset` after inactivity
* The backend remains authoritative for session validity
* Closing the browser tab is not guaranteed to trigger backend cleanup and must not be relied upon as a security mechanism

### UI-005

The frontend MUST display friendly error messages when the backend fails.

### UI-006

The frontend MUST NOT expose API keys, provider configuration, or internal state transitions.

---

## 12. API Requirements

### API-001

The backend MUST expose:

```txt
GET /api/v1/health
POST /api/v1/chat
POST /api/v1/sessions/reset
GET /api/v1/sessions/{session_id}
```

### API-002

`POST /api/v1/chat` MUST accept:

```json
{
  "session_id": "optional-string",
  "message": "string"
}
```

### API-003

`POST /api/v1/chat` MUST return:

```json
{
  "session_id": "string",
  "reply": "string",
  "agent": "string",
  "state": "string",
  "ended": false,
  "trace_id": "string",
  "metadata": {
    "recoverable": true,
    "retry_available": false,
    "suggested_action": "continue"
  }
}
```

Rules:

* `metadata` may be `null` when no frontend guidance is needed.
* If present, `metadata` must follow `API_CONTRACT.md`.

---

## 13. Requirement Traceability to Tests

| Requirement Group | Minimum Test Coverage |
| --- | --- |
| Authentication | Unit + integration |
| Authentication attempt blocking | Unit + integration |
| Session TTL (V2) | Deferred — not implemented in V1 |
| Credit service | Unit + integration |
| Score service | Unit |
| CSV repositories | Unit |
| Atomic CSV writes | Unit |
| Domain state cleanup | Unit + integration |
| Natural language bridging | Integration or snapshot-style |
| LangGraph routing | Integration |
| LLM fallback | Unit with mocks |
| Exchange API failure | Unit + integration with mock |
| Frontend chat flow | Manual or component test |
| State Guard | Unit + integration |
| Seed reset | Unit or script verification |

---

## 14. Definition of Requirements Completion

This requirements document is considered satisfied when:

1. Every functional requirement has corresponding implementation.
2. Every critical business rule has automated tests.
3. Protected flows are impossible before authentication.
4. LLM outputs are validated before use.
5. CSV contracts are respected.
6. Credit decisions are deterministic.
7. Agent transitions are explicit in LangGraph.
8. Frontend contains no business logic.
9. README documents setup, architecture, tests, decisions, and limitations.
10. The system can be demonstrated through a public frontend or local execution.
