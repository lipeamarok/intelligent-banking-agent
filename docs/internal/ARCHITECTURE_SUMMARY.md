# Architecture Summary

Este documento resume a arquitetura para avaliação técnica.

Conceito central: core determinístico vs camada probabilística controlada.

## 1. Decisões principais

- LangGraph para orquestração explícita de estados
- core determinístico vs camada probabilística controlada
- regras críticas em serviços determinísticos
- persistência V1 em CSV via camada de repositório
- LLM controlada para tarefas de linguagem e intenção
- API pública com contratos estáveis

## 2. Separação de responsabilidades

- API valida payload, gerencia sessão e expõe envelope público
- nodes orquestram transições e chamadas de domínio
- services aplicam regras de negócio
- repositories leem e escrevem CSV com segurança
- providers externos encapsulam integrações HTTP

## 3. Por que LangGraph

- fluxo é cíclico e orientado a estado
- transições ficam auditáveis
- reduz acoplamento entre agentes
- facilita testes de caminho e proteção de transição

## 4. Por que CSV com repository

- atende requisito do desafio
- isola persistência em camada própria
- permite troca futura por banco sem quebrar regras de domínio

## 5. Por que LLM controlada

- linguagem natural melhora UX
- decisões críticas continuam determinísticas
- evita delegar autenticação, score e aprovação de crédito para modelo probabilístico
- camada probabilística fica restrita a interpretação e geração de linguagem

## 6. Como fallback Grok/OpenAI funciona

- LLMManager usa Grok como primário
- em falha do primário, tenta OpenAI como fallback
- falhas são encapsuladas e cobertas por testes

## 7. Como câmbio externo funciona

- provider de câmbio é injetado no bootstrap
- adapters suportados: SearchApi e SerpApi
- testes usam fakes; smoke real é manual

## 8. Como a API evita expor internals

- responses usam tipos públicos de agent e state
- API não retorna GraphState completo
- API não retorna current_customer nem authenticated_cpf
- erros usam envelope controlado sem stack trace

## 9. Como os testes protegem arquitetura

- testes unitários para schemas, serviços e repositórios
- testes de integração para graph e API
- testes verificam ausência de chamadas reais externas na suíte
- testes verificam envelopes de erro e privacidade de resposta
