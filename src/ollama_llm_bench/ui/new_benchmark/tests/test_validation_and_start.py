"""Unit tests for the Run Validator wiring and the Start button gate
(STORY-055-AC-4, AC-5).
"""

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import InferenceActivity, InferenceActivityState
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry
from ollama_llm_bench.ui.new_benchmark.protocols import RunValidator
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

_IN_FLIGHT_TOOLTIP = "Another inference activity is in flight — please wait."
_REVIEW_WARNINGS_TOOLTIP = "Click to review warnings before starting."

_ZERO_MODELS_MESSAGE = "Select at least one test model before starting."
_NO_TASK_FILES_MESSAGE = "Add at least one task file for this mode before starting."
_TIMEOUT_ORDER_MESSAGE = "Maximum timeout must be greater than or equal to minimum timeout."
_NO_JUDGE_PROVIDER_MESSAGE = "No enabled provider for judging. Open Settings to add one."
_STREAMING_UNCONFIRMED_MESSAGE = "Streaming has not been confirmed for the selected model."
_EC_RUN_3_MESSAGE = "No provider for the selected models is reachable."
_EC_TASK_2_MESSAGE = (
    "Two tasks share the same task_id; the Task File Validator flags both rows as hard errors."
)
_EC_PROV_6_MESSAGE = (
    "A selected provider's environment variable is unset; starting a run is "
    "blocked for that provider's selected models."
)

_SEVERITY_CASES: tuple[tuple[str, tuple[ValidationEntry, ...], bool, str], ...] = (
    (
        "zero_models_selected",
        (ValidationEntry(severity=RunValidationSeverity.HARD_ERROR, message=_ZERO_MODELS_MESSAGE),),
        False,
        _ZERO_MODELS_MESSAGE,
    ),
    (
        "tasks_or_graded_no_task_files",
        (
            ValidationEntry(
                severity=RunValidationSeverity.HARD_ERROR, message=_NO_TASK_FILES_MESSAGE
            ),
        ),
        False,
        _NO_TASK_FILES_MESSAGE,
    ),
    (
        "max_timeout_less_than_min_timeout",
        (
            ValidationEntry(
                severity=RunValidationSeverity.HARD_ERROR, message=_TIMEOUT_ORDER_MESSAGE
            ),
        ),
        False,
        _TIMEOUT_ORDER_MESSAGE,
    ),
    (
        "no_enabled_judge_provider_while_required",
        (
            ValidationEntry(
                severity=RunValidationSeverity.HARD_ERROR, message=_NO_JUDGE_PROVIDER_MESSAGE
            ),
        ),
        False,
        _NO_JUDGE_PROVIDER_MESSAGE,
    ),
    (
        "soft_warning_only_streaming_unconfirmed",
        (
            ValidationEntry(
                severity=RunValidationSeverity.SOFT_WARNING, message=_STREAMING_UNCONFIRMED_MESSAGE
            ),
        ),
        True,
        _REVIEW_WARNINGS_TOOLTIP,
    ),
    ("no_validation_entries", (), True, ""),
    (
        "ec_run_3_no_reachable_test_model",
        (ValidationEntry(severity=RunValidationSeverity.HARD_ERROR, message=_EC_RUN_3_MESSAGE),),
        False,
        _EC_RUN_3_MESSAGE,
    ),
    (
        "ec_task_2_duplicate_task_id",
        (ValidationEntry(severity=RunValidationSeverity.HARD_ERROR, message=_EC_TASK_2_MESSAGE),),
        False,
        _EC_TASK_2_MESSAGE,
    ),
    (
        "ec_prov_6_missing_env_var",
        (ValidationEntry(severity=RunValidationSeverity.HARD_ERROR, message=_EC_PROV_6_MESSAGE),),
        False,
        _EC_PROV_6_MESSAGE,
    ),
)


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


@pytest.mark.parametrize(
    ("entries", "expected_enabled", "expected_tooltip"),
    [case[1:] for case in _SEVERITY_CASES],
    ids=[case[0] for case in _SEVERITY_CASES],
)
def test_start_button_reflects_validator_severity(  # noqa: PLR0913  # parametrize axes plus
    # five construction fixtures
    entries: tuple[ValidationEntry, ...],
    expected_enabled: bool,  # noqa: FBT001  # parametrize tuple element
    expected_tooltip: str,
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-055-AC-4

    Covers: EC-RUN-3, EC-TASK-2, EC-PROV-6

    For each Run Validator condition, the Start button reflects the produced
    severity: any hard error disables Start with a tooltip joining every hard-error
    message; only soft warnings leaves Start enabled with the review-warnings
    tooltip; no entries at all leaves Start enabled with no tooltip.
    """
    # Arrange / Act
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=entries),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    # Assert
    assert view.start_button.isEnabled() is expected_enabled
    assert view.start_button.toolTip() == expected_tooltip


def test_start_button_gated_on_inference_activity(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-055-AC-5

    Covers: EC-RUN-1

    Given the configuration has no hard error, when a _inference_activity_changed
    event reports the gate held by another activity, then the Start button
    disables with the in-flight tooltip; and when the gate returns to IDLE, the
    Start button re-enables.
    """
    # Arrange
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=()),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    assert view.start_button.isEnabled()
    # Act (the gate is acquired by another activity)
    fake_event_bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(
            state=InferenceActivityState(current=InferenceActivity.BENCHMARK_RUN)
        ),
    )
    # Assert (disabled with the in-flight tooltip)
    assert not view.start_button.isEnabled()
    assert view.start_button.toolTip() == _IN_FLIGHT_TOOLTIP
    # Act (the gate returns to IDLE)
    fake_event_bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(state=InferenceActivityState(current=InferenceActivity.IDLE)),
    )
    # Assert (re-enabled)
    assert view.start_button.isEnabled()
