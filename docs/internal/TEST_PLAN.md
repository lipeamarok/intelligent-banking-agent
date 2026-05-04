# Banco Ágil - Test Plan

**Version:** 1.0
**Reference Documents:** PROJECT.md, REQUIREMENTS.md, ARCHITECTURE.md, STATE_MACHINE.md, DECISIONS.md
**Status:** Ready for TDD Zero
**Purpose:** Define the testing strategy, scope, test cases, fixtures, mocks, acceptance gates, and manual validation checklist for the Banco Ágil Intelligent Banking Agent system.

---

## 1. Purpose

This document defines how the Banco Ágil system will be validated before, during, and after implementation.

The goal is not only to prove that the application works, but to prove that the architecture constraints are respected.

The test plan must validate:

* Authentication safety.
* Credit decision determinism.
* Score calculation correctness.
* CSV persistence safety.
* LangGraph state transitions.
* StateGuard enforcement.
* LLM fallback behavior.
* API contract stability.
* Frontend behavior without business logic.
* Failure recovery under controlled conditions.

Core principle:

```txt
If a behavior is business-critical, it must be covered by an automated test before implementation is considered complete.
```

---

## 2. Testing Philosophy

This project follows **TDD Zero** for deterministic core behavior.

Implementation order:

```txt
1. Write tests
2. Watch tests fail for the right reason
3. Implement the minimum code required
4. Pass tests
5. Refactor without changing behavior
```

The system must not rely on manual testing for critical banking-adjacent rules.

Manual testing is reserved for:

* Final user experience.
* Demo flow validation.
* Visual feedback.
* Deployment smoke testing.

---

## 3. Testing Pyramid

```txt
                  Manual E2E / Demo UAT
                         ▲
                         │
              API + LangGraph Integration
                         ▲
                         │
        Services + Repositories + StateGuard Unit Tests
                         ▲
                         │
              Schemas and Validation Tests
```

### 3.1 Unit Tests

Purpose:

* Validate deterministic logic.
* Run fast.
* Avoid external dependencies.
* Protect business rules.

Target:

* Pydantic schemas (Schema tests must target Pydantic v2 behavior).
* NormalizerService.
* AuthService.
* ScoreService.
* CreditService.
* CSV repositories.
* StateGuard.
* LLMManager fallback with mocks.

### 3.2 Integration Tests

Purpose:

* Validate interaction between components.
* Validate graph flow.
* Validate API behavior.
* Validate state persistence across requests.

Target:

* LangGraph execution.
* FastAPI endpoints.
* Session state lifecycle.
* CSV repositories with temporary files.
* Mocked LLM and exchange providers.

Triage hardening integration rule:

* Triage flow validation must include real graph + real API + real CSV repositories.
* For triage-first scenarios, tests must avoid mocks/fakes and avoid external provider calls.
* First turn (`olá`) must return `ASKING_CPF` without relying on recursion errors.

Triage Routing IA controlled rule:

* Routing tests may run in a separate phase with controlled real LLM smoke.
* Real LLM smoke must run only after successful authentication preconditions.
* Real LLM smoke must be limited, sanitized, and must not auto-retry on provider failure.

Mandatory assertions for routing phase:

* `intent_node` must not run before successful authentication.
* Pre-auth turns must not call intent classifier providers.
* Classifier output must map to `Intent` enum only.
* Raw node names (for example `credit_node`) must be rejected as `unknown`.
* Invalid or verbose classifier output must be treated as `unknown`.
* Routing after auth must be deterministic for canonical phrases.
* `credit_limit` -> credit flow
* `credit_increase` -> credit flow
* `exchange_quote` -> exchange flow
* `end_conversation` -> ending flow

Happy-path triage assertions (Phase 13C):

* Greeting must request CPF in natural language without exposing internal states.
* CPF with punctuation (for example `123.456.789-01`) must be accepted and normalized.
* Birth date input `12-05-1990` must authenticate correctly when data matches CSV.
* Invalid birth-date text must not end the session before three failed authentication attempts.
* After successful authentication, the next user message must route to the target agent without re-requesting CPF.
* Happy-path API/UI turns must not rely on `GraphRecursionError` recovery as normal behavior.

