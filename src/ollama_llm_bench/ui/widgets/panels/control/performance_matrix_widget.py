"""Performance Matrix widget — visible only in System Benchmark mode."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import PromptInputSize, PromptOutputSize
from ollama_llm_bench.backend.core.performance_prompts import (
    INPUT_SIZE_DESCRIPTIONS,
    OUTPUT_SIZE_DESCRIPTIONS,
)

_logger = logging.getLogger(__name__)

_DEFAULT_REPEAT_COUNT = 3
_MIN_REPEAT_COUNT = 1
_MAX_REPEAT_COUNT = 20

_INPUT_SIZE_LABELS: dict[PromptInputSize, str] = INPUT_SIZE_DESCRIPTIONS
_OUTPUT_SIZE_LABELS: dict[PromptOutputSize, str] = OUTPUT_SIZE_DESCRIPTIONS


class PerformanceMatrixWidget(QWidget):
    """Matrix of input/output size checkboxes and a repeat count for System Benchmark mode.

    State is preserved when the widget is hidden; nothing resets on visibility change.
    """

    def __init__(self, *, parent: QWidget | None = None) -> None:
        """Initialize the widget with default checkbox selections and repeat count.

        Args:
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)

        self._input_checks: dict[PromptInputSize, QCheckBox] = {
            size: QCheckBox(label) for size, label in _INPUT_SIZE_LABELS.items()
        }
        self._output_checks: dict[PromptOutputSize, QCheckBox] = {
            size: QCheckBox(label) for size, label in _OUTPUT_SIZE_LABELS.items()
        }
        self._repeat_spinbox = QSpinBox()
        self._repeat_spinbox.setToolTip(
            "Number of times each model is tested per task. Higher values produce more reliable averages"
            " but increase total benchmark time. Takes effect on the next run."
        )

        self._configure_widgets()
        self._build_layout()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _configure_widgets(self) -> None:
        self._repeat_spinbox.setRange(_MIN_REPEAT_COUNT, _MAX_REPEAT_COUNT)
        self._repeat_spinbox.setValue(_DEFAULT_REPEAT_COUNT)
        self._repeat_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)

    def _build_layout(self) -> None:
        # Input sizes group
        input_layout = QVBoxLayout()
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(4)
        for cb in self._input_checks.values():
            input_layout.addWidget(cb)
        input_group = QGroupBox("Input Sizes")
        input_group.setLayout(input_layout)

        # Output sizes group
        output_layout = QVBoxLayout()
        output_layout.setContentsMargins(4, 4, 4, 4)
        output_layout.setSpacing(4)
        for cb in self._output_checks.values():
            output_layout.addWidget(cb)
        output_group = QGroupBox("Output Sizes")
        output_group.setLayout(output_layout)

        # Repeats row
        repeat_row = QHBoxLayout()
        repeat_row.setContentsMargins(0, 0, 0, 0)
        repeat_row.setSpacing(8)
        repeat_row.addWidget(QLabel("Repeats:"))
        repeat_row.addWidget(self._repeat_spinbox)
        repeat_row.addStretch()

        # Outer layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        outer.addWidget(input_group)
        outer.addWidget(output_group)
        outer.addLayout(repeat_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_input_sizes(self) -> list[PromptInputSize]:
        """Return all input sizes whose checkbox is currently checked.

        Returns:
            Ordered list of selected ``PromptInputSize`` values.
        """
        return [size for size, cb in self._input_checks.items() if cb.isChecked()]

    def get_selected_output_sizes(self) -> list[PromptOutputSize]:
        """Return all output sizes whose checkbox is currently checked.

        Returns:
            Ordered list of selected ``PromptOutputSize`` values.
        """
        return [size for size, cb in self._output_checks.items() if cb.isChecked()]

    def get_repeat_count(self) -> int:
        """Return the current repeat count from the spin box.

        Returns:
            Integer repeat count in the range 1-20.
        """
        return self._repeat_spinbox.value()
