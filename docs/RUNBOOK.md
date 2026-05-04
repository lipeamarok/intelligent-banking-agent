# Local Execution Runbook

## 1. Installation

1. Navigate to the backend folder:
   - `cd backend`
2. Create a virtual environment:
   - `python -m venv .venv`
3. Activate the environment:
   - Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
4. Install dependencies:
   - `python -m pip install -e .[dev]`

## 2. Environment Variables

1. Copy `.env.example` to `.env`
2. Set at minimum:
   - `XAI_API_KEY`
   - `OPENAI_API_KEY`
   - `EXCHANGE_API_KEY`
3. Important note:

   - When starting with `uvicorn app.main:app --reload`, the backend loads `backend/.env` automatically in local runtime.
   - Non-empty variables already exported in the shell take precedence over `.env` values.
   - If a variable exists but is empty in the shell, the `.env` value is used as a local fallback.

4. Supporting variables:
   - `APP_ENV`
   - `APP_VERSION`
   - `DATA_DIR` (canonical: `app/data`)
   - `EXCHANGE_PROVIDER`

## 3. Tests

- Full run:
  - `python -m pytest`
- Quiet run:
  - `python -m pytest -q`

## 4. Running the API

- Basic command:
  - `uvicorn app.main:app --reload`
- Recommended command (handles busy port and correct venv):
  - `powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1`
- Recommended command with cleanup of existing listener on port 8000:
  - `powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1 -KillExisting`
- Base endpoint:
  - `http://localhost:8000/api/v1`

## 5. Smoke Bootstrap

- Purpose: validate local CSVs (presence + headers) and bootstrap wiring without external calls
- Command:
  - `python scripts/smoke_bootstrap.py`

## 5.2 Smoke Triage Routing With Real LLM (Controlled)

- Purpose: validate intent classification for post-auth routing only, using real Grok without automatic fallback
- Command:
  - `python scripts/smoke_triage_routing_llm.py`
- Operational rules:
  - Run manually once per validation round
  - Does not print keys, tokens, authorization headers, or `.env` contents
  - Limited to four canonical phrases
  - Reports intent, provider, model, and `fallback_triggered` per phrase

## 5.1 CSV Data Seed

- Command (create missing files, no overwrite):
  - `python scripts/seed_data.py`
- Command (full deterministic reset):
  - `python scripts/seed_data.py --reset`
- Expected files under `DATA_DIR=app/data`:
  - `clientes.csv`
  - `score_limite.csv`
  - `solicitacoes_aumento_limite.csv`
- Canonical header for `score_limite.csv`:
  - `score_minimo,score_maximo,limite_maximo_permitido`

## 6. Smoke SearchApi

- Purpose: manual real call to the exchange provider
- Command:
  - `python scripts/smoke_searchapi_exchange.py`
- Note:
  - Run only in a controlled local environment
  - Requires `EXCHANGE_API_KEY` to be set

## 7. Common Issues

### EXCHANGE_API_KEY is not set

- Cause: variable not loaded in the current process
- Fix: export the variable in the current shell and restart the API

### graph unavailable

- Cause: bootstrap could not build the graph due to missing configuration
- Effect: the API may return a controlled unavailability error
- Fix: verify `XAI_API_KEY`, `OPENAI_API_KEY`, `EXCHANGE_API_KEY`, and `DATA_DIR`
- Safe diagnostics:
  - `python scripts/diagnose_runtime.py`
  - `python scripts/diagnose_http_chat.py`
  - `python scripts/diagnose_triage_flow.py`
  - `python scripts/smoke_triage_routing_llm.py`

### Missing or invalid CSV

- Cause: `DATA_DIR` is missing one of the three required CSVs or has an incorrect header
- Fix: run `python scripts/seed_data.py --reset` then `python scripts/smoke_bootstrap.py`

### Session not found

- Cause: `session_id` does not exist or session was lost after a process restart
- Fix: `POST /api/v1/sessions/reset` to start a new session

### malformed exchange provider response

- Cause: external provider response did not match the expected format
- Fix: verify the selected provider and run a manual smoke for diagnostics

### Port already in use

- Cause: another process is using port 8000
- Fix: start the server on a different port, for example:
  - `uvicorn app.main:app --reload --port 8001`

### Missing API keys

- Cause: required variables are empty
- Fix: populate `.env` and restart the process

## 8. How to Reset a Session

- Endpoint:
  - `POST /api/v1/sessions/reset`
- Result:
  - A new clean `session_id` for restarting the conversation

## 9. How to Clear the Test Cache

- Available function:
  - `app.api.dependencies.clear_api_dependency_caches`
- Quick example:
  - `python -c "from app.api import dependencies as d; d.clear_api_dependency_caches(); print('ok')"`
