"""``MainWindowGateway`` -- the adapter gateway backing the Main Window shell (D-R-06).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.1. Declared locally, verbatim from the spec, per ``protocol-first-interfaces`` --
``ui/main_window/`` is the declared public entry point that consumes it
(``01_MODULE_INVENTORY.md``). Wraps ``SettingsService`` (window-shell persistence keys),
``ReadinessService`` (status-bar health dot), and ``BenchmarkFlowApi`` (the quit decision
and graceful shutdown) so this shell never holds a backend Protocol directly.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import AppReadinessSnapshot

__all__: list[str] = ["MainWindowGateway"]


class MainWindowGateway(Protocol):
    """Adapter gateway for the Main Window shell (D-R-06)."""

    def get_window_geometry(self) -> str | None:
        """Read the persisted ``ui.window_geometry`` blob, or ``None`` if unset."""
        ...

    def set_window_geometry(self, value: str) -> None:
        """Persist the ``ui.window_geometry`` blob (debounced by the caller)."""
        ...

    def get_splitter_sizes(self) -> str | None:
        """Read the persisted ``ui.splitter_sizes``, or ``None`` if unset."""
        ...

    def set_splitter_sizes(self, value: str) -> None:
        """Persist ``ui.splitter_sizes``."""
        ...

    def get_active_workspace(self) -> str | None:
        """Read the persisted ``ui.active_workspace`` (``"benchmark"``/``"task_editor"``)."""
        ...

    def set_active_workspace(self, value: str) -> None:
        """Persist ``ui.active_workspace``."""
        ...

    def get_theme(self) -> str:
        """Read the resolved ``ui.theme`` setting."""
        ...

    def set_theme(self, value: str) -> None:
        """Persist ``ui.theme``."""
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the status-bar dot."""
        ...

    def reprobe(self) -> None:
        """Trigger a readiness re-probe (on a worker thread) on a dot click."""
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently active (non-terminal) -- the quit decision."""
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit (bounded wait)."""
        ...