### 3.3 Manual UAT

Purpose:

* Validate final evaluator experience.
* Confirm frontend/backend integration.
* Confirm deployed demo usability.

Target:

* Public frontend.
* Full chat flows.
* Loading states.
* Friendly error handling.
* README instructions.

---

## 4. Test Environment

### 4.1 Test Framework

Required tools:

```txt
pytest
pytest-cov
pytest-asyncio if async flows are used
httpx test client for FastAPI if needed
unittest.mock or pytest monkeypatch
freezegun or injected time_provider for TTL tests
threading or concurrent.futures for controlled CSV contention tests
```

### 4.2 Test Isolation Rules

Automated tests must not depend on:

* Live Grok API.
* Live OpenAI API.
* Live exchange API.
* Production or demo CSV files.
* Frontend deployment.
* Network availability.

Tests must use:

* `tmp_path` for temporary CSV files.
* Mock LLM providers.
* Mock exchange provider.
* Controlled test fixtures.
* Deterministic input and output.

Exchange provider integration note:

* Provider adapters (for example SearchApi or SerpAPI) must be tested with fake HTTP clients.
* SearchApi is the initial adapter for manual smoke validation; SerpAPI remains supported.
* No automated test may call a live external exchange endpoint.

Bootstrap smoke note:

* `scripts/smoke_bootstrap.py` is local-only and must not execute external API calls.
* It may print only a safe settings summary and non-sensitive status messages.

### 4.3 Environment Variables in Tests

Tests must not require real secrets.

Allowed test values:

```txt
XAI_API_KEY=test-xai-key
OPENAI_API_KEY=test-openai-key
EXCHANGE_API_KEY=test-exchange-key
SEARCHAPI_API_KEY=test-searchapi-key
PRIMARY_MODEL=test-primary-model
FALLBACK_MODEL=test-fallback-model
SESSION_TTL_MINUTES=30
```

### 4.4 Coverage Target

Minimum expected coverage:

```txt
Core deterministic services: 90%+
Repositories: 85%+
StateGuard: 90%+
Graph routing: integration coverage for all main paths
Frontend: manual validation acceptable for V1
```

Coverage is a signal, not the final authority. A 95% coverage suite with weak assertions is not acceptable.

---

## 5. Test Data Strategy

### 5.1 Base Customers Fixture

Test fixtures should include at least:

```csv
cpf,data_nascimento,nome,score_atual,limite_credito
12345678901,1990-05-12,Ana Silva,720,5000.00
98765432100,1985-10-03,Carlos Souza,580,2500.00
45678912300,1998-02-20,Marina Costa,830,12000.00
```

### 5.2 Score Limit Fixture

```csv
score_minimo,score_maximo,limite_maximo_permitido
0,299,1000.00
300,499,2500.00
500,699,5000.00
700,849,10000.00
850,1000,20000.00
```

### 5.3 Credit Requests Fixture

Initial state:

```csv
cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido
```

Rules:

* Tests must create isolated temporary files.
* Tests must not mutate repository sample data.
* Tests must assert headers remain intact.

---

## 6. Unit Test Plan

## 6.1 Schema Validation Tests

### TC-SCHEMA-001 - Valid Customer schema

Given valid customer data
When `Customer` schema is instantiated
Then validation succeeds

### TC-SCHEMA-002 - Invalid customer score

Given `score_atual` below 0 or above 1000
When `Customer` schema is instantiated
Then validation fails

### TC-SCHEMA-003 - Invalid credit request status

Given a credit request with unsupported status
When `CreditLimitRequest` schema is instantiated
Then validation fails

### TC-SCHEMA-004 - Valid interview payload

Given valid interview data
When `CreditInterviewData` schema is instantiated
Then validation succeeds

### TC-SCHEMA-005 - Invalid interview financial values

Given negative income, expenses, or dependents
When `CreditInterviewData` schema is instantiated
Then validation fails

---

## 6.2 NormalizerService Tests

