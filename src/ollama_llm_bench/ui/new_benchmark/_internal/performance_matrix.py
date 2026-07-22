"""Performance Matrix section — Input Sizes, Output Sizes, Repeats (STORY-071).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §4.2 (captions, ranges,
XS+SM defaults), ``mode_specifics/synthetic.md`` §3, and the size-bucket table in
``11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md`` §2.3 — each toggle
carries its bucket's numeric token target, the only values the generator accepts.
The selection is per-session in-memory state only; every fresh construction
restores the XS+SM default (never persisted).
"""

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QSpinBox, QVBoxLayout, QWidget

__all__: list[str] = ["PerformanceMatrixSectionWidget"]

_REPEATS_MIN: Final[int] = 1
_REPEATS_MAX: Final[int] = 20
_REPEATS_DEFAULT: Final[int] = 3

# (size key, bucket token target, default checked, input caption, output caption)
_SIZE_ROWS: Final[tuple[tuple[str, int, bool, str, str], ...]] = (
    (
        "XS",
        64,
        True,
        "XS — ~5 tok · 1 sentence · 7 words",
        "XS — ~1 sentence · ~15 words · ~25 tok",
    ),
    (
        "SM",
        256,
        True,
        "SM — ~50 tok · 1 paragraph · 70 words",
        "SM — ~5 sentences · ~75 words · ~125 tok",
    ),
    (
        "MD",
        1024,
        False,
        "MD — ~250 tok · 1 page · 380 words",
        "MD — ~20 sentences · ~300 words · ~500 tok",
    ),
    (
        "LG",
        4096,
        False,
        "LG — ~1500 tok · long doc · 2300 words",
        "LG — ~100 sentences · ~1500 words · ~2500 tok",
    ),
    (
        "XL",
        16384,
        False,
        "XL — ~3500 tok · very long · 5300 words",
        "XL — ~500 sentences · ~7500 words · ~12500 tok",
    ),
)


class PerformanceMatrixSectionWidget(QWidget):
    """The three Synthetic-only sections: Input Sizes, Output Sizes, Repeats."""

    matrix_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.performance_matrix")
        self._input_boxes: dict[int, QCheckBox] = {}
        self._output_boxes: dict[int, QCheckBox] = {}
        layout = QVBoxLayout(self)
        self._add_size_group(layout, title="Input Sizes", group="input", boxes=self._input_boxes)
        self._add_size_group(layout, title="Output Sizes", group="output", boxes=self._output_boxes)
        layout.addWidget(_section_title("Repeats"))
        self._repeats_stepper = QSpinBox()
        self._repeats_stepper.setObjectName("new_benchmark.performance_matrix.repeats")
        self._repeats_stepper.setRange(_REPEATS_MIN, _REPEATS_MAX)
        self._repeats_stepper.setValue(_REPEATS_DEFAULT)
        self._repeats_stepper.valueChanged.connect(self._on_matrix_input_changed)
        layout.addWidget(self._repeats_stepper)
        self._estimate_label = QLabel("")
        self._estimate_label.setObjectName("new_benchmark.performance_matrix.estimate")
        layout.addWidget(self._estimate_label)

    def _add_size_group(
        self, layout: QVBoxLayout, *, title: str, group: str, boxes: dict[int, QCheckBox]
    ) -> None:
        layout.addWidget(_section_title(title))
        for row in _SIZE_ROWS:
            size_key, tokens, default_checked, input_caption, output_caption = row
            caption = input_caption if group == "input" else output_caption
            box = QCheckBox(caption)
            box.setObjectName(f"new_benchmark.performance_matrix.{group}.{size_key}")
            box.setChecked(default_checked)
            box.toggled.connect(self._on_matrix_input_changed)
            boxes[tokens] = box
            layout.addWidget(box)

    @property
    def selected_input_sizes(self) -> tuple[int, ...]:
        """The checked input buckets' token targets, ascending."""
        return tuple(tokens for tokens, box in self._input_boxes.items() if box.isChecked())

    @property
    def selected_output_sizes(self) -> tuple[int, ...]:
        """The checked output buckets' token targets, ascending."""
        return tuple(tokens for tokens, box in self._output_boxes.items() if box.isChecked())

    @property
    def repeats(self) -> int:
        """The Repeats stepper value (1..20)."""
        return self._repeats_stepper.value()

    def set_estimate_text(self, text: str) -> None:
        """Render the live estimated-task-count line under the Repeats stepper."""
        self._estimate_label.setText(text)

    def _on_matrix_input_changed(self, *_args: object) -> None:
        self.matrix_changed.emit()


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section-title")
    return label
