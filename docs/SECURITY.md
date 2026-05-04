# Segurança

## 1. Escopo

Este documento descreve os controles de segurança aplicados no Banco Ágil para a V1 publicada.

Áreas cobertas:

* Fronteira de autenticação e proteção de fluxo
* Gerenciamento de segredos
* Segurança na persistência em CSV
* Segurança nas respostas HTTP
* Limitações conhecidas de sessão na V1

---

## 2. Fronteira Determinística vs LLM

Regra principal:

* A LLM não decide autenticação, aprovação de crédito, cálculo de score, persistência ou transições críticas de estado.

Controles aplicados:

* Autenticação tratada por serviço determinístico
* Decisões de crédito tratadas por serviço determinístico
* Persistência exclusivamente via repositories
* Roteamento guiado por estado estruturado, não por saída livre do modelo
* Saída de intent validada contra enum permitido antes de qualquer uso

Referências:

* [ARCHITECTURE.md](ARCHITECTURE.md)
* [STATE_MACHINE.md](STATE_MACHINE.md)
* [DECISIONS.md](DECISIONS.md)

---

## 3. Segredos e Configuração Sensível

Variáveis sensíveis principais:

* `XAI_API_KEY`
* `OPENAI_API_KEY`
* `EXCHANGE_API_KEY`
* `SEARCHAPI_API_KEY` (opcional)
* `SERPAPI_API_KEY` (opcional)

Regras:

* Segredos devem ser carregados exclusivamente via variáveis de ambiente
* Nenhum segredo pode ser commitado no repositório
* O nome canônico da chave xAI é `XAI_API_KEY` — não usar `GROK_API_KEY`
* Logs devem sanitizar padrões de chave e valores do header `Authorization`

Referências:

* [README.md](../README.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 4. Segurança de Sessão na V1

Modelo atual:

* Sessão armazenada em memória de processo (`MemorySaver` + `SessionService`)
* Sem expiração por TTL ativa no backend na V1
* Reinício do processo invalida todas as sessões existentes

Comportamento da API:

* Sessão inexistente retorna `SESSION_NOT_FOUND`
* O frontend deve criar ou resetar a sessão quando necessário

Risco residual conhecido:

* A V1 não implementa expiração por inatividade
* TTL está reservado para uma versão pós-V1

---

## 5. Endpoints Administrativos

Endpoints:

* `GET /api/v1/admin/csv/{table}`
* `POST /api/v1/admin/csv/reset`

Controles:

* Disponíveis apenas quando `APP_ENV=local`
* Qualquer outro ambiente retorna `HTTP 403`
* Finalidade: inspeção local e reset de dados CSV durante o desenvolvimento

---

## 6. Persistência em CSV e Integridade

Regras:

* Services não escrevem arquivos CSV diretamente
* Repositories concentram todo acesso de leitura e escrita
* Escritas devem usar estratégia segura com tratamento de erros
* Falhas devem ser controladas e não vazar detalhes internos na resposta da API

Objetivos:

* Reduzir risco de corrupção e acesso não intencional
* Manter fronteira clara entre lógica de domínio e persistência

---

## 7. Segurança nas Respostas e Observabilidade

As respostas públicas da API não devem expor:

* Conteúdo completo do `GraphState`
* CPF autenticado
* Objeto `current_customer`
* Stack traces
* Segredos ou configurações de provider

Observabilidade:

* `trace_id` incluído em todas as respostas para correlação de suporte
* Logs internos podem conter detalhes técnicos, mas devem sanitizar valores sensíveis

---

## 8. Checklist Pré-Publicação

Antes de tornar o repositório público:

* Confirmar que `.env` está no `.gitignore`
* Confirmar que `.env.example` não contém segredos reais
* Confirmar que endpoints admin retornam `403` fora do ambiente local
* Confirmar ausência de chaves hardcoded no backend ou frontend
* Confirmar que os documentos principais estão alinhados com o comportamento real da sessão na V1

---

## 9. Referências

* [README.md](../README.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)
* [STATE_MACHINE.md](STATE_MACHINE.md)
* [DECISIONS.md](DECISIONS.md)
* [API_CONTRACT.md](API_CONTRACT.md)
