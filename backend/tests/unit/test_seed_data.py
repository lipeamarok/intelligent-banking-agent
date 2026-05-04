"""Unit tests for seed_data and smoke CSV validation helpers."""

from __future__ import annotations

from scripts.seed_data import SEED_FILES, seed_runtime_data
from scripts.smoke_bootstrap import validate_runtime_csv_data


def test_seed_data_creates_required_files(tmp_path):
    created, preserved, reset_files = seed_runtime_data(tmp_path, reset=False)

    assert set(created) == set(SEED_FILES)
    assert preserved == []
    assert reset_files == []

    for filename, expected_content in SEED_FILES.items():
        path = tmp_path / filename
        assert path.exists()
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == expected_content.splitlines()[0]


def test_seed_data_uses_canonical_score_limit_header(tmp_path):
    seed_runtime_data(tmp_path, reset=True)
    header = (tmp_path / "score_limite.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "score_minimo,score_maximo,limite_maximo_permitido"


def test_seed_data_preserves_existing_files_without_reset(tmp_path):
    custom = tmp_path / "clientes.csv"
    custom.write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "99999999999,2001-01-01,Custom User,700,9000.00\n",
        encoding="utf-8",
    )

    created, preserved, reset_files = seed_runtime_data(tmp_path, reset=False)

    assert "clientes.csv" in preserved
    assert "clientes.csv" not in created
    assert reset_files == []
    assert "Custom User" in custom.read_text(encoding="utf-8")


def test_seed_data_reset_overwrites_files(tmp_path):
    custom = tmp_path / "clientes.csv"
    custom.write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "99999999999,2001-01-01,Custom User,700,9000.00\n",
        encoding="utf-8",
    )

    created, preserved, reset_files = seed_runtime_data(tmp_path, reset=True)

    assert created == []
    assert preserved == []
    assert set(reset_files) == set(SEED_FILES)
    assert "Custom User" not in custom.read_text(encoding="utf-8")


def test_smoke_bootstrap_validation_fails_when_csv_missing(tmp_path):
    (tmp_path / "clientes.csv").write_text(SEED_FILES["clientes.csv"], encoding="utf-8")

    try:
        validate_runtime_csv_data(tmp_path)
    except ValueError as exc:
        assert "Missing required data files" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing required CSV files")
