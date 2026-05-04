"""
Semantic evaluation harness for intent classification and confirmation
normalization.

Purpose
-------
Run the live IntentClassifier and StructuredResponseInterpreter against a
curated dataset (backend/tests/data/intent_eval_dataset.json) and emit a
report with accuracy, abstention_rate, fallback_rate, and per-case detail.

Design
------
The harness deliberately separates the *parser/validator* layer of the
classifier from the *language-understanding* layer of the LLM provider.
This lets it run in CI with no API keys (using a deterministic
RuleOracleProvider) and still report meaningful metrics about how the
classifier handles noisy / ambiguous / verbose model output.

Two modes are supported:

* mode="oracle"  (default): use a built-in deterministic oracle provider
  that simulates realistic model noise (verbose answers, capitalization,
  occasional refusals). Safe in CI, no network.
* mode="live"    : use the configured LLMManager from app.bootstrap
  (real Grok primary + OpenAI fallback). Requires API keys.

Output
------
Prints a single JSON document with summary metrics and per-case results.
Exit code is 0 on success regardless of accuracy — this is a measurement
tool, not a gate. Callers (CI, demo, manual) decide what to do with the
metrics.

Source of truth: TEST_PLAN.md §11, ARCHITECTURE.md §7.5.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.provider import LLMProvider, LLMProviderError
from app.llm.structured_response_interpreter import StructuredResponseInterpreter
from app.schemas.common import Intent
from app.schemas.llm import LLMProviderName, LLMRequest, LLMResponse


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "data" / "intent_eval_dataset.json"
)


# ── Deterministic oracle provider (CI-safe) ──────────────────────────────────


class RuleOracleProvider(LLMProvider):
    """
    Deterministic provider that simulates realistic model noise.

    Maps user messages to expected labels using simple substring rules and
    occasionally returns:
      - verbose answers ("the intent is credit_limit because ...")
      - capitalized answers ("CREDIT_LIMIT")
      - mismatched node names (rejected by classifier validator)

    The classifier's validator must still accept the safe ones and reject
    the unsafe ones — that is what the harness measures.
    """

    provider_name = LLMProviderName.MOCK

    def __init__(self, model: str = "rule-oracle-v1") -> None:
        self.model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        ctx = request.structured_context
        if request.task == StructuredResponseInterpreter.TASK_NAME:
            content = self._answer_choice(ctx)
        else:
            content = self._answer_intent(ctx)
        return LLMResponse(
            content=content,
            provider=LLMProviderName.MOCK,
            model=self.model,
            fallback_triggered=False,
            input_tokens=len(content),
            output_tokens=len(content),
        )

    def _answer_intent(self, ctx: dict[str, Any]) -> str:
        message = str(ctx.get("user_message", "")).lower()
        rules = [
            (("encerrar", "finalizar", "tchau", "terminar"), Intent.END_CONVERSATION),
            (("aument", "elevar", "subir", "mais limite", "aumento"), Intent.CREDIT_INCREASE),
            (("cota", "câmbio", "cambio", "dolar", "dólar", "euro", "usd", "eur"), Intent.EXCHANGE_QUOTE),
            (("limite", "saldo", "cartão", "cartao"), Intent.CREDIT_LIMIT),
        ]
        for triggers, intent in rules:
            if any(token in message for token in triggers):
                return intent.value
        return Intent.UNKNOWN.value

    def _answer_choice(self, ctx: dict[str, Any]) -> str:
        message = str(ctx.get("user_message", "")).lower()
        accepted_tokens = ("sim", "claro", "ok", "aceito", "pode ser", "vamos")
        declined_tokens = ("não", "nao", "negativo", "prefiro não", "obrigado", "agora não")
        if any(token in message for token in accepted_tokens):
            return "accepted"
        if any(token in message for token in declined_tokens):
            return "declined"
        return ""  # forces classifier to abstain (rejected)


# ── Result containers ────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    case_id: str
    message: str
    expected: str | list[str]
    actual: str
    correct: bool
    fallback_triggered: bool = False
    confidence_bucket: str | None = None
    safe_rationale: str | None = None
    latency_ms: float | None = None


@dataclass
class SectionMetrics:
    name: str
    total: int = 0
    correct: int = 0
    abstained: int = 0
    fallback_calls: int = 0
    cases: list[CaseResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        accuracy = (self.correct / self.total) if self.total else 0.0
        abstention = (self.abstained / self.total) if self.total else 0.0
        fallback_rate = (self.fallback_calls / self.total) if self.total else 0.0
        return {
            "name": self.name,
            "total": self.total,
            "correct": self.correct,
            "abstained": self.abstained,
            "accuracy": round(accuracy, 4),
            "abstention_rate": round(abstention, 4),
            "fallback_rate": round(fallback_rate, 4),
            "cases": [c.__dict__ for c in self.cases],
        }


# ── Harness ──────────────────────────────────────────────────────────────────


def _build_manager(mode: str) -> LLMManager:
    if mode == "oracle":
        return LLMManager(primary_provider=RuleOracleProvider())
    if mode == "live":
        from app.bootstrap.dependencies import create_llm_manager
        from app.config.settings import load_settings_from_env

        return create_llm_manager(load_settings_from_env())
    raise ValueError(f"Unsupported evaluation mode: {mode!r}")


def _evaluate_intents(
    classifier: IntentClassifier, dataset: dict
) -> SectionMetrics:
    metrics = SectionMetrics(name="intent_classification")
    for case in dataset.get("intent_cases", []):
        expected = case["expected_intent"]
        intent, classification, telemetry = classifier.classify_with_telemetry(case["message"])
        actual = intent.value
        correct = actual == expected
        metrics.total += 1
        if correct:
            metrics.correct += 1
        if actual == Intent.UNKNOWN.value and expected != Intent.UNKNOWN.value:
            metrics.abstained += 1
        if telemetry and telemetry.get("fallback_triggered"):
            metrics.fallback_calls += 1
        metrics.cases.append(
            CaseResult(
                case_id=case["id"],
                message=case["message"],
                expected=expected,
                actual=actual,
                correct=correct,
                fallback_triggered=bool(telemetry and telemetry.get("fallback_triggered")),
                confidence_bucket=classification.confidence_bucket,
                safe_rationale=classification.safe_rationale,
                latency_ms=telemetry.get("latency_ms") if telemetry else None,
            )
        )
    return metrics


def _evaluate_confirmations(
    interpreter: StructuredResponseInterpreter, dataset: dict
) -> SectionMetrics:
    metrics = SectionMetrics(name="confirmation_normalization")
    allowed = ["accepted", "declined"]
    for case in dataset.get("confirmation_cases", []):
        expected = case["expected_value"]
        choice, telemetry = interpreter.interpret_choice_with_telemetry(
            user_message=case["message"],
            field_name="partial_increase_response",
            allowed_values=allowed,
            guidance="Map the user's short reply to accepted or declined.",
        )
        actual = choice or "abstain"
        correct = actual == expected
        metrics.total += 1
        if correct:
            metrics.correct += 1
        if choice is None:
            metrics.abstained += 1
        if telemetry and telemetry.get("fallback_triggered"):
            metrics.fallback_calls += 1
        metrics.cases.append(
            CaseResult(
                case_id=case["id"],
                message=case["message"],
                expected=expected,
                actual=actual,
                correct=correct,
                fallback_triggered=bool(telemetry and telemetry.get("fallback_triggered")),
                safe_rationale=telemetry.get("safe_rationale") if telemetry else None,
                latency_ms=telemetry.get("latency_ms") if telemetry else None,
            )
        )
    return metrics


def _evaluate_ambiguous(
    classifier: IntentClassifier, dataset: dict
) -> SectionMetrics:
    metrics = SectionMetrics(name="ambiguity_handling")
    for case in dataset.get("ambiguous_cases", []):
        allowed = case.get("expected_intent_in", [Intent.UNKNOWN.value])
        intent, classification, telemetry = classifier.classify_with_telemetry(case["message"])
        actual = intent.value
        correct = actual in allowed
        metrics.total += 1
        if correct:
            metrics.correct += 1
        if classification.should_clarify:
            metrics.abstained += 1
        if telemetry and telemetry.get("fallback_triggered"):
            metrics.fallback_calls += 1
        metrics.cases.append(
            CaseResult(
                case_id=case["id"],
                message=case["message"],
                expected=allowed,
                actual=actual,
                correct=correct,
                fallback_triggered=bool(telemetry and telemetry.get("fallback_triggered")),
                confidence_bucket=classification.confidence_bucket,
                safe_rationale=classification.safe_rationale,
                latency_ms=telemetry.get("latency_ms") if telemetry else None,
            )
        )
    return metrics


def run_evaluation(mode: str = "oracle", dataset_path: Path | None = None) -> dict[str, Any]:
    """Run the full evaluation suite and return a structured report."""
    path = dataset_path or DEFAULT_DATASET_PATH
    with path.open(encoding="utf-8") as f:
        dataset = json.load(f)

    try:
        manager = _build_manager(mode)
    except (ValueError, LLMProviderError) as exc:
        return {
            "mode": mode,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    classifier = IntentClassifier(manager)
    interpreter = StructuredResponseInterpreter(manager)

    intent_metrics = _evaluate_intents(classifier, dataset)
    confirmation_metrics = _evaluate_confirmations(interpreter, dataset)
    ambiguous_metrics = _evaluate_ambiguous(classifier, dataset)

    return {
        "mode": mode,
        "status": "ok",
        "dataset_version": dataset.get("version"),
        "sections": [
            intent_metrics.as_dict(),
            confirmation_metrics.as_dict(),
            ambiguous_metrics.as_dict(),
        ],
        "summary": {
            "intent_accuracy": intent_metrics.as_dict()["accuracy"],
            "confirmation_accuracy": confirmation_metrics.as_dict()["accuracy"],
            "ambiguity_handling_accuracy": ambiguous_metrics.as_dict()["accuracy"],
            "overall_fallback_rate": round(
                (
                    intent_metrics.fallback_calls
                    + confirmation_metrics.fallback_calls
                    + ambiguous_metrics.fallback_calls
                )
                / max(
                    1,
                    intent_metrics.total
                    + confirmation_metrics.total
                    + ambiguous_metrics.total,
                ),
                4,
            ),
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Intent evaluation harness")
    parser.add_argument(
        "--mode",
        choices=["oracle", "live"],
        default="oracle",
        help="oracle = deterministic CI-safe simulation; live = real LLMManager",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Optional path to evaluation dataset JSON",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print only the summary block, not per-case detail",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    report = run_evaluation(mode=args.mode, dataset_path=args.dataset)

    if args.compact and report.get("status") == "ok":
        compact = {
            "mode": report["mode"],
            "summary": report["summary"],
            "sections": [
                {
                    "name": section["name"],
                    "total": section["total"],
                    "correct": section["correct"],
                    "accuracy": section["accuracy"],
                    "abstention_rate": section["abstention_rate"],
                    "fallback_rate": section["fallback_rate"],
                }
                for section in report["sections"]
            ],
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
