"""``QtWorkspaceController`` — the concrete workspace-switch coordinator.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§19 (Workspace Controller) and
``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` §9.1
(``WorkspaceChangedEvent``).

This is a plain-Python coordinator, not a ``QObject`` — it never owns a Qt ``Signal`` and so
carries no risk of the ``emit``-name Shiboken pitfall (``pyside6-app-development.md``). It
holds the ``WorkspaceStore`` (state of record for the active workspace) and the ``EventBus``
(the ``_workspace_changed`` announcement channel), plus the ``QStackedWidget`` container and
the per-workspace widget factories registered by ``compose.py``. Each destination widget is
constructed at most once, on first ``switch_to``, and retained thereafter.
"""

from collections.abc import Callable, Mapping
from typing import Protocol, cast, runtime_checkable

from PySide6.QtWidgets import QStackedWidget, QWidget

from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.events import (
    SIGNAL_WORKSPACE_CHANGED,
    EventBus,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.backend.stores import WorkspaceStore

__all__: list[str] = ["QtWorkspaceController"]


@runtime_checkable
class _SupportsOpenPaths(Protocol):
    """Forward-compatible hook for a workspace widget that can pre-open files.

    No shipped workspace widget implements this yet (STORY-045 out of scope);
    ``QtWorkspaceController`` forwards ``WorkspaceHint.open_paths`` only when
    the shown widget happens to satisfy this shape.
    """

    def open_paths(self, paths: tuple[str, ...]) -> None:
        """Pre-open the given file paths in the workspace widget."""
        ...


class QtWorkspaceController:
    """Coordinates the switch between the benchmark and task-editor workspaces.

    Holds the ``WorkspaceStore`` (state of record), the ``EventBus``
    (``_workspace_changed`` announcements), the ``QStackedWidget`` container
    the two workspace widgets are shown in, and the lazy per-workspace widget
    factories registered by ``compose.py``.
    """

    def __init__(
        self,
        *,
        workspace_store: WorkspaceStore,
        event_bus: EventBus,
        container: QStackedWidget,
        workspace_factories: Mapping[str, Callable[[], QWidget]],
    ) -> None:
        """Store the collaborators and factories this controller coordinates.

        Args:
            workspace_store: The reactive store holding the active workspace
                name.
            event_bus: The bus this controller emits ``_workspace_changed``
                on.
            container: The stacked-widget region the two workspace widgets
                are shown in.
            workspace_factories: One zero-argument widget factory per
                workspace name, keyed by ``"benchmark"``/``"task_editor"``.
        """
        self._workspace_store = workspace_store
        self._event_bus = event_bus
        self._container = container
        self._workspace_factories = workspace_factories
        self._widgets: dict[str, QWidget] = {}

    def active(self) -> str:
        """Return the currently active workspace name.

        Returns:
            ``"benchmark"`` or ``"task_editor"``, read straight from the
            ``WorkspaceStore``.
        """
        return self._workspace_store.active_workspace()

    def switch_to(self, name: str, hint: WorkspaceHint | None = None) -> None:
        """Switch to the named workspace, applying the optional hint.

        A same-workspace call is a no-op: no widget is (re-)constructed and
        no ``_workspace_changed`` event is emitted (AC-4). Otherwise the
        destination widget is built at most once (AC-1), the store is
        updated and exactly one event is emitted (AC-2), the shown widget
        has its theme reapplied and the hint applied (AC-3).

        Args:
            name: The destination workspace — ``"benchmark"`` or
                ``"task_editor"``.
            hint: Optional guidance applied after the switch completes.

        Raises:
            ContractViolationError: ``name`` is not a registered workspace —
                the name is a code constant, never user input, so this is a
                programmer error.
        """
        if name not in self._workspace_factories:
            raise ContractViolationError(
                message=(
                    f"invalid workspace name {name!r}; must be one of "
                    f"{sorted(self._workspace_factories)}"
                )
            )
        if name == self._workspace_store.active_workspace():
            return

        previous = self._workspace_store.active_workspace()
        widget = self._widget_for(name)
        self._workspace_store.set_active_workspace(name)
        self._show(self._container, widget)
        self._apply_hint(widget, hint)
        self._event_bus.emit(
            SIGNAL_WORKSPACE_CHANGED,
            WorkspaceChangedEvent(workspace=name, previous_workspace=previous),
        )

    def _widget_for(self, name: str) -> QWidget:
        """Return the cached widget for ``name``, building it on first use."""
        if name not in self._widgets:
            widget = self._workspace_factories[name]()
            self._container.addWidget(widget)
            self._widgets[name] = widget
        return self._widgets[name]

    @staticmethod
    def _show(container: QStackedWidget, widget: QWidget) -> None:
        """Show ``widget`` in ``container`` and force a style re-polish.

        Style re-application uses the generic Qt idiom
        (``unpolish``/``polish``/``update``) rather than a call into
        ``ui/theme/`` — this module's dependency set excludes ``ui/*``
        (``01_MODULE_INVENTORY.md`` §5).
        """
        container.setCurrentWidget(widget)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    @staticmethod
    def _apply_hint(widget: QWidget, hint: WorkspaceHint | None) -> None:
        """Apply an optional focus/pre-open-paths hint to the shown widget."""
        if hint is None:
            return
        if hint.focus_widget is not None:
            # PySide6-stubs' `findChild` return type is solved from an unconstrained
            # TypeVar (bound only via the runtime `type` argument, not `type[T]`), so
            # mypy cannot infer it as `QWidget | None` here; cast to the real contract.
            focused = cast("QWidget | None", widget.findChild(QWidget, hint.focus_widget))
            if focused is not None:
                focused.setFocus()
        if hint.open_paths and isinstance(widget, _SupportsOpenPaths):
            widget.open_paths(hint.open_paths)
