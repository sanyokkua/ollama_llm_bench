"""Unit tests verifying that _build_run_start_event preserves all providers.

Covers the multi-provider fix: selecting models from two different providers
must result in both ModelDescriptor objects appearing in RunStartEvent.test_models,
with their original provider_id values intact.
"""

from typing import cast

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import (
    AdvancedRunOptions,
    ModelDescriptor,
    ReadinessVerdict,
    RunMode,
    RunStartEvent,
)
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DESCRIPTOR_OLLAMA = ModelDescriptor(
    provider_id="ollama_local",
    provider_type="ollama",
    model_name="llama3:8b",
    display_label="llama3:8b (ollama_local)",
)

_DESCRIPTOR_LM_STUDIO = ModelDescriptor(
    provider_id="lm_studio_local",
    provider_type="openai_compatible",
    model_name="mistral-7b",
    display_label="mistral-7b (lm_studio_local)",
)

_ADVANCED_OPTS = AdvancedRunOptions(
    streaming_enabled=True,
    warmup_enabled=True,
    reasoning_effort="default",
    streaming_is_override=False,
    warmup_is_override=False,
    reasoning_is_override=False,
)


# ---------------------------------------------------------------------------
# Panel fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def run_config_panel(qapp: QApplication, mocker: MockerFixture) -> RunConfigPanel:
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_svc = mocker.Mock()
    mock_svc.get_bool.return_value = True
    mock_svc.get.return_value = "0"
    mock_ctrl._app_settings_service = mock_svc
    mock_ctrl.get_provider_names.return_value = []
    mock_ctrl.get_healthy_provider_ids.return_value = []
    mock_ctrl.get_recent_runs.return_value = []
    mock_ctrl.readiness_verdict.return_value = ReadinessVerdict(
        mode=RunMode.SPEED, is_ready=True, issues=(), severity="ok"
    )
    return RunConfigPanel(controller=cast(RunConfigController, mock_ctrl))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_run_start_event_preserves_all_providers(
    run_config_panel: RunConfigPanel,
    mocker: MockerFixture,
) -> None:
    """_build_run_start_event must include descriptors from all selected providers."""
    # Arrange — replace internal sub-widgets with mocks
    mock_store = mocker.Mock()
    mock_store.all.return_value = [_DESCRIPTOR_OLLAMA, _DESCRIPTOR_LM_STUDIO]

    mock_test_models = mocker.Mock()
    mock_test_models.get_selection_store.return_value = mock_store

    mock_run_mode = mocker.Mock()
    mock_run_mode.current_mode.return_value = RunMode.FULL_GRADING

    mock_judge = mocker.Mock()
    mock_judge.get_selected_provider.return_value = "ollama_local"
    mock_judge.get_selected_model.return_value = "llama3:8b"

    mock_task_files = mocker.Mock()
    mock_task_files.get_task_paths.return_value = []

    mock_advanced = mocker.Mock()
    mock_advanced.get_effective_options.return_value = _ADVANCED_OPTS

    run_config_panel._test_models_widget = mock_test_models  # type: ignore[assignment]
    run_config_panel._run_mode_widget = mock_run_mode  # type: ignore[assignment]
    run_config_panel._judge_widget = mock_judge  # type: ignore[assignment]
    run_config_panel._task_files_widget = mock_task_files  # type: ignore[assignment]
    run_config_panel._advanced_widget = mock_advanced  # type: ignore[assignment]

    # Act
    event = run_config_panel._build_run_start_event()

    # Assert
    assert isinstance(event, RunStartEvent)
    assert len(event.test_models) == 2
    provider_ids = {d.provider_id for d in event.test_models}
    assert provider_ids == {"ollama_local", "lm_studio_local"}


def test_build_run_start_event_preserves_descriptor_identity(
    run_config_panel: RunConfigPanel,
    mocker: MockerFixture,
) -> None:
    """Descriptor objects in test_models must be identical to those in the store."""
    mock_store = mocker.Mock()
    mock_store.all.return_value = [_DESCRIPTOR_OLLAMA, _DESCRIPTOR_LM_STUDIO]

    mock_test_models = mocker.Mock()
    mock_test_models.get_selection_store.return_value = mock_store

    mock_run_mode = mocker.Mock()
    mock_run_mode.current_mode.return_value = RunMode.FULL_GRADING

    mock_judge = mocker.Mock()
    mock_judge.get_selected_provider.return_value = "ollama_local"
    mock_judge.get_selected_model.return_value = "llama3:8b"

    mock_task_files = mocker.Mock()
    mock_task_files.get_task_paths.return_value = []

    mock_advanced = mocker.Mock()
    mock_advanced.get_effective_options.return_value = _ADVANCED_OPTS

    run_config_panel._test_models_widget = mock_test_models  # type: ignore[assignment]
    run_config_panel._run_mode_widget = mock_run_mode  # type: ignore[assignment]
    run_config_panel._judge_widget = mock_judge  # type: ignore[assignment]
    run_config_panel._task_files_widget = mock_task_files  # type: ignore[assignment]
    run_config_panel._advanced_widget = mock_advanced  # type: ignore[assignment]

    event = run_config_panel._build_run_start_event()

    assert event is not None
    assert _DESCRIPTOR_OLLAMA in event.test_models
    assert _DESCRIPTOR_LM_STUDIO in event.test_models


def test_build_run_start_event_returns_none_when_no_models_in_grading_mode(
    run_config_panel: RunConfigPanel,
    mocker: MockerFixture,
) -> None:
    """_build_run_start_event must return None when no models selected in FULL_GRADING mode."""
    mock_store = mocker.Mock()
    mock_store.all.return_value = []

    mock_test_models = mocker.Mock()
    mock_test_models.get_selection_store.return_value = mock_store

    mock_run_mode = mocker.Mock()
    mock_run_mode.current_mode.return_value = RunMode.FULL_GRADING

    mock_judge = mocker.Mock()
    mock_judge.get_selected_provider.return_value = "ollama_local"
    mock_judge.get_selected_model.return_value = "llama3:8b"

    run_config_panel._test_models_widget = mock_test_models  # type: ignore[assignment]
    run_config_panel._run_mode_widget = mock_run_mode  # type: ignore[assignment]
    run_config_panel._judge_widget = mock_judge  # type: ignore[assignment]

    result = run_config_panel._build_run_start_event()

    assert result is None