### TC-NORM-001 - Normalize BRL formatted amount

Inputs:

```txt
R$ 5.000
R$ 5.000,00
5.000,00
5000 reais
```

Expected:

```txt
5000.0
```

### TC-NORM-002 - Normalize shorthand amount

Input:

```txt
10k
```

Expected:

```txt
10000.0
```

### TC-NORM-003 - Reject ambiguous amount

Inputs:

```txt
bastante
mais ou menos
alto
baixo
```

Expected:

* normalization fails
* clarification required

### TC-NORM-004 - Reject out-of-range amount

Given amount greater than 1,000,000
When normalized and validated
Then value is rejected

### TC-NORM-005 - Normalize debt answers

Inputs expected as true:

```txt
sim
tenho dívidas
yes
possuo dívidas
```

Inputs expected as false:

```txt
não
nao
sem dívidas
no
```

### TC-NORM-006 - Reject ambiguous debt answer

Inputs:

```txt
talvez
não sei
depende
```

Expected:

* normalization fails
* clarification required

### TC-NORM-007 - Normalize employment type

Inputs:

```txt
CLT -> formal
autônomo -> autonomo
autonomo -> autonomo
sem emprego -> desempregado
```

Expected:

* normalized supported employment type

Fallback-aware examples that should be covered:

* `faço bicos -> autonomo`
* `trabalho registrado -> formal`

### TC-NORM-008 - Normalize strict birth date format to ISO

Inputs:

```txt
12-05-1990
```

Expected:

```txt
1990-05-12
```

Rules:

* Human date input must use `DD-MM-YYYY`
* CSV comparison must use `YYYY-MM-DD`
* Invalid dates must be rejected
* Confirmation fallback coverage should include contextual examples such as `pode ser -> accepted` and `ok -> accepted`
* Dependents coverage should include `nenhum -> 0`

---

## 6.3 AuthService Tests

### TC-AUTH-001 - Authenticate valid customer

Given CPF and birth date matching `clientes.csv`
When `AuthService.authenticate` is called
Then authentication succeeds
And customer data is returned

### TC-AUTH-002 - Reject unknown CPF

Given CPF not present in `clientes.csv`
When authentication is attempted
Then authentication fails

### TC-AUTH-003 - Reject incorrect birth date

Given CPF exists but birth date does not match
When authentication is attempted
Then authentication fails

### TC-AUTH-004 - Preserve CPF as string

Given CPF with potential leading zeros
When customer record is loaded
Then CPF is preserved as string

### TC-AUTH-005 - Block after three failed attempts

Given three failed authentication attempts
When the third failure occurs
Then session is blocked
And protected flows remain inaccessible

---

## 6.4 ScoreService Tests

### TC-SCORE-001 - Calculate score for formal employee without debts

Given:

```txt
income=5000
expenses=2500
employment=formal
dependents=0
has_debts=false
```

When score is calculated
Then result follows the deterministic formula

### TC-SCORE-002 - Apply employment weights

Validate:

```txt
formal = +300
autonomo = +200
desempregado = 0
```

### TC-SCORE-003 - Apply dependent weights

Validate:

```txt
0 dependents = +100
1 dependent = +80
2 dependents = +60
3 or more = +30
```

### TC-SCORE-004 - Apply debt weights

Validate:

```txt
has_debts=true -> -100
has_debts=false -> +100
```

### TC-SCORE-005 - Avoid division by zero

Given expenses = 0
When score is calculated
Then no division error occurs
And formula uses `expenses + 1`

### TC-SCORE-006 - Clip score above 1000

Given inputs producing score greater than 1000
When score is calculated
Then final score is 1000

### TC-SCORE-007 - Clip score below 0

Given inputs producing score below 0
When score is calculated
Then final score is 0

### TC-SCORE-008 - Reject invalid negative values

Given negative income, expenses, or dependents
When score calculation is requested
Then validation fails before calculation

---

## 6.5 CreditService Tests

### TC-CREDIT-001 - Get current credit limit

Given authenticated customer exists
When current credit limit is requested
Then service returns `limite_credito`

