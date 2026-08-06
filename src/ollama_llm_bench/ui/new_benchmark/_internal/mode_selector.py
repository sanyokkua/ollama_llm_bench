"""``ModeSelectorWidget`` -- the three-mode radio list (STORY-054-AC-1).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §3. Fixed display order
Synthetic -> Task -> Graded; persistence of ``benchmark.last_mode`` is the caller's
(controller's) responsibility via ``set_mode``/``mode_changed`` -- this widget holds
no Gateway itself (D-R-06; passive-View rule).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QRadioButton, QVBoxLayout, QWidget

from ollama_llm_bench.backend.domain import RunMode

__all__: list[str] = ["ModeSelectorWidget"]

_DISPLAY_ORDER: tuple[RunMode, ...] = (RunMode.SYNTHETIC, RunMode.TASKS, RunMode.GRADED)
_CAPTIONS: dict[RunMode, tuple[str, str]] = {
    RunMode.SYNTHETIC: ("Synthetic Benchmark", "Synthetic prompt sizes; measures throughput"),
    RunMode.TASKS: ("Task Benchmark", "Your task files; throughput only; no grading"),
    RunMode.GRADED: ("Graded Benchmark", "Your task files; full grading pipeline"),
}


class ModeSelectorWidget(QWidget):
    """The mode radio list; emits ``mode_changed`` only on a genuine user selection."""

    mode_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.mode_selector")
        self._buttons: dict[RunMode, QRadioButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._suppress_signal = False
        self._build_ui()
        self._group.buttonToggled.connect(self._on_button_toggled)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        for mode in _DISPLAY_ORDER:
            title, caption = _CAPTIONS[mode]
            button = QRadioButton(f"{title}\n{caption}")
            button.setObjectName(f"new_benchmark.mode_selector.{mode.value}")
            button.setAccessibleName(f"{title}: {caption}")
            button.setProperty("role", "mode-selector-row")
            self._group.addButton(button)
            self._buttons[mode] = button
            layout.addWidget(button)

    @property
    def selected_mode(self) -> RunMode:
        """The currently selected ``RunMode``."""
        for mode, button in self._buttons.items():
            if button.isChecked():
                return mode
        raise AssertionError("no mode radio button is checked -- construction invariant broken")

    def set_mode(self, mode: RunMode) -> None:
        """Select ``mode`` programmatically without emitting ``mode_changed``.

        Used by the controller to apply the persisted ``benchmark.last_mode`` value
        once at construction, before any user interaction.
        """
        self._suppress_signal = True
        try:
            self._buttons[mode].setChecked(True)
        finally:
            self._suppress_signal = False

    def select_mode_for_test(self, mode: RunMode) -> None:
        """Test helper: simulate a user click selecting ``mode`` (emits the signal)."""
        self._buttons[mode].setChecked(True)

    def _on_button_toggled(self, button: QRadioButton, checked: bool) -> None:  # noqa: FBT001,ARG002  # Qt signal callback
        if not checked or self._suppress_signal:
            return
        self.mode_changed.emit(self.selected_mode)
