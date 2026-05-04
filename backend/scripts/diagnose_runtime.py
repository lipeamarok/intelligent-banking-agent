"""Safe runtime diagnosis for backend settings/bootstrap graph availability."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.api import dependencies as api_dependencies
from app.bootstrap.dependencies import create_graph_dependencies
from app.bootstrap.graph import create_application_graph
from app.observability.logger import sanitize_text
from app.config.settings import load_settings_from_env


def _print_data_checks(data_dir: Path) -> None:
    print(f"data_dir_exists: {data_dir.exists() and data_dir.is_dir()}")
    for filename in (
        "clientes.csv",
        "score_limite.csv",
        "solicitacoes_aumento_limite.csv",
    ):
        print(f"{filename}_exists: {(data_dir / filename).exists()}")


def _safe_try_create_dependencies() -> None:
    settings = load_settings_from_env()
    try:
        create_graph_dependencies(settings=settings)
        print("create_graph_dependencies: OK")
    except Exception as exc:
        print(f"create_graph_dependencies: ERROR {type(exc).__name__}: {exc}")



def _safe_try_create_graph() -> None:
    settings = load_settings_from_env()
    try:
        create_application_graph(settings=settings)
        print("create_application_graph: OK")
    except Exception as exc:
        print(f"create_application_graph: ERROR {type(exc).__name__}: {exc}")



def _safe_try_get_app_graph() -> None:
    api_dependencies.clear_api_dependency_caches()
    graph = api_dependencies.get_app_graph()
    unavailable_type = getattr(api_dependencies, "_UnavailableGraph")
    if isinstance(graph, unavailable_type):
        print("get_app_graph: unavailable_fallback")
        print(f"get_app_graph_reason: {sanitize_text(graph.reason)}")
    else:
        print("get_app_graph: real_graph")



def main() -> int:
    settings = load_settings_from_env()
    summary = settings.safe_summary()
    cwd = Path(os.getcwd()).resolve()
    backend_root = Path(__file__).resolve().parents[1]
    data_dir_abs = (Path(settings.data_dir) if Path(settings.data_dir).is_absolute() else (backend_root / settings.data_dir)).resolve()

    print(f"pid: {os.getpid()}")
    print(f"python: {sys.executable}")
    print(f"cwd: {cwd}")
    print(f"backend_root: {backend_root}")
    print(summary)

    data_dir = Path(settings.data_dir)
    print(f"data_dir: {data_dir}")
    print(f"data_dir_absolute: {data_dir_abs}")
    _print_data_checks(data_dir_abs)

    _safe_try_create_dependencies()
    _safe_try_create_graph()
    _safe_try_get_app_graph()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
