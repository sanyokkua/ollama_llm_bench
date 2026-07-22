"""Public factory for ``ui/new_benchmark/`` (STORY-054).

Source of truth: ``docs/v3_specification/02_New_Benchmark_Widget/description.md``,
``state_machine.md``, ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §7b.2.
``compose.py`` wiring is explicitly out of scope for this story (Phase 11 owns it) --
this factory only declares the collaborators a later composition-root story wires.
"""

import icontract
import msgspec
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.settings import PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.task_files import TaskFileLoader
from ollama_llm_bench.ui.new_benchmark._internal.advanced_options import (
    AdvancedOptionsSectionWidget,
)
from ollama_llm_bench.ui.new_benchmark._internal.controller import NewBenchmarkController
from ollama_llm_bench.ui.new_benchmark._internal.judge_section import JudgeSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.protocols import (
    ModeVisibilityPolicy,
    NewBenchmarkGateway,
    RunValidator,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["NewBenchmarkCollaborators", "make_new_benchmark_widget"]

_ANALYSIS_TOGGLE_KEY = "feature.judge_run_analysis_enabled"


class NewBenchmarkCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``make_new_benchmark_widget``'s collaborators (coding-style.md's
    4-parameter hard maximum -- the factory would otherwise take 8 keyword arguments).

    Attributes:
        gateway: The adapter gateway exposing settings/provider-list/readiness/
            start-run (D-R-06).
        event_bus: The bus this widget rebuilds its provider cache from on
            ``_provider_registry_reloaded``.
        task_file_loader: Parses a dropped/picked task file into tasks.
        mode_visibility_policy: The section-visibility source of truth.
        run_validator: Computes Run Validator entries for a would-be request
            (STORY-055 Design Decision 1).
        native_pickers: OS file/folder dialogs for Add File/Add Folder.
        workspace: Switches to the Task Editor workspace for "Open in Task Editor".
        theme_manager: Resolves theme roles for badges and section styling.
        platform_kind: The host platform classification passed alongside
            ``theme_manager`` to every themed custom-painted primitive.
    """

    gateway: NewBenchmarkGateway
    event_bus: EventBus
    task_file_loader: TaskFileLoader
    mode_visibility_policy: ModeVisibilityPolicy
    run_validator: RunValidator
    native_pickers: NativePickers
    workspace: WorkspaceController
    theme_manager: ThemeManager
    platform_kind: PlatformKind


@icontract.require(
    lambda collaborators: all(
        c is not None
        for c in (
            collaborators.gateway,
            collaborators.event_bus,
            collaborators.task_file_loader,
            collaborators.mode_visibility_policy,
            collaborators.run_validator,
            collaborators.native_pickers,
            collaborators.workspace,
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_new_benchmark_widget(*, collaborators: NewBenchmarkCollaborators) -> QWidget:
    """Construct the mountable New Benchmark widget.

    Args:
        collaborators: Every collaborator this widget and its controller need,
            bundled per coding-style.md's 4-parameter hard maximum.

    Returns:
        The fully wired, mountable ``QWidget``, ready to be added to a parent layout.
    """
    mode_selector = ModeSelectorWidget()
    task_files_section = TaskFilesSectionWidget(
        task_file_loader=collaborators.task_file_loader,
        native_pickers=collaborators.native_pickers,
        workspace=collaborators.workspace,
        theme_manager=collaborators.theme_manager,
        platform_kind=collaborators.platform_kind,
    )
    test_models_section = TestModelsSectionWidget(
        provider_configs_source=collaborators.gateway.provider_list,
        hide_embedding_models_initial=(
            collaborators.gateway.get_setting("embedding.hide_from_test_models") or "true"
        )
        == "true",
        on_hide_embedding_changed=lambda value: collaborators.gateway.set_setting(
            "embedding.hide_from_test_models", "true" if value else "false"
        ),
        event_bus=collaborators.event_bus,
    )
    judge_section = JudgeSectionWidget(
        provider_configs_source=collaborators.gateway.provider_list,
        hide_embedding_models_source=lambda: test_models_section.hide_embedding_models,
        event_bus=collaborators.event_bus,
    )
    advanced_options_section = AdvancedOptionsSectionWidget(
        initial_values={
            key: collaborators.gateway.get_setting(key) or ""
            for key in sorted(PER_RUN_OVERRIDABLE - {_ANALYSIS_TOGGLE_KEY})
        }
    )
    view = NewBenchmarkView(
        mode_selector=mode_selector,
        task_files_section=task_files_section,
        test_models_section=test_models_section,
        judge_section=judge_section,
        advanced_options_section=advanced_options_section,
    )
    controller = NewBenchmarkController(
        gateway=collaborators.gateway,
        event_bus=collaborators.event_bus,
        mode_visibility_policy=collaborators.mode_visibility_policy,
        run_validator=collaborators.run_validator,
        view=view,
    )
    controller.bind()
    return view