### TC-CREDIT-002 - Approve request within allowed limit

Given customer score maps to max allowed limit 10,000
And requested limit is 8,000
When request is evaluated
Then request is approved

### TC-CREDIT-003 - Reject request above allowed limit

Given customer score maps to max allowed limit 5,000
And requested limit is 8,000
When request is evaluated
Then request is rejected

### TC-CREDIT-004 - Reject invalid requested limit

Given requested limit is zero, negative, ambiguous, non-normalizable, or above 1,000,000 after normalization
When request is evaluated
Then validation fails

### TC-CREDIT-005 - Persist evaluated request

Given valid credit increase request
When evaluated
Then request is persisted with final status `aprovado` or `rejeitado`

### TC-CREDIT-006 - Decision rationale is produced

Given a credit request
When evaluated
Then service returns decision rationale containing score, requested limit, and allowed limit

---

## 6.6 CSV Repository Tests

### TC-REPO-001 - Read existing customer

Given `clientes.csv` contains a customer
When customer is read by CPF
Then repository returns correct customer data

### TC-REPO-002 - Return None for missing customer

Given customer does not exist
When lookup is performed
Then repository returns no customer

### TC-REPO-003 - Preserve headers when appending credit request

Given empty `solicitacoes_aumento_limite.csv` with headers
When request is appended
Then headers remain unchanged
And one row is added

### TC-REPO-004 - Update customer score atomically

Given customer exists
When score is updated
Then repository writes `.tmp` file first
And replaces original only after validation succeeds

### TC-REPO-005 - Keep original CSV when temp validation fails

Given `.tmp` validation fails
When update is attempted
Then original CSV remains unchanged
And `.tmp` is discarded

### TC-REPO-006 - Fail safely when lock timeout occurs

Given file lock cannot be acquired
When write operation is attempted
Then repository raises controlled error
And original CSV remains unchanged

### TC-REPO-007 - Remove orphan lock files during seed reset

Given orphan `.lock` files exist
When `seed_data.py` runs
Then lock files are removed
And CSV files are reset to known initial state

### TC-REPO-008 - Preserve score_limit as read-only during app flow

Given app flow executes credit evaluation
When score ranges are read
Then `score_limite.csv` is not modified

### TC-REPO-009 - Controlled concurrent CSV write contention

Given multiple concurrent write attempts against the same CSV file
When 10 workers attempt to update the same customer score or append credit requests
Then the repository must either serialize the writes through file locking or fail controlled operations with lock timeout
And the final CSV must preserve headers
And the final CSV must not contain partial rows
And the final CSV must remain readable by the repository

Note:

This test validates controlled contention behavior for challenge-level robustness. It is not a claim of production-grade concurrent persistence.

---

## 6.7 StateGuard Tests

### TC-GUARD-001 - Block protected flow before authentication

Given `authenticated=false`
When transition to credit, interview, or exchange is requested
Then StateGuard rejects transition
And redirects to triage

### TC-GUARD-002 - Allow protected flow after authentication

Given `authenticated=true`
When transition to credit is requested
Then transition is allowed

### TC-GUARD-003 - Block transition for blocked session

Given `is_blocked=true`
When any protected transition is requested
Then transition is rejected
And session routes to ending

### TC-GUARD-004 - Reject invalid transition

Given a transition not allowed by the state machine
When StateGuard validates it
Then transition is rejected
And violation is logged

### TC-GUARD-005 - Expired session requires re-authentication

Given session TTL has expired
When transition is requested
Then temporary sensitive state is cleared
And authentication is required again

### TC-GUARD-006 - Domain cleanup occurs on transition

Given interview data exists
When flow leaves interview after completion
Then interview temporary data is cleared

### TC-GUARD-007 - Expire authenticated session using mocked time

Given an authenticated session
And session TTL is 30 minutes
When the time provider advances beyond the TTL
Then StateGuard must reject protected transitions
And sensitive temporary state must be cleared
And the user must be required to authenticate again

Rules:

* The test must not wait for real time to pass
* Use `freezegun` or an injected `time_provider`

