# Banco Ágil - State Machine Specification

**Version:** 1.0
**Status:** Execution-Ready
**Purpose:** Define deterministic conversational flow, LangGraph nodes, transitions, guards, and LLM interaction boundaries.

---

## 1. Objective

This document defines how the conversational system behaves at runtime.

It ensures:

* Deterministic flow control
* Explicit state transitions
* Controlled LLM usage
* Isolation between domains (credit, interview, exchange)
* Full traceability of decisions

Core principle:

```txt
The graph controls the flow.
The state controls the truth.
The services control the decisions.
The LLM only assists with language.
```

---

## 2. Graph State Definition

The `GraphState` is the single source of truth across the system.

State data rules:

* `last_user_input` and `recent_messages` may contain raw user text.
* Domain stores such as `credit_request`, `interview_data`, and `exchange_request` must contain normalized and validated data only.
* Raw user input must not be stored inside domain stores.
* Business services must receive typed values derived from normalized domain stores.

```python
class GraphState(TypedDict, total=False):

    # Identity
    session_id: str
    trace_id: str

    # Security
    authenticated: bool
    auth_attempts: int
    is_blocked: bool

    # Customer context
    cpf_candidate: str | None
    birth_date_candidate: str | None
    authenticated_cpf: str | None
    current_customer: dict | None

    # Flow control
    current_state: str
    previous_state: str | None
    next_step: str | None
    ended: bool

    # Intent
    intent: str | None
    unknown_intent_count: int

    # Conversation memory
    last_user_input: str
    last_assistant_output: str | None
    recent_messages: list[dict]  # max 3 turns
    last_action_summary: str | None
    system_bridge_message: str | None

    # Domain stores
    credit_request: dict | None
    request_rejected: bool | None
   offered_partial_limit: float | None
    interview_data: dict
    interview_step: str | None
    interview_complete: bool | None
    exchange_request: dict | None
   registration_data: dict

    # Credit domain
   interview_offer_response: InterviewOfferResponse | None  # accepted | declined | unknown | None

    # Recovery
    recoverable_error: bool
    retry_available: bool
    fatal_error: bool

    # Observability
    provider_used: str | None
    fallback_triggered: bool
    decision_rationale: str | None
    last_error: str | None
```

Error state rules:

* `last_error` must store a controlled error code or short safe diagnostic label.
* `last_error` must not store stack traces, raw provider responses, or secrets.
* API error mapping must follow `API_CONTRACT.md`.

---

## 2.1 Runtime State Persistence

The graph must persist runtime state between requests using a LangGraph checkpointer.

V1 strategy:

```txt
MemorySaver
```

Purpose:

* Preserve `GraphState` during the active runtime process
* Allow session continuity across multiple `POST /api/v1/chat` requests
* Support basic session recovery when the frontend refreshes the page

Limitations:

* MemorySaver is process-local
* State is lost on backend restart or redeploy
* This is acceptable for V1 and must be documented in README

Production evolution:

```txt
MemorySaver → Redis-backed checkpointing → durable database-backed checkpointing
```

Rules:

* `session_id` must identify the graph thread/session
* V1 does not enforce backend TTL expiration for in-memory sessions
* Backend remains authoritative for session validity

---

## 3. Graph Nodes

Nodes are deterministic orchestration units.

They:

* Read state
* Call services
* Update state
* Return next transition context

They do NOT:

* Own business logic
* Write CSV directly
* Decide flow via LLM

### Node Return Contracts

Every node must return a partial state update.

Conceptual contract:

```python
class NodeUpdate(TypedDict, total=False):
    current_state: str
    next_step: str | None
    last_assistant_output: str | None
    decision_rationale: str | None
    last_action_summary: str | None
    system_bridge_message: str | None
    recoverable_error: bool
    retry_available: bool
    fatal_error: bool
```

Rules:

1. Nodes must update only fields related to their domain.
2. Nodes must not overwrite unrelated state fields.
3. Nodes must not return raw LLM output directly to the graph.
4. Nodes must validate all structured outputs before updating state.
5. Nodes must set `decision_rationale` for relevant business or routing decisions.

---

## 3.1 Node: `start_node`

