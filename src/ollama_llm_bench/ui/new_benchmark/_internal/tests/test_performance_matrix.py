"""Unit tests for the Performance Matrix section widget defaults (STORY-071, STORY-092)."""

from PySide6.QtWidgets import QCheckBox, QSpinBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.performance_task_generator import SIZE_BUCKETS
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

_CAPTION_CASES: tuple[tuple[str, str, str], ...] = (
    ("input", "XS", "XS — ~5 tok · 1 sentence · 7 words"),
    ("input", "SM", "SM — ~50 tok · 1 paragraph · 70 words"),
    ("input", "MD", "MD — ~250 tok · 1 page · 380 words"),
    ("input", "LG", "LG — ~1500 tok · long doc · 2300 words"),
    ("input", "XL", "XL — ~3500 tok · very long · 5300 words"),
    ("output", "XS", "XS — ~1 sentence · ~15 words · ~25 tok"),
    ("output", "SM", "SM — ~5 sentences · ~75 words · ~125 tok"),
    ("output", "MD", "MD — ~20 sentences · ~300 words · ~500 tok"),
    ("output", "LG", "LG — ~100 sentences · ~1500 words · ~2500 tok"),
    ("output", "XL", "XL — ~500 sentences · ~7500 words · ~12500 tok"),
)


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


@pytest.mark.parametrize("axis_property", ["offered_input_sizes", "offered_output_sizes"])
def test_offered_sizes_equal_generator_published_table(
    axis_property: str,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-092-AC-2

    On a fresh widget, the token targets the Input Size toggles offer and the
    token targets the Output Size toggles offer each equal exactly the key set of
    the Performance Task Generator's published bucket table — so the generator's
    §4 precondition holds by construction, not by coincidence.
    """
    # Arrange
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    # Act
    offered = getattr(widget, axis_property)
    # Assert
    assert set(offered) == set(SIZE_BUCKETS)


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


@pytest.mark.parametrize(
    ("group", "size_key", "expected_caption"),
    _CAPTION_CASES,
    ids=[f"{group}_{key}" for group, key, _ in _CAPTION_CASES],
)
def test_toggle_captions_are_verbatim(
    group: str,
    size_key: str,
    expected_caption: str,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-071-AC-1

    Each Input Sizes and Output Sizes toggle's visible text is the exact
    spec-verbatim caption for its size bucket, character-for-character (em
    dash and middle dot included).
    """
    # Arrange / Act
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    # Assert
    box = widget.findChild(QCheckBox, f"new_benchmark.performance_matrix.{group}.{size_key}")
    assert box is not None
    assert box.text() == expected_caption  # type: ignore[unreachable]  # mypy false positive with narrowing