---

## 6.8 LLMManager and Provider Tests

### TC-LLM-001 - Use Grok as primary provider

Given primary provider succeeds
When completion is requested
Then Grok provider is used
And OpenAI provider is not called

### TC-LLM-002 - Fallback to OpenAI when Grok fails

Given Grok provider fails
When completion is requested
Then OpenAI provider is called
And fallback is logged

### TC-LLM-003 - Use deterministic fallback when both providers fail

Given Grok and OpenAI both fail
When intent classification is requested
Then deterministic keyword classifier is used

### TC-LLM-004 - Reject invalid structured LLM output

Given provider returns malformed JSON or unsupported intent
When output is parsed
Then output is rejected
And unknown intent count is incremented

### TC-LLM-005 - Automated tests do not require real API keys

Given test suite runs locally
When LLM tests execute
Then no live API call is made

### TC-LLM-006 - PromptBuilder includes required structured context

Given a valid `GraphState`
When the PromptBuilder creates the LLM request
Then the structured context must include:

```txt
current_state
authenticated
current_node
last_user_input
supported_intents when intent classification is requested
constraints
```

Rules:

* `current_node` is derived runtime metadata.
* `current_node` must not be persisted as a required `GraphState` field.
* `current_agent` must not be used as a canonical state field.

And the prompt must not include:

```txt
full unlimited chat history
API keys
raw secrets
unmasked sensitive data when not necessary
```

### TC-LLM-007 - PromptBuilder remains stable after state refactor

Given optional fields are missing from `GraphState`
When PromptBuilder builds context
Then it must produce a valid request with safe defaults
And must not crash due to missing optional fields

---

## 6.9 ExchangeService Tests

### TC-EXCHANGE-001 - Return valid quote from provider

Given exchange provider returns valid response
When quote is requested
Then service returns `ExchangeQuote`

### TC-EXCHANGE-002 - Default to USD when currency is missing

Given user asks for exchange quote without specifying currency
When request is processed
Then service defaults to USD

### TC-EXCHANGE-003 - Reject invalid provider response

Given external provider returns malformed data
When response is parsed
Then service returns controlled error

### TC-EXCHANGE-004 - Handle provider failure gracefully

Given external API fails
When quote is requested
Then no crash occurs
And safe failure is returned

---

## 6.10 Boot and Seed Safety Tests

### TC-INFRA-001 - Missing CSV files fail clearly or require explicit seed

Given required CSV files are missing
When the application starts or repositories initialize
Then the system must not operate in an inconsistent state

Accepted behaviors:

1. Fail startup with a clear `MissingDataFileError`
2. Or expose a documented explicit seed/reset command

Rejected behavior:

* Silently creating incomplete CSV files during normal runtime

Smoke expectation:

* `python scripts/smoke_bootstrap.py` must fail with clear message and non-zero exit when required CSV files are missing or headers are invalid.

### TC-INFRA-002 - Seed script restores foundation data

Given CSV files are missing, empty, or corrupted
When `seed_data.py` is executed manually
Then all required CSV files are recreated with valid headers and known sample rows
And orphan `.lock` files are removed

### TC-INFRA-003 - Seed script is idempotent

Given `seed_data.py` has already been executed
When it is executed again
Then the final CSV state remains valid and predictable
And duplicate header rows are not created

---

## 7. Integration Test Plan

## 7.1 Authentication Flow

### TC-INT-AUTH-001 - Full successful authentication flow

Given new session
When user provides valid CPF and birth date
Then session becomes authenticated
And graph routes to intent identification

### TC-INT-AUTH-002 - Authentication failure then success

Given new session
When user fails once and succeeds on second attempt
Then session becomes authenticated
And `auth_attempts` is reset to 0 after successful authentication

### TC-INT-AUTH-003 - Three failures end session

Given new session
When user fails authentication three times
Then graph routes to ending node
And session is blocked

---

## 7.2 Credit Flow

### TC-INT-CREDIT-001 - Consult credit limit after authentication

Given authenticated session
When user asks for current limit
Then credit node returns current limit

