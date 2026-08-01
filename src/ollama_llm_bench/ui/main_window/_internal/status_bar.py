"""``StatusBarWidget`` -- the persistent status bar (STORY-053, STORY-077 Fix 2).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §2, §4. Hosts
``ui.shared.make_health_dot`` for the left health region, a centre toast label, and a
trailing version label. A passive view: ``apply_view_model(view_model)`` is its only
state-changing entry point; it never imports a Gateway, an ``EventBus``, or a backend
service symbol.

**Resolved deviation (see the ``ui/main_window`` package docstring / ``api.py``).** The
health dot must repaint live on theme change, including the CHECKING-state pulse (08-D §6),
so this widget takes an explicit ``theme_manager``/``platform_kind`` pair rather than a
global/singleton accessor, matching every other themed custom-painted primitive in this
codebase.

**Subclasses the real ``QStatusBar`` (STORY-077 Fix 2), not a plain ``QWidget``.** The
application must have exactly one status-bar object (§2): this same instance is handed to
both ``MainWindowShell.setStatusBar`` and
``adapters.notification_service.make_notification_service`` by ``compose.py``, so
``NotificationService``'s native ``QStatusBar.showMessage`` toasts render in the one bar
that also holds the health dot and the version label, instead of a second, disconnected
``QStatusBar``. The three regions are mounted as a single **permanent** widget
(``addPermanentWidget``) so they stay visible even while a native temporary message is
showing -- ``QStatusBar`` hides only its non-permanent widgets during a temporary message.
"""

from typing import Final, override

from PySide6.QtCore import QEvent, QObject, Signal as QtSignal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from ollama_llm_bench.backend.domain import ReadinessState
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel
from ollama_llm_bench.ui.shared import make_health_dot
from ollama_llm_bench.ui.theme import HealthDisplayState, PlatformKind, ThemeManager

__all__: list[str] = ["StatusBarWidget"]

_STATUS_BAR_HEIGHT = 22

_HEALTH_DISPLAY_STATE_BY_READINESS: Final[dict[ReadinessState, HealthDisplayState]] = {
    ReadinessState.READY: HealthDisplayState.LIVE,
    ReadinessState.DEGRADED: HealthDisplayState.REACHABLE_NO_MODELS,
    ReadinessState.NOT_READY: HealthDisplayState.DOWN,
    ReadinessState.CHECKING: HealthDisplayState.CHECKING,
}
_HEALTH_LABEL_BY_DISPLAY_STATE: Final[dict[HealthDisplayState, str]] = {
    HealthDisplayState.LIVE: "Ready",
    HealthDisplayState.REACHABLE_NO_MODELS: "Degraded",
    HealthDisplayState.DOWN: "Not ready",
    HealthDisplayState.CHECKING: "Checking",
}


def _map_readiness_to_health_display(state: ReadinessState) -> HealthDisplayState:
    """Map the backend ``ReadinessState`` to the theme module's display-state enum (§4.1)."""
    return _HEALTH_DISPLAY_STATE_BY_READINESS[state]


class StatusBarWidget(QStatusBar):
    """The Main Window's one status bar: health dot, toast region, version (§2, §4)."""

    health_dot_clicked = QtSignal()

    def __init__(
        self, *, theme_manager: ThemeManager, platform_kind: PlatformKind, app_version: str
    ) -> None:
        """Build the status bar's three fixed regions.

        Args:
            theme_manager: The live theme switcher the health dot re-reads its colour
                role from on every theme change.
            platform_kind: The host platform classification the health dot resolves
                alongside ``theme_manager``.
            app_version: The version string shown in the trailing version label.
        """
        super().__init__()
        # Attribute init MUST precede every native `QStatusBar` call below (STORY-077
        # Fix 2 regression): unlike a plain `QWidget`, `QStatusBar.setSizeGripEnabled`
        # touches an internal child `QSizeGrip` and can synchronously redeliver a stale
        # queued event to this object's overridden `eventFilter` before construction
        # finishes -- `eventFilter` must find `self._health_dot` already set.
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._health_dot: QWidget | None = None
        self.setObjectName("status_bar")
        self.setFixedHeight(_STATUS_BAR_HEIGHT)
        self.setSizeGripEnabled(False)
        self._health_container = QWidget()
        self._health_container.setObjectName("health_region")
        self._health_layout = QHBoxLayout(self._health_container)
        self._health_layout.setContentsMargins(0, 0, 0, 0)
        self._toast_label = QLabel()
        self._toast_label.setObjectName("toast_label")
        self._version_label = QLabel(f"v{app_version}")
        self._version_label.setObjectName("status_bar_version_label")

        regions = QWidget()
        regions.setObjectName("status_bar_regions")
        regions_layout = QHBoxLayout(regions)
        regions_layout.setContentsMargins(0, 0, 0, 0)
        regions_layout.addWidget(self._health_container)
        regions_layout.addWidget(self._toast_label, 1)
        regions_layout.addWidget(self._version_label)
        self.addPermanentWidget(regions, 1)

    def apply_view_model(self, view_model: MainWindowViewModel) -> None:
        """Reflect ``view_model`` in the health dot and the toast label.

        Named ``apply_view_model`` rather than ``render`` -- ``QWidget`` already declares
        an incompatible ``render(...)`` method (offscreen painting).
        """
        self._rebuild_health_dot(view_model)
        self._toast_label.setText(view_model.toast_text)

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # Qt override
        """Forward every click on the health dot as ``health_dot_clicked`` (§4.2).

        This view never decides reprobe-vs-toast itself -- the dot has no native
        disabled visual state, so every click is forwarded unconditionally and the
        *controller* is the one that reads ``health_dot_clickable`` to choose between
        triggering a re-probe and showing the "disabled" toast (matching "click is
        ignored, toast appears" rather than greying out a custom-painted widget).
        """
        if watched is self._health_dot and event.type() == QEvent.Type.MouseButtonPress:
            self.health_dot_clicked.emit()
            return True
        return super().eventFilter(watched, event)

    def _rebuild_health_dot(self, view_model: MainWindowViewModel) -> None:
        if self._health_dot is not None:
            self._health_layout.removeWidget(self._health_dot)
            self._health_dot.removeEventFilter(self)
            self._health_dot.deleteLater()
        display_state = _map_readiness_to_health_display(view_model.health_state)
        dot = make_health_dot(
            state=display_state,
            text=_HEALTH_LABEL_BY_DISPLAY_STATE[display_state],
            theme_manager=self._theme_manager,
            platform_kind=self._platform_kind,
        )
        dot.setToolTip(view_model.health_tooltip)
        dot.installEventFilter(self)
        self._health_layout.addWidget(dot)
        self._health_dot = dot
