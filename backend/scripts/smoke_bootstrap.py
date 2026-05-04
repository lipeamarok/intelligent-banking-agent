"""Local smoke for bootstrap wiring without executing external API calls."""

from __future__ import annotations

import csv
from pathlib import Path

from app.bootstrap.dependencies import create_graph_dependencies
from app.config.settings import load_settings_from_env

_REQUIRED_HEADERS = {
    "clientes.csv": [
        "cpf",
        "data_nascimento",
        "nome",
        "score_atual",
        "limite_credito",
    ],
    "score_limite.csv": [
        "score_minimo",
        "score_maximo",
        "limite_maximo_permitido",
    ],
    "solicitacoes_aumento_limite.csv": [
        "cpf_cliente",
        "data_hora_solicitacao",
        "limite_atual",
        "novo_limite_solicitado",
        "status_pedido",
    ],
}


def validate_runtime_csv_data(data_dir: Path) -> None:
    """Validate required CSV files and minimum header shape for local runtime."""
    if not data_dir.exists() or not data_dir.is_dir():
        raise ValueError(f"Missing data directory: {data_dir}")

    missing_files = [name for name in _REQUIRED_HEADERS if not (data_dir / name).exists()]
    if missing_files:
        raise ValueError(f"Missing required data files: {', '.join(missing_files)}")

    for filename, expected_header in _REQUIRED_HEADERS.items():
        csv_path = data_dir / filename
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)

        if header is None:
            raise ValueError(f"Missing header row in {filename}")
        if list(header) != expected_header:
            raise ValueError(
                f"Invalid header in {filename}: expected {expected_header}, got {header}"
            )


def main() -> int:
    settings = load_settings_from_env()
    print(settings.safe_summary())

    data_dir = Path(settings.data_dir)
    print(f"Using data_dir: {data_dir}")

    try:
        validate_runtime_csv_data(data_dir)
    except ValueError as exc:
        print(f"Bootstrap smoke failed data validation: {exc}")
        return 1

    if not (settings.xai_api_key and settings.openai_api_key and settings.exchange_api_key):
        print("Bootstrap smoke passed local CSV validation; skipped provider creation because required keys are missing.")
        return 0

    create_graph_dependencies(settings=settings)
    print("GraphDependencies created successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