Responsibility:

* Initialize session state

Behavior:

* Set default values
* Redirect immediately to `triage_node`

---

## 3.2 Node: `triage_node`

Responsibility:

* Authenticate user
* Execute Triage Auth phase only

Flow:

1. Ask for CPF if missing
2. Ask for birth date if CPF exists
3. Normalize inputs
4. Call `AuthService`
5. Update:

   * authenticated
   * auth_attempts
   * is_blocked
   * ended when authentication failure limit is reached

Rules:

* If `auth_attempts >= 3`, set `is_blocked = True`, prepare session termination, and route to `ending_node`
* Cannot proceed to any domain before authentication
* Must not call LLM
* Birth date normalization should accept only `DD-MM-YYYY` as user input and convert internally to `YYYY-MM-DD`.

---

## 3.3 Node: `intent_node`

Responsibility:

* Identify user intent
* Execute Triage Routing phase after successful authentication

Flow:

1. Build structured context
2. Call LLM
3. Validate response
4. If invalid:

   * increment `unknown_intent_count`
5. If valid:

   * reset counter

Fallback:

* If LLM fails → deterministic classifier

Circuit Breaker:

```txt
if unknown_intent_count >= 3 → ending_node
```

Turn contract:

* A credential-only successful authentication turn must stop after `AUTHENTICATED` and wait for the next user message.
* Intent classification must not run in the same invoke that validates CPF + birth date.

Routing guard:

* `intent_node` is part of triage at product level (Triage Routing), but it must run only after authentication success.

---

## 3.4 Node: `credit_node`

Responsibility:

* Handle credit limit consultation and credit increase requests.

Flow:

1. If the user asks for current limit:
   * call `CreditService.get_current_limit`
   * return current limit
   * route back to `intent_node`

2. If the user requests a limit increase:
   * normalize requested amount
   * validate requested amount
   * call `CreditService.evaluate_limit_request`
   * let `CreditService` register the evaluated request through the repository layer
   * return approval or rejection message

Rejected request behavior:

* Set `request_rejected = True`
* Ask whether the user wants to complete a credit interview
* Set `system_bridge_message` if the user accepts interview
* Preserve the rejected `credit_request` for one explicit reassessment turn after the interview completes
* If reassessment still rejects the increase, keep `limite_credito` unchanged

Rules:

* Credit approval must come only from `CreditService`
* Node must never approve credit directly
* Node must not update customer score
* Node must not write CSV directly
* After a user-facing credit reply is generated (for example showing current limit or approved/rejected request), the current invoke should end and wait for the next user message.

---

## 3.5 Node: `credit_interview_node`

Responsibility:

* Conduct a linear and validated financial interview.

Interview order:

```txt
income → employment → expenses → dependents → debts → complete
```

Flow for each field:

1. Ask for the current field if no input is available
2. Normalize user input with deterministic parsing first and constrained LLM fallback only when needed
3. Validate normalized value with Pydantic schema
4. If valid:

   * store value in `interview_data`
   * advance `interview_step`
5. If invalid:

   * keep the same `interview_step`
   * set `last_action_summary = INVALID_INPUT`
   * ask the same question again with clearer guidance

Completion flow:

1. When all fields are valid, call `ScoreService`
2. Call the appropriate deterministic service to persist the new score through the repository layer
3. If update succeeds:

   * set `interview_complete = True`
   * clear `interview_data`
   * return a completion message
   * end the current invoke and wait for next user message
   * allow the next turn to confirm reassessment of the same rejected request
4. If update fails:

   * retain `interview_data`
   * set `recoverable_error = True`
   * set `retry_available = True`
   * inform the user that the update could not be completed

Rules:

* The node must not skip fields
* The node must not calculate score before all fields are valid
* The node must not silently discard collected interview data after a recoverable write failure
* Retry must be explicit, not an automatic hidden loop

---

## 3.6 Node: `exchange_node`

Responsibility:

* Provide currency quotes

Flow:

1. Identify currency
2. Call `ExchangeService`
3. Validate response

Fallback:

* If API fails:

  * return safe message
  * do NOT break flow

Turn behavior:

