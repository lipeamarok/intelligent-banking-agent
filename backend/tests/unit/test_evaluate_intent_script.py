"""Smoke test for the intent evaluation harness (oracle mode)."""

from pathlib import Path

from scripts.evaluate_intent import run_evaluation


def test_run_evaluation_oracle_mode_produces_report():
    report = run_evaluation(mode="oracle")
    assert report["status"] == "ok"
    assert report["mode"] == "oracle"

    sections = {s["name"]: s for s in report["sections"]}
    assert "intent_classification" in sections
    assert "confirmation_normalization" in sections
    assert "ambiguity_handling" in sections

    # Each section must have run at least one case.
    for section in sections.values():
        assert section["total"] >= 1
        # Accuracy must be a finite ratio in [0, 1].
        assert 0.0 <= section["accuracy"] <= 1.0
        assert 0.0 <= section["abstention_rate"] <= 1.0
        assert 0.0 <= section["fallback_rate"] <= 1.0


def test_run_evaluation_oracle_intent_accuracy_is_high():
    """The oracle provider is permissive enough that intent accuracy must be
    well above random for a 6-class problem."""
    report = run_evaluation(mode="oracle")
    summary = report["summary"]
    assert summary["intent_accuracy"] >= 0.80
    assert summary["confirmation_accuracy"] >= 0.80


def test_run_evaluation_with_explicit_dataset_path():
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "intent_eval_dataset.json"
    )
    report = run_evaluation(mode="oracle", dataset_path=path)
    assert report["status"] == "ok"