### TC-INT-CREDIT-002 - Approve credit increase request

Given authenticated customer with sufficient score
When user requests allowed limit
Then request is approved
And CSV request row is created

### TC-INT-CREDIT-003 - Reject credit increase request

Given authenticated customer with insufficient score
When user requests limit above allowed maximum
Then request is rejected
And interview offer is presented

### TC-INT-CREDIT-004 - Decline interview after rejection

Given rejected credit request
When user declines interview
Then graph returns to intent identification or closing option

---

## 7.3 Credit Interview Flow

### TC-INT-INTERVIEW-001 - Complete interview and update score

Given rejected credit request
And user accepts interview
When all interview fields are provided correctly
Then score is recalculated
And `clientes.csv` is updated
And graph returns to credit flow

### TC-INT-INTERVIEW-002 - Invalid interview input repeats same step

Given user is at interview income step
When user provides ambiguous value
Then graph remains at the same interview step
And asks for clarification

### TC-INT-INTERVIEW-003 - Interview cannot skip steps

Given user is at employment step
When user tries to provide debt information early
Then graph remains at employment step

### TC-INT-INTERVIEW-004 - CSV write failure retains interview data

Given interview is complete
And customer score update fails
When repository returns write error
Then `interview_data` remains available
And `retry_available=true`

---

## 7.4 Exchange Flow

### TC-INT-EXCHANGE-001 - Exchange quote success

Given authenticated session
When user asks for USD quote
Then exchange node returns quote

### TC-INT-EXCHANGE-002 - Exchange provider failure

Given exchange provider fails
When user asks for quote
Then graph returns safe message
And routes back to intent identification

### TC-INT-EXCHANGE-003 - Exchange requires authentication

Given unauthenticated session
When user asks for exchange quote
Then graph routes to triage first

---

## 7.5 State Machine and Circuit Breaker

### TC-INT-GRAPH-001 - Unknown intent counter increments

Given authenticated session
When user provides unsupported request
Then `unknown_intent_count` increments

### TC-INT-GRAPH-002 - Unknown intent counter resets after valid intent

Given previous unknown intent count > 0
When user provides valid intent
Then counter resets

### TC-INT-GRAPH-003 - Circuit breaker ends after three unknown intents

Given authenticated session
When user provides unknown intent three times consecutively
Then graph routes to ending node

### TC-INT-GRAPH-004 - Domain purge after interview completion

Given interview completes successfully
When graph routes back to credit
Then temporary interview data is cleared

### TC-INT-GRAPH-005 - Bridge message is consumed and cleared

Given `system_bridge_message` exists
When next node uses it
Then message is included in user-facing response
And cleared from state

### TC-INT-GRAPH-006 - Session expiration blocks graph continuation

Given an authenticated graph session
And runtime state exists in MemorySaver
When the session is expired according to backend TTL
Then the graph must not continue protected flow
And must route the user back to authentication or safe ending state

### TC-INT-GRAPH-007 - Fatal persistence error routes to ending node

Given a graph session is active
And a non-recoverable persistence error occurs, such as missing required CSV files or corrupted foundation CSV data
When the graph receives the error
Then `fatal_error` must be set to true
And the graph must route to `ending_node`
And the user must receive a safe failure message
And the error must be logged with `trace_id`

---

## 7.6 API Integration Tests

### TC-API-001 - Health endpoint

Given backend is running
When `GET /api/v1/health` is called
Then response is 200
And body contains status ok

### TC-API-002 - Chat endpoint creates session

Given request has no `session_id`
When `POST /api/v1/chat` is called
Then response includes a new `session_id`

### TC-API-003 - Chat endpoint continues existing session

Given request has valid `session_id`
When `POST /api/v1/chat` is called
Then backend uses existing session state

### TC-API-004 - Reset session endpoint

Given existing session
When `POST /api/v1/sessions/reset` is called
Then the backend returns a new usable `session_id`
And the new session starts unauthenticated
And previous authentication status, domain data, and recent messages are not preserved

### TC-API-005 - API response follows contract

