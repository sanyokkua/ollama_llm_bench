"""``MenuBarWidget`` -- the minimal in-window menu bar (STORY-053).

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §3. Deliberately
has no ``QMenuBar``/dropdown menus (the spec forbids File/Edit/View/Help). A passive view:
``apply_view_model(view_model)`` is its only state-changing entry point; it imports no
Gateway, no ``EventBus``, and no backend symbol.
"""

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget

from ollama_llm_bench.ui.main_window.models import MainWindowViewModel

__all__: list[str] = ["MenuBarWidget"]

_MENU_BAR_HEIGHT = 32
_MIN_CLICK_TARGET_PX: Final = 24  # 08_ACCESSIBILITY_FLOOR.md §6 -- 24px click-target floor
_DISABLED_SETTINGS_TOOLTIP: Final = "Disabled - a benchmark is in progress."
_SETTINGS_TOOLTIP: Final = "Open the Settings dialog"
_ABOUT_TOOLTIP: Final = "Application information: version, links, data folders"
_BENCHMARK_WORKSPACE_LABEL: Final = "Benchmark workspace"
_TASK_EDITOR_WORKSPACE_LABEL: Final = "Task Editor workspace"
_RUNNING_PILL_ACCESSIBLE_NAME: Final = "Run in progress — open Progress"
_RUNNING_PILL_TOOLTIP: Final = "Switch to the Benchmark workspace and focus the Progress widget"


class _WorkspaceSwitcherWidget(QWidget):
    """The two-segment ``Benchmark`` / ``Task Editor`` switcher (§3.3)."""

    segment_activated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("workspace_switcher")
        self._benchmark_button = QPushButton("Benchmark")
        self._benchmark_button.setObjectName("workspace_benchmark_button")
        self._benchmark_button.setAccessibleName(_BENCHMARK_WORKSPACE_LABEL)
        self._benchmark_button.setToolTip(_BENCHMARK_WORKSPACE_LABEL)
        self._benchmark_button.setCheckable(True)
        self._benchmark_button.setProperty("role", "segmented-control")
        self._task_editor_button = QPushButton("Task Editor")
        self._task_editor_button.setObjectName("workspace_task_editor_button")
        self._task_editor_button.setAccessibleName(_TASK_EDITOR_WORKSPACE_LABEL)
        self._task_editor_button.setToolTip(_TASK_EDITOR_WORKSPACE_LABEL)
        self._task_editor_button.setCheckable(True)
        self._task_editor_button.setProperty("role", "segmented-control")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.addButton(self._benchmark_button)
        self._group.addButton(self._task_editor_button)
        # 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md §6 (24x24 click target). A nested
        # QWidget inside the menu bar's QHBoxLayout raises that layout's minimum height by
        # 12px over its tallest child, so the bar's spec-fixed 32px (01_Main_Window §2) is
        # 4px short of the 36px the layout asks for; Qt resolves the shortfall by shrinking
        # this nested branch -- and only this branch -- to 20px, taking both buttons with it.
        # An explicit minimum is honoured strictly, so the segments keep the floor inside the
        # 32px bar. Measured: without it 77x20, with it 77x24.
        self.setMinimumHeight(_MIN_CLICK_TARGET_PX)
        self._benchmark_button.setChecked(True)
        self._benchmark_button.clicked.connect(self._on_benchmark_clicked)
        self._task_editor_button.clicked.connect(self._on_task_editor_clicked)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._benchmark_button)
        layout.addWidget(self._task_editor_button)

    def set_active(self, name: str) -> None:
        """Reflect ``name`` as the checked segment, without emitting a signal."""
        if name == "task_editor":
            self._task_editor_button.setChecked(True)
        else:
            self._benchmark_button.setChecked(True)

    def _on_benchmark_clicked(self) -> None:
        self.segment_activated.emit("benchmark")

    def _on_task_editor_clicked(self) -> None:
        self.segment_activated.emit("task_editor")


class MenuBarWidget(QWidget):
    """The Main Window's in-window menu bar: Settings, About, switcher, pill, version."""

    settings_requested = Signal()
    about_requested = Signal()
    workspace_switch_requested = Signal(str)
    running_pill_clicked = Signal()

    def __init__(self, *, app_version: str) -> None:
        """Build the menu bar's fixed left-to-right layout (§3).

        Args:
            app_version: The version string shown in the trailing version label.
        """
        super().__init__()
        self.setObjectName("menu_bar")
        self.setFixedHeight(_MENU_BAR_HEIGHT)
        self._settings_action = QPushButton("Settings")
        self._settings_action.setObjectName("settings_menu_button")
        self._settings_action.setAccessibleName("Settings")
        self._settings_action.setToolTip(_SETTINGS_TOOLTIP)
        self._settings_action.setProperty("role", "menu-action")
        self._settings_action.clicked.connect(self.settings_requested)
        self._about_action = QPushButton("About")
        self._about_action.setObjectName("about_menu_button")
        self._about_action.setAccessibleName("About")
        self._about_action.setToolTip(_ABOUT_TOOLTIP)
        self._about_action.setProperty("role", "menu-action")
        self._about_action.clicked.connect(self.about_requested)
        self._workspace_switcher = _WorkspaceSwitcherWidget()
        self._workspace_switcher.segment_activated.connect(self.workspace_switch_requested)
        self._running_pill = QPushButton()
        self._running_pill.setObjectName("running_pill_button")
        self._running_pill.setAccessibleName(_RUNNING_PILL_ACCESSIBLE_NAME)
        self._running_pill.setToolTip(_RUNNING_PILL_TOOLTIP)
        self._running_pill.setProperty("role", "running-pill")
        self._running_pill.clicked.connect(self.running_pill_clicked)
        self._running_pill.setVisible(False)
        self._version_label = QLabel(f"v{app_version}")
        self._version_label.setObjectName("menu_bar_version_label")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._settings_action)
        layout.addWidget(self._about_action)
        layout.addWidget(self._workspace_switcher)
        layout.addStretch(1)
        layout.addWidget(self._running_pill)
        layout.addWidget(self._version_label)

    def apply_view_model(self, view_model: MainWindowViewModel) -> None:
        """Reflect ``view_model`` in every menu-bar control (the widget's only mutator).

        Named ``apply_view_model`` rather than ``render`` -- ``QWidget`` already declares
        a ``render(...)`` method (offscreen painting to a ``QPainter``/``QPaintDevice``)
        that this method must not shadow with an incompatible signature.
        """
        self._settings_action.setEnabled(view_model.settings_action_enabled)
        self._settings_action.setToolTip(
            _SETTINGS_TOOLTIP if view_model.settings_action_enabled else _DISABLED_SETTINGS_TOOLTIP
        )
        self._running_pill.setVisible(view_model.running_pill_visible)
        self._running_pill.setText(view_model.running_pill_label)
        self._workspace_switcher.set_active(view_model.active_workspace)
