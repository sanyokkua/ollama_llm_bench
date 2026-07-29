"""``MainWindowGateway`` -- a **deliberate duplicate** of ``ui/main_window/protocols.py``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.1.

``ui/main_window/protocols.py`` stays the source of truth for the shape: the Main
Window owns it, but ``adapters/*`` may not import ``ui/*`` (``import-linter``), so this
module's ``api.py`` cannot annotate ``make_main_window_gateway``'s return type with the
UI module's copy. This copy exists only so ``api.py`` has something to annotate. The
concrete ``_MainWindowGateway`` satisfies both structurally, with no import in either
direction. Any change to one must be mirrored in the other.

This duplicate resolves a contradiction inside ADR-0014 rather than applying it: the
ADR's decision item 2 requires each factory to return "the corresponding **UI-declared**
gateway Protocol type", while item 3 requires that ``adapters/ui_gateways/`` "declares no
gateway Protocol of its own" and never imports the UI module. Those two cannot both hold
-- annotating with the UI-declared type *is* importing the UI module. Item 3's layering
rule is the one with teeth (it is now enforced by the "Adapters never import the UI
layer" ``import-linter`` contract), so item 2 is satisfied structurally instead of
nominally, at the cost of item 3's "no Protocol of its own". A corrective ADR should
record that; ADR-0014 itself is accepted and so may no longer be edited in place
(``14_Process_and_Traceability/04_ADR_FORMAT.md`` §8).
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import AppReadinessSnapshot

__all__: list[str] = ["MainWindowGateway"]


class MainWindowGateway(Protocol):
    """Adapter gateway for the Main Window shell (D-R-06).

    Mirror of ``ui.main_window.protocols.MainWindowGateway`` -- see this module's
    docstring for why the declaration is duplicated.
    """

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
        """Trigger a readiness re-probe (on a worker thread) on a dot click.

        The parenthetical is §7b.1's wording and means only "not on the graphical
        thread". The batch itself is orchestrated on the pipeline-dispatcher thread,
        never on a ``TaskRunner`` worker: ``08-E`` §12 and
        ``16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a both name the
        readiness ``probe_all`` batch as dispatcher-thread work, because it fans leaf
        probes out to the pool and blocks on them -- and a pool thread waiting on pool
        threads is the forbidden submit-and-wait pattern (STORY-105-AC-2).
        """
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently active (non-terminal) -- the quit decision."""
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit (bounded wait)."""
        ...