Given any valid chat request
When response is returned
Then body contains:

```txt
session_id
reply
agent
state
ended
trace_id
metadata
```

---

## 8. Contract Testing Plan

API contract must be stable between backend and frontend.

Contract checks:

1. `POST /api/v1/chat` request shape matches `ChatRequest`.
2. `POST /api/v1/chat` response shape matches `ChatResponse`.
3. `agent` value is one of allowed public agent labels.
4. `state` value is a public-safe state string.
5. `trace_id` is always present.
6. `metadata` is present and is either `null` or follows `ChatMetadata`.
7. Error responses follow standard error shape.
8. Frontend does not depend on internal node names.

Contract violation blocks frontend implementation.

---

## 9. Manual UAT Plan

Manual validation must be performed after backend and frontend are connected.

## 9.1 Happy Path - Credit Limit

Steps:

1. Open frontend.
2. Start conversation.
3. Authenticate with valid customer.
4. Ask current credit limit.
5. Confirm limit is displayed correctly.

Expected:

* No internal agent names are shown.
* Response is clear.
* No frontend error occurs.

---

## 9.2 Credit Increase Approved

Steps:

1. Authenticate as high-score customer.
2. Request credit increase within allowed limit.
3. Confirm approval.
4. Inspect `solicitacoes_aumento_limite.csv`.

Expected:

* Request row exists.
* Status is `aprovado`.
* Timestamp is ISO 8601.

---

## 9.3 Credit Increase Rejected + Interview

Steps:

1. Authenticate as lower-score customer.
2. Request high credit limit.
3. Confirm rejection.
4. Accept interview.
5. Complete all financial questions.
6. Confirm score update.
7. Return to credit flow.

Expected:

* Natural language bridging occurs.
* Interview does not skip steps.
* `clientes.csv` score is updated.
* User returns to credit flow naturally.

---

## 9.4 Exchange Quote

Steps:

1. Authenticate.
2. Ask for USD quote.
3. Observe response.

Expected:

* Quote appears if provider succeeds.
* Friendly failure appears if provider fails.
* No internal API errors are exposed.

---

## 9.5 Session Reset

Steps:

1. Authenticate.
2. Click reset.
3. Start new conversation.

Expected:

* Previous state is cleared.
* User must authenticate again.

---

## 9.6 LLM Fallback Smoke Test

Steps:

1. Temporarily disable or mock primary provider.
2. Send intent classification request.
3. Confirm fallback provider is used.

Expected:

* User does not see provider failure.
* Logs show fallback activation.
* Conversation continues.

---

## 10. Frontend Validation Plan

The frontend must be validated primarily against API behavior.

Checklist:

* Chat displays user and assistant messages.
* Input disables or shows loading while waiting.
* Loading message is contextual when possible.
* Error banner appears on backend error.
* Reset button calls reset endpoint.
* Session ID is stored client-side for UX continuity.
* No business rules exist in frontend components.
* No API keys are present in frontend code or environment.

Forbidden frontend behavior:

* Calculating score.
* Checking authentication rules.
* Deciding credit approval.
* Reading CSV.
* Calling LLM providers.
* Inferring graph transitions.

---

## 11. Observability Validation

Logs must be inspected during integration and manual tests.

Required events:

* `api_request_received`
* `session_created`
* `session_loaded`
* `state_transition`
* `state_guard_rejected_transition`
* `llm_provider_called`
* `llm_fallback_triggered`
* `credit_decision`
* `score_recalculated`
* `csv_write_success`
* `csv_write_failure`
* `exchange_quote_success`
* `exchange_quote_failure`

Additional required validation:

* Every API request must generate or propagate a `trace_id`
* The same `trace_id` must appear in graph, service, repository, and LLM logs for the same request
* Credit decision logs must include score, requested limit, allowed limit, and decision rationale
* LLM fallback logs must include provider, model, latency, and fallback status

Required metadata when applicable:

* `trace_id`
* `session_id`
* `component`
* `agent`
* `from_state`
* `to_state`
* `decision_rationale`
* `provider`
* `model`
* `latency_ms`
* `input_tokens`
* `output_tokens`

