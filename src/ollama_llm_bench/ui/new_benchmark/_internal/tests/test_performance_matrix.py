"""Unit tests for the Performance Matrix section widget defaults (STORY-071)."""

from PySide6.QtWidgets import QCheckBox, QSpinBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.new_benchmark._internal.performance_matrix import (
    PerformanceMatrixSectionWidget,
)

_DEFAULT_CASES: tuple[tuple[str, str, bool], ...] = (
    ("input", "XS", True),
    ("input", "SM", True),
    ("input", "MD", False),
    ("input", "LG", False),
    ("input", "XL", False),
    ("output", "XS", True),
    ("output", "SM", True),
    ("output", "MD", False),
    ("output", "LG", False),
    ("output", "XL", False),
)

_DEFAULT_REPEATS: int = 3


@pytest.mark.parametrize(
    ("group", "size_key", "expected_checked"),
    _DEFAULT_CASES,
    ids=[f"{group}_{key}" for group, key, _ in _DEFAULT_CASES],
)
def test_default_size_selection_and_repeats(
    group: str,
    size_key: str,
    expected_checked: bool,  # noqa: FBT001  # pytest parametrize provides bool positionally
    qtbot: QtBot,
) -> None:
    """Proves: STORY-071-AC-1

    On a fresh construction, XS and SM are checked and MD/LG/XL unchecked in
    both the Input Sizes and Output Sizes groups.
    """
    # Arrange / Act
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    # Assert
    box = widget.findChild(QCheckBox, f"new_benchmark.performance_matrix.{group}.{size_key}")
    assert box is not None
    assert box.isChecked() == expected_checked  # type: ignore[unreachable]  # mypy false positive with narrowing


def test_repeats_stepper_default_and_range(qtbot: QtBot) -> None:
    """Proves: STORY-071-AC-1

    The Repeats stepper reads 3 on a fresh construction and is bounded 1..20.
    """
    # Arrange / Act
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    # Assert
    stepper = widget.findChild(QSpinBox, "new_benchmark.performance_matrix.repeats")
    assert stepper is not None
    assert (stepper.value(), stepper.minimum(), stepper.maximum()) == (3, 1, 20)  # type: ignore[unreachable]  # mypy false positive with narrowing


def test_selected_sizes_expose_bucket_token_targets(qtbot: QtBot) -> None:
    """Proves: STORY-071-AC-1

    The default XS+SM selection maps to the generator's bucket token targets
    (64, 256) on both axes — the exact values `PerformanceConfig` must carry.
    """
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    assert widget.selected_input_sizes == (64, 256)
    assert widget.selected_output_sizes == (64, 256)
    assert widget.repeats == _DEFAULT_REPEATS