* After a user-facing quote reply is generated, the current invoke should end and wait for the next user message.

---

## 3.7 Node: `ending_node`

Responsibility:

* Terminate session

Flow:

1. Send final message
2. Clear sensitive state
3. Set `ended = True`

---

## 3.8 Node: `registration_node`

Responsibility:

* Conduct new-customer registration flow with deterministic validation.

Flow:

1. Collect full name (`REGISTRATION_ASKING_NAME`)
2. Collect CPF (`REGISTRATION_ASKING_CPF`)
3. Collect birth date (`REGISTRATION_ASKING_BIRTH_DATE`)
4. Validate and persist through `RegistrationService`
5. Authenticate the newly created customer and hand off to intent flow

Rules:

* User may cancel registration and return to login flow (`ASKING_CPF`)
* Duplicate CPF must be handled safely with user guidance
* Registration node must not write CSV directly
* Registration completion must preserve deterministic service authority

---

## 4. Transition Logic

All transitions are deterministic.

---

Fatal errors:

* Missing required CSV files
* Corrupted foundation CSV data
* Non-recoverable repository initialization failure
* Invalid required configuration

Fatal errors must route to `ending_node` with a safe user-facing message and must be logged with `trace_id`.

---

### Global Rules

```txt
if ended == True → ending_node
if is_blocked == True → ending_node
if fatal_error == True → ending_node
```

---

### Triage

```txt
if auth_attempts >= 3 → ending_node
if current_state starts with REGISTRATION_ and last_action_summary == REGISTRATION_STARTED → END
if current_state starts with REGISTRATION_ and last_action_summary != REGISTRATION_STARTED → registration_node
if current_state in {ASKING_CPF, ASKING_BIRTH_DATE} → END (wait next user turn)
if authenticated == True and auth turn consumed credential-only input → END (handoff prepared)
if authenticated == True and current_state == CREDIT_INTERVIEW_IN_PROGRESS → credit_interview_node
if authenticated == True and current_state == RECALCULATING_SCORE and interview_complete == True → credit_node
if authenticated == True and current_state == OFFERING_PARTIAL_INCREASE → credit_node
if authenticated == True and session already authenticated → intent_node
else → triage_node
```

Notes:

* Triage must not loop in the same invoke while waiting for user credentials.
* Successful credential-only authentication completes the turn and prepares handoff to `intent_node` for the next user message.

---

### Intent

```txt
if unknown_intent_count >= 3 → ending_node
if intent == credit → credit_node
if intent == exchange → exchange_node
if intent == end → ending_node
else → intent_node
```

---

### Credit

```txt
if recoverable_error == True AND retry_available == True → credit_node
if last_action_summary in {
   ASKED_FOR_NEW_LIMIT,
   CREDIT_LIMIT_SHOWN,
   CREDIT_REQUEST_APPROVED,
   CREDIT_MAX_LIMIT_REACHED,
   PARTIAL_INCREASE_OFFERED,
   PARTIAL_INCREASE_APPROVED,
   CREDIT_INTERVIEW_OFFERED
} → END
if request_rejected == True AND interview_offer_response == accepted → credit_interview_node
if request_rejected == True AND interview_offer_response == declined → intent_node
if request_rejected == True AND interview_offer_response == unknown → credit_node
if current_state == RECALCULATING_SCORE AND interview_complete == True → credit_node
else → intent_node
```

---

### Interview

```txt
if interview emitted a user-facing question or retry prompt → END
if interview_complete == True → END
else → credit_interview_node
```

---

### Exchange

```txt
always → intent_node
```

---

### Registration

```txt
if ended == True → ending_node
if current_state == ERROR → ending_node
else → END
```

---

## 5. Transition Contract

All transitions must follow:

1. Based on structured state only
2. Guarded by `StateGuard` checks (entry checks in V1)
3. Explicit exit conditions per node
4. No hidden transitions
5. Invalid transitions must:

   * be blocked
   * be logged
   * redirect safely

---

## 6. State Guard Rules

`StateGuard` enforces:

* Authentication before protected flows
* Protected-node entry checks (`credit_node`, `credit_interview_node`, `exchange_node`)
* Domain isolation
* Circuit breaker enforcement

