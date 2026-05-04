"""Graph bootstrap factory using centralized settings/dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bootstrap.dependencies import create_graph_dependencies
from app.config.settings import Settings
from app.graph.graph_builder import build_graph


def create_application_graph(
    settings: Settings,
    data_dir: Path | str | None = None,
    llm_http_client: Any = None,
    exchange_http_client: Any = None,
    checkpointer: Any = None,
    interrupt_before: list[str] | None = None,
):
    """Create compiled LangGraph app graph with bootstrap-wired dependencies."""
    deps = create_graph_dependencies(
        settings=settings,
        data_dir=data_dir,
        llm_http_client=llm_http_client,
        exchange_http_client=exchange_http_client,
    )
    return build_graph(
        deps,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
