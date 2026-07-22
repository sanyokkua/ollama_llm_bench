"""Synthetic missing-sizes validation tests (STORY-071)."""

from PySide6.QtWidgets import QCheckBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import PerformanceConfig, RunMode, RunStartRequest
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark._internal.synthetic_validation import (
    MISSING_SIZES_MESSAGE,
    SyntheticSizeRuleValidator,
)
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry
from ollama_llm_bench.ui.new_benchmark.protocols import RunValidator
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager


def _build_widget(
    *,
    run_validator: RunValidator,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> tuple[NewBenchmarkView, FakeNewBenchmarkGateway]:
    gateway = FakeNewBenchmarkGateway()
    collaborators = NewBenchmarkCollaborators(
        gateway=gateway,
        event_bus=fake_event_bus,
        task_file_loader=FakeTaskFileLoader(),
        mode_visibility_policy=real_mode_visibility_policy,
        run_validator=run_validator,
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    widget = make_new_benchmark_widget(collaborators=collaborators)
    assert isinstance(widget, NewBenchmarkView)
    return widget, gateway


@pytest.mark.parametrize("group", ["input", "output"])
def test_missing_input_or_output_size_disables_start(  # noqa: PLR0913  # parametrize axis
    # plus four construction fixtures
    group: str,
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-071-AC-4

    Unchecking every size in either group produces the hard error
    'Select at least one input size and one output size.' and disables Start.
    """
    # Arrange -- inner validator returns nothing; only the local rule can fire
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=()),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    assert view.start_button.isEnabled()  # XS+SM defaults are valid
    matrix = view.performance_matrix_section
    # Act -- only XS and SM are checked by default; unchecking both empties the group
    xs_box = matrix.findChild(QCheckBox, f"new_benchmark.performance_matrix.{group}.XS")
    sm_box = matrix.findChild(QCheckBox, f"new_benchmark.performance_matrix.{group}.SM")
    assert xs_box is not None
    assert sm_box is not None  # type: ignore[unreachable]  # mypy false positive with narrowing
    xs_box.setChecked(False)
    sm_box.setChecked(False)
    # Assert
    assert not view.start_button.isEnabled()
    assert MISSING_SIZES_MESSAGE in view.start_button.toolTip()


def test_size_rule_prepends_entry_and_passes_through_inner() -> None:
    """Proves: STORY-071-AC-4

    The decorator adds the hard error only for a SYNTHETIC request with an empty
    axis, and always forwards the inner validator's entries.
    """
    # Arrange
    inner_entry = ValidationEntry(
        severity=RunValidationSeverity.SOFT_WARNING, message="inner-warning"
    )
    validator = SyntheticSizeRuleValidator(inner=FakeRunValidator(entries=(inner_entry,)))
    empty_axis = RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(),
        performance_config=PerformanceConfig(input_sizes=(), output_sizes=(64,), repeats=3),
    )
    valid = RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(),
        performance_config=PerformanceConfig(input_sizes=(64,), output_sizes=(64,), repeats=3),
    )
    tasks_mode = RunStartRequest(run_mode=RunMode.TASKS, test_models=(), performance_config=None)
    # Act / Assert
    assert [e.message for e in validator.validate(empty_axis)] == [
        MISSING_SIZES_MESSAGE,
        "inner-warning",
    ]
    assert [e.message for e in validator.validate(valid)] == ["inner-warning"]
    assert [e.message for e in validator.validate(tasks_mode)] == ["inner-warning"]