Invalid transition behavior:

```txt
reject → log → redirect → safe response
```

---

## 7. Domain State Cleanup

Mandatory cleanup rules:

* Leaving credit → clear `credit_request`
* Leaving interview → clear `interview_data`
* Leaving exchange → clear `exchange_request`
* Ending session → clear all sensitive data

---

## 7.1 Bridge Message Contract

`system_bridge_message` preserves natural continuity between domains.

Consumption rule:

* The next node that produces a user-facing response must prepend `system_bridge_message` to its generated reply.
* The final composed message must be stored in `last_assistant_output`.
* After being consumed, `system_bridge_message` must be cleared in the same turn.
* `system_bridge_message` must never be returned as a separate API field.

Example:

```txt
system_bridge_message:
"Como sua solicitação não foi aprovada com o score atual, posso fazer algumas perguntas rápidas para atualizar sua análise de crédito."

node reply:
"Para começar, qual é sua renda mensal?"

last_assistant_output:
"Como sua solicitação não foi aprovada com o score atual, posso fazer algumas perguntas rápidas para atualizar sua análise de crédito. Para começar, qual é sua renda mensal?"
```

Rules:

1. Bridge messages must be user-facing and natural.
2. Bridge messages must not expose internal agents, nodes, or graph mechanics.
3. Bridge messages must be consumed once and then cleared.
4. Bridge messages must never change business logic.

---

## 8. LLM Interaction Model

---

## 8.1 Allowed Tasks

LLM may:

* Classify intent
* Generate natural responses
* Help extract structured values

---

## 8.2 Forbidden Tasks

LLM must NOT:

* Authenticate users
* Approve credit
* Calculate score
* Control state transitions
* Modify persistence

---

## 8.3 Context Strategy

LLM receives:

```json
{
  "current_state": "...",
  "authenticated": true,
  "current_node": "...",
  "last_user_input": "...",
  "recent_messages": [...],
  "constraints": [...]
}
```

Rules:

* `current_node` is derived runtime metadata.
* `current_node` is not a required persisted `GraphState` field.
* Canonical persisted state fields remain those defined in `GraphState`.

Priority:

1. Structured state
2. Context
3. Short memory

---

## 8.4 Intent Prompt

```txt
Return ONLY JSON:

{
  "intent": "credit | exchange | end | unknown"
}
```

Rules:

* No explanation
* No extra text
* No assumptions

---

## 9. Node Execution Contract

Every node must:

1. Read state
2. Call services
3. Optionally call LLM
4. Update relevant fields
5. Return state

Must NOT:

* Write CSV directly
* Trust LLM blindly
* Modify unrelated state
* Skip validation

---

## 10. Circuit Breaker Strategy

If intent fails 3 times:

```txt
unknown_intent_count >= 3
```

Then:

* Transition to ending_node
* Return safe message
* Suggest alternative

---

## 11. Failure Handling

System must degrade safely:

* LLM failure: fallback
* API failure: safe response
* CSV failure: log + inform
* Invalid input: re-ask
* Session not found on resume: reset

---

## 11.1 Error Recovery Policy

The state machine will not introduce a dedicated `error_recovery_node` in V1.

Instead, recovery is handled through structured state fields:

```txt
recoverable_error
retry_available
fatal_error
last_error
system_bridge_message
```

Recovery rules:

* Recoverable domain errors keep the user in the current domain when retry is safe
* Non-recoverable errors must set `fatal_error = True` when the current session cannot continue safely
* Fatal errors route to `ending_node`
* CSV write failures during interview retain collected data for explicit retry
* Exchange API failures route back to `intent_node`
* LLM failures use fallback provider or deterministic classifier

Rationale:

* Avoids adding an extra orchestration layer
* Keeps the graph small and testable
* Makes recovery behavior explicit in state

---

## 12. Completion Criteria

State machine is valid when:

1. All nodes defined
2. All transitions explicit
3. No dead-end states
4. No implicit transitions
5. No LLM-driven routing
6. Domain isolation enforced
7. Circuit breaker implemented
8. State cleanup guaranteed
9. Testable paths exist for all flows
