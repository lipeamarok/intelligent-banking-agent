"""
Admin-only endpoints for local development: CSV inspection and reset.

All routes in this module are protected by the `require_local_env` dependency
which returns HTTP 403 when APP_ENV != "local". This prevents accidental
exposure of raw CSV data or destructive resets in non-local deployments.
"""

from __future__ import annotations

import csv
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.config.settings import load_settings_from_env
from app.observability.logger import get_logger, log_event

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Allowed table identifiers (enum prevents path traversal) ─────────────────

class CsvTable(str, Enum):
    CLIENTES = "clientes"
    SCORE_LIMITE = "score_limite"
    SOLICITACOES = "solicitacoes"


_TABLE_FILES: dict[CsvTable, str] = {
    CsvTable.CLIENTES: "clientes.csv",
    CsvTable.SCORE_LIMITE: "score_limite.csv",
    CsvTable.SOLICITACOES: "solicitacoes_aumento_limite.csv",
}


# ── Dependency: only available in local env ───────────────────────────────────

def require_local_env() -> None:
    """Dependency that blocks access when APP_ENV != 'local'."""
    settings = load_settings_from_env()
    if settings.app_env != "local":
        raise HTTPException(
            status_code=403,
            detail={"error": "Admin endpoints are only available in the local environment."},
        )


# ── Data dir helper (mirrors main.py logic) ───────────────────────────────────

def _resolve_data_dir() -> Path:
    settings = load_settings_from_env()
    backend_root = Path(__file__).resolve().parents[2]
    data_dir = Path(settings.data_dir)
    if not data_dir.is_absolute():
        data_dir = (backend_root / data_dir).resolve()
    return data_dir


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/csv/{table}")
def get_csv_table(
    table: CsvTable,
    _env: None = Depends(require_local_env),
) -> dict:
    """Return the full contents of a CSV table as JSON rows."""
    data_dir = _resolve_data_dir()
    csv_path = data_dir / _TABLE_FILES[table]

    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": f"Table '{table.value}' not found. Run seed_data.py to initialize."},
        )

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        columns: list[str] = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = [dict(row) for row in reader]

    log_event(logger, "admin_csv_read", table=table.value, row_count=len(rows))
    return {"table": table.value, "columns": columns, "rows": rows}


@router.post("/csv/reset")
def reset_csv_data(
    _env: None = Depends(require_local_env),
) -> dict:
    """Reset all CSV tables to seed defaults (destructive — local only)."""
    from scripts.seed_data import get_default_data_dir, seed_runtime_data  # noqa: PLC0415

    data_dir = _resolve_data_dir()
    _, _, reset_files = seed_runtime_data(data_dir=data_dir, reset=True)
    log_event(logger, "admin_csv_reset", reset_files=reset_files)
    return {"reset": True, "tables": reset_files}
