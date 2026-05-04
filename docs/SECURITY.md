# Security

## 1. Scope

This document describes the security controls applied in Banco Ágil for the published V1.

Covered areas:

* Authentication boundary and flow protection
* Secret management
* CSV persistence safety
* HTTP response safety
* Known session limitations in V1

---

## 2. Deterministic Boundary vs LLM

Core rule:

* The LLM does not decide authentication, credit approval, score calculation, persistence, or critical state transitions.

Controls in place:

* Authentication handled by a deterministic service
* Credit decisions handled by a deterministic service
* Persistence only through repositories
* Routing driven by structured state, not by free-form model output
* Intent output validated against an allowed enum before use

References:

* [ARCHITECTURE.md](ARCHITECTURE.md)
* [STATE_MACHINE.md](STATE_MACHINE.md)
* [DECISIONS.md](DECISIONS.md)

---

## 3. Secrets and Sensitive Configuration

Key sensitive variables:

* `XAI_API_KEY`
* `OPENAI_API_KEY`
* `EXCHANGE_API_KEY`
* `SEARCHAPI_API_KEY` (optional)
* `SERPAPI_API_KEY` (optional)

Rules:

* Secrets must be loaded from environment variables only
* No secret may be committed to the repository
* Canonical xAI key name is `XAI_API_KEY` — do not use `GROK_API_KEY`
* Logs must sanitize key patterns and `Authorization` header values

References:

* [README.md](../README.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 4. Session Security in V1

Current model:

* Session stored in process memory (`MemorySaver` + `SessionService`)
* No active TTL expiration on the backend in V1
* Process restart invalidates all existing sessions

API behavior:

* A non-existent session returns `SESSION_NOT_FOUND`
* The frontend must create or reset the session when required

Known residual risk:

* V1 does not implement inactivity-based expiration
* TTL is reserved for a post-V1 release

---

## 5. Admin Endpoints

Endpoints:

* `GET /api/v1/admin/csv/{table}`
* `POST /api/v1/admin/csv/reset`

Controls:

* Available only when `APP_ENV=local`
* Any other environment returns `HTTP 403`
* Purpose: local inspection and reset of CSV data during development

---

## 6. CSV Persistence and Integrity

Rules:

* Services do not write CSV files directly
* Repositories concentrate all read/write access
* Writes must use a safe strategy with error handling
* Failures must be controlled and must not leak internal details in the API response

Goals:

* Reduce corruption risk and unintended access
* Maintain a clear boundary between domain logic and persistence

---

## 7. Response Safety and Observability

Public API responses must not expose:

* Full `GraphState` contents
* Authenticated CPF
* `current_customer` object
* Stack traces
* Provider secrets or configuration

Observability:

* `trace_id` included in all responses for support correlation
* Internal logs may contain technical detail but must sanitize sensitive values

---

## 8. Pre-Publication Checklist

Before making the repository public:

* Confirm `.env` is in `.gitignore`
* Confirm `.env.example` contains no real secrets
* Confirm admin endpoints return `403` outside local environment
* Confirm no hardcoded keys in backend or frontend source
* Confirm core docs are aligned with actual V1 session behavior

---

## 9. References

* [README.md](../README.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)
* [STATE_MACHINE.md](STATE_MACHINE.md)
* [DECISIONS.md](DECISIONS.md)
* [API_CONTRACT.md](API_CONTRACT.md)
