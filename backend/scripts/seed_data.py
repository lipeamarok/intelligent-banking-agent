"""Create/reset local CSV seed data for Banco Agil runtime."""

from __future__ import annotations

import argparse
from pathlib import Path

CLIENTES_SEED = """cpf,data_nascimento,nome,score_atual,limite_credito
12345678901,1990-05-12,Ana Silva,720,5000.00
98765432100,1985-10-03,Carlos Souza,580,2500.00
45678912300,1998-02-20,Marina Costa,830,12000.00
"""

SCORE_LIMITE_SEED = """score_minimo,score_maximo,limite_maximo_permitido
0,299,1000.00
300,499,2500.00
500,699,5000.00
700,849,10000.00
850,1000,20000.00
"""

SOLICITACOES_SEED = """cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido
"""

SEED_FILES = {
    "clientes.csv": CLIENTES_SEED,
    "score_limite.csv": SCORE_LIMITE_SEED,
    "solicitacoes_aumento_limite.csv": SOLICITACOES_SEED,
}


def get_default_data_dir() -> Path:
    """Return canonical runtime data dir relative to backend root."""
    return Path(__file__).resolve().parents[1] / "app" / "data"


def seed_runtime_data(data_dir: Path, reset: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Create or reset required runtime CSV files deterministically."""
    data_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    preserved: list[str] = []
    reset_files: list[str] = []

    for filename, content in SEED_FILES.items():
        target = data_dir / filename
        if reset:
            target.write_text(content, encoding="utf-8")
            reset_files.append(filename)
            continue

        if target.exists():
            preserved.append(filename)
            continue

        target.write_text(content, encoding="utf-8")
        created.append(filename)

    return created, preserved, reset_files


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create/reset local CSV seed data")
    parser.add_argument("--reset", action="store_true", help="Overwrite all required CSV files with deterministic seed")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    data_dir = get_default_data_dir()

    created, preserved, reset_files = seed_runtime_data(data_dir=data_dir, reset=args.reset)

    print(f"data_dir: {data_dir}")
    print(f"files_created: {created}")
    print(f"files_preserved: {preserved}")
    print(f"files_reset: {reset_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