Security rule:

* Logs must not expose full CPF or API keys.

---

## 12. Test Execution Commands

Suggested commands:

```bash
# Run all backend tests
pytest

# Run only unit tests
pytest backend/app/tests/unit

# Run only integration tests
pytest backend/app/tests/integration

# Run with coverage
pytest --cov=backend/app --cov-report=term-missing
```

Final commands may be adjusted based on actual project structure.

---

## 13. Quality Gates

## 13.1 Gate 1 - Before Core Implementation

Required:

* Schema tests exist.
* Service tests exist.
* Repository tests exist.
* StateGuard tests exist.

Blocking condition:

* Core service implementation starts without tests.

---

## 13.2 Gate 2 - Before LangGraph Integration

Required:

* AuthService tests passing.
* ScoreService tests passing.
* CreditService tests passing.
* NormalizerService tests passing.
* Repository tests passing.
* Atomic CSV write tests passing.
* Controlled CSV contention test passing.
* Seed script tests passing.

Blocking condition:

* Graph implementation starts while deterministic core is unstable.

---

## 13.3 Gate 3 - Before LLM Integration

Required:

* Graph works with mocked intent outputs.
* StateGuard tests passing.
* Circuit breaker tested.
* Domain cleanup tested.
* Session expiration behavior tested.
* PromptBuilder structured context tests defined.

Blocking condition:

* Real LLM is introduced before graph flow works deterministically.

---

## 13.4 Gate 4 - Before Frontend Implementation

Required:

* API contract documented.
* API integration tests passing.
* `POST /api/v1/chat` stable.
* Error response format stable.

Blocking condition:

* Frontend starts before API contract is stable.

---

## 13.5 Gate 5 - Before Deploy

Required:

* Main integration flows pass.
* README instructions tested.
* `.env.example` complete.
* No secrets committed.
* Seed script tested.
* Manual UAT checklist passed locally.

Blocking condition:

* Deploy with failing deterministic core tests.

---

## 14. Definition of Done for Testing

Testing is considered complete when:

1. All deterministic service tests pass.
2. Repository tests pass using temporary files.
3. StateGuard blocks invalid transitions.
4. LangGraph integration tests cover main flows.
5. LLM fallback is tested with mocks.
6. Exchange failure is tested with mocks.
7. API responses match contract.
8. Manual UAT checklist is completed.
9. Logs include traceable business events.
10. No automated test requires real API credentials.
11. No frontend business logic exists.
12. README documents how to run tests.

---

## 15. Non-Goals

The test plan does not require for V1:

* Load testing.
* Browser automation with Playwright.
* Real provider integration tests in CI.
* OpenTelemetry validation.
* Real bank-grade security testing.
* Mutation testing.
* Contract testing with external tooling.
* Production-grade concurrency benchmarking.

These may be added later if the project evolves beyond the technical challenge.

---

## 16. Execução local e política de testes

### 16.1 Comandos locais

Comando completo:

```bash
python -m pytest
```

Comando resumido:

```bash
python -m pytest -q
```

### 16.2 Tipos de teste

O projeto combina:

* unit tests para schemas, services e repositories
* integration tests para LangGraph, API e fluxo entre camadas
* testes de contrato para envelopes e formatos publicos

### 16.3 Politica de mocks e fakes

* Providers de LLM e cambio devem ser testados com mocks/fakes
* Clientes HTTP em testes devem ser fakes quando aplicavel
* Fixtures locais devem eliminar dependencia de rede

### 16.4 Regra de isolamento

A suite automatizada nao deve chamar APIs reais externas.

### 16.5 Smokes manuais separados

Validacoes manuais ficam fora da suite automatizada, por exemplo:

* `python scripts/smoke_bootstrap.py`
* `python scripts/smoke_searchapi_exchange.py`
* `python scripts/smoke_serpapi_exchange.py`

### 16.6 Status atual aproximado

Estado esperado da suite:

```txt
Na última auditoria local, a suíte executou sem warnings relevantes.
```
