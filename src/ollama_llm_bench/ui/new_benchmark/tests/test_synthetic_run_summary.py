"""Run Summary work-count breakdown test (STORY-071)."""

from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderConfig,
    ProviderHealth,
    ProviderType,
    ReadinessState,
)
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.common_dialogs import make_run_summary_dialog
from ollama_llm_bench.ui.new_benchmark._internal.advanced_options import (
    AdvancedOptionsSectionWidget,
)
from ollama_llm_bench.ui.new_benchmark._internal.controller import NewBenchmarkController
from ollama_llm_bench.ui.new_benchmark._internal.judge_section import JudgeSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget
from ollama_llm_bench.ui.new_benchmark._internal.synthetic_validation import (
    SyntheticSizeRuleValidator,
)
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

_PROVIDER_ID = "aaaaaaaa-0000-4000-8000-000000000000"
_MODEL_NAME = "llama3"


def test_run_summary_work_count_matches_live_estimate(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-071-AC-5

    The Run Summary dialog's work-count line shows
    'cells x repeats x models = N tasks' where N equals the live estimate
    rendered in the panel.
    """
    # Arrange: real sections + NewBenchmarkView + NewBenchmarkController, constructed
    # directly (mirrors make_new_benchmark_widget's own wiring in api.py) so the test
    # keeps a handle on the controller -- the public factory only returns the view.
    gateway = FakeNewBenchmarkGateway()
    gateway.set_providers(
        (
            ProviderConfig(
                provider_id=_PROVIDER_ID,
                name="Local Ollama",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                enabled=True,
            ),
        )
    )
    gateway.set_readiness(
        AppReadinessSnapshot(
            overall=ReadinessState.READY,
            per_provider=(
                ProviderHealth(
                    provider_id=_PROVIDER_ID,
                    reachable=True,
                    discovery_supported=True,
                    model_count=1,
                    last_probe_ms=5,
                    probed_at=0,
                ),
            ),
            embedding_reachable=True,
        )
    )
    mode_selector = ModeSelectorWidget()
    task_files_section = TaskFilesSectionWidget(
        task_file_loader=FakeTaskFileLoader(),
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    test_models_section = TestModelsSectionWidget(
        provider_configs_source=gateway.provider_list,
        hide_embedding_models_initial=True,
        on_hide_embedding_changed=lambda _value: None,
        event_bus=fake_event_bus,
    )
    judge_section = JudgeSectionWidget(
        provider_configs_source=gateway.provider_list,
        hide_embedding_models_source=lambda: test_models_section.hide_embedding_models,
        event_bus=fake_event_bus,
    )
    advanced_options_section = AdvancedOptionsSectionWidget(initial_values={})
    view = NewBenchmarkView(
        mode_selector=mode_selector,
        task_files_section=task_files_section,
        test_models_section=test_models_section,
        judge_section=judge_section,
        advanced_options_section=advanced_options_section,
    )
    validator = SyntheticSizeRuleValidator(inner=FakeRunValidator(entries=()))
    controller = NewBenchmarkController(
        gateway=gateway,
        event_bus=fake_event_bus,
        mode_visibility_policy=real_mode_visibility_policy,
        run_validator=validator,
        view=view,
    )
    controller.bind()
    qtbot.addWidget(view)
    # Select one (provider, model) pair the fake gateway's provider_list actually
    # reports -- the run mode defaults to SYNTHETIC with the XS+SM size defaults, so
    # this alone produces cells=4, repeats=3, models=1 -> live estimate 12.
    view.test_models_section.selection.add(_PROVIDER_ID, _MODEL_NAME)
    view.test_models_section.selection_changed.emit()
    estimate_label = view.performance_matrix_section.findChild(
        QLabel, "new_benchmark.performance_matrix.estimate"
    )
    assert estimate_label is not None
    estimate_text = estimate_label.text()  # type: ignore[unreachable]  # mypy false positive with narrowing
    live_estimate = int(estimate_text.removeprefix("Estimated tasks: "))
    # Act: assemble the dialog from the controller-built request (no exec())
    request = controller._build_current_run_start_request()
    dialog = make_run_summary_dialog(
        gateway=gateway, run_validator=validator, request=request, parent=view
    )
    # Assert
    assert dialog is not None
    config = request.performance_config
    assert config is not None
    cells = len(config.input_sizes) * len(config.output_sizes)
    expected_line = (
        f"{cells} cells × {config.repeats} repeats "  # noqa: RUF001  # matches dialog's mult. sign
        f"× {len(request.test_models)} models = {live_estimate} tasks"  # noqa: RUF001
    )
    dialog_texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert expected_line in dialog_texts
