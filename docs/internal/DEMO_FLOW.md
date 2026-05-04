# Demo Flow

## Pré requisitos

- API em execução em <http://localhost:8000>
- dados CSV de clientes disponíveis no ambiente local
- opcional: jq para facilitar leitura de JSON

Antes da demo, prepare os CSVs locais:

- python scripts/seed_data.py --reset

Os exemplos assumem que existe cliente compatível no CSV local. Confira clientes.csv antes de executar.

Cliente seed fictício recomendado para a demo:

- nome: Ana Silva
- cpf: 12345678901
- data_nascimento: 1990-05-12

## 1. Health

curl <http://localhost:8000/api/v1/health>

Resposta esperada:

- status ok
- trace_id
- version

## 2. Reset de sessão

curl -X POST <http://localhost:8000/api/v1/sessions/reset>

Exemplo de resposta:
{
  "message": "Session reset successfully",
  "session_id": "...",
  "state": "STARTED",
  "ended": false,
  "trace_id": "..."
}

Guarde o valor de session_id.

## 3. Conversa via chat

### 3.1 Mensagem inicial (início de triagem)

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"message":"olá"}'

Use o `session_id` retornado para os próximos passos.

### 3.2 Enviar CPF

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"12345678901"}'

### 3.3 Enviar data de nascimento

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"12-05-1990"}'

Formato aceito no fluxo de triagem:

- 12-05-1990

### 3.4 Consultar limite

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"quero consultar meu limite"}'

### 3.5 Solicitar aumento

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"quero aumentar meu limite"}'

### 3.6 Informar novo limite

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"8000"}'

### 3.7 Fluxo de entrevista financeira (se ofertado)

Siga as perguntas de renda, emprego, despesas, dependentes e dívidas conforme resposta do agente.

### 3.8 Cotação de câmbio

curl -X POST <http://localhost:8000/api/v1/chat> \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<SESSION_ID>","message":"quero cotação do dólar"}'

## Observações importantes

- Use dados fictícios compatíveis com os CSV locais de seed. O CPF e a data precisam existir no dataset.
- Nem todo fluxo vai passar por entrevista financeira. Isso depende do resultado de crédito.
- As respostas seguem envelope público. A API não retorna GraphState completo.

## Validação opcional de roteamento IA controlado

Para validar apenas a etapa de Triage Routing com provedor real, execute localmente:

- python scripts/smoke_triage_routing_llm.py

Critérios esperados:

- execução única e manual
- no máximo quatro frases canônicas
- saída contendo `intent`, `provider`, `model` e `fallback_triggered`
- sem exposição de segredos

## Reutilização do session_id

- sempre reaproveite o mesmo session_id durante uma conversa
- se perder o session_id, use reset para iniciar nova sessão
