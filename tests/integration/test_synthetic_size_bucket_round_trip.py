"""Integration test: every bucket the Performance Matrix offers round-trips through the
Performance Task Generator (STORY-092-AC-3).

This crosses ``ui/new_benchmark/`` <-> ``backend/performance_task_generator/``, so it
belongs in ``tests/integration/`` rather than either module's colocated ``tests/``
(07_TESTING_STANDARD.md layout). It is the assertion that the generator's §4
precondition -- "every numeric value in ``input_sizes``/``output_sizes`` corresponds to a
defined size bucket" -- is now guaranteed by construction: no selection the user can make
in the Performance Matrix can produce the §8 "no matching size bucket" failure that aborts
run creation.

The token targets are restated in ``_BUCKET_CASES`` on purpose. AC-3's table pairs each
widget toggle with the exact number ``PerformanceConfig`` must carry; deriving those
numbers from ``SIZE_BUCKETS`` would reduce the test to asserting ``x == x``.
"""

from typing import cast

from PySide6.QtWidgets import QCheckBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import PerformanceConfig
from ollama_llm_bench.backend.performance_task_generator import make_performance_task_generator
from ollama_llm_bench.ui.new_benchmark._internal.performance_matrix import (
    PerformanceMatrixSectionWidget,
)

# (§4.2 widget toggle, the token target it must carry into PerformanceConfig)
_BUCKET_CASES: tuple[tuple[str, int], ...] = (
    ("XS", 64),
    ("SM", 256),
    ("MD", 1024),
    ("LG", 4096),
    ("XL", 16384),
)


def _select_only(widget: PerformanceMatrixSectionWidget, size_key: str) -> None:
    """Check exactly one size bucket on both axes, clearing the XS+SM defaults.

    A helper rather than inline test code because the testing standard forbids a loop in a
    test body; the loop itself is unavoidable, since selecting one bucket means unchecking
    the four others on each of the two axes.
    """
    suffix = f".{size_key}"
    # PySide6's findChildren stub is typed ``Iterable[PlaceHolderType]``, which mypy
    # resolves to ``Iterable[Never]``; the cast restores the type Qt actually returns.
    boxes = cast("list[QCheckBox]", widget.findChildren(QCheckBox))
    for box in boxes:
        box.setChecked(box.objectName().endswith(suffix))


@pytest.mark.parametrize(
    ("size_key", "expected_tokens"),
    _BUCKET_CASES,
    ids=[size_key for size_key, _ in _BUCKET_CASES],
)
def test_every_offered_bucket_is_accepted_by_the_generator(
    size_key: str,
    expected_tokens: int,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-092-AC-3

    Selecting exactly one size bucket on both axes yields a ``PerformanceConfig``
    carrying that bucket's token target, which the generator expands into tasks
    without raising -- for every bucket the widget offers.
    """
    # Arrange
    widget = PerformanceMatrixSectionWidget()
    qtbot.addWidget(widget)
    _select_only(widget, size_key)
    config = PerformanceConfig(
        input_sizes=widget.selected_input_sizes,
        output_sizes=widget.selected_output_sizes,
        repeats=1,
    )
    # Act
    tasks = make_performance_task_generator().generate(config)
    # Assert
    assert (config.input_sizes, config.output_sizes, len(tasks)) == (
        (expected_tokens,),
        (expected_tokens,),
        1,
    )
