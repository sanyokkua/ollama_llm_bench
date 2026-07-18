"""Public factory for ``ui/new_benchmark/`` (STORY-054).

Source of truth: ``docs/v3_specification/02_New_Benchmark_Widget/description.md``,
``state_machine.md``, ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §7b.2.
``compose.py`` wiring is explicitly out of scope for this story (Phase 11 owns it) --
this factory only declares the collaborators a later composition-root story wires.
"""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.task_files import TaskFileLoader
from ollama_llm_bench.ui.new_benchmark._internal.controller import NewBenchmarkController
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.protocols import ModeVisibilityPolicy, NewBenchmarkGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["make_new_benchmark_widget"]


@icontract.require(
    lambda gateway, event_bus, task_file_loader, mode_visibility_policy, native_pickers, workspace: (
        all(
            collaborator is not None
            for collaborator in (
                gateway,
                event_bus,
                task_file_loader,
                mode_visibility_policy,
                native_pickers,
                workspace,
            )
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_new_benchmark_widget(  # noqa: PLR0913  # six distinct required collaborators per the
    # approved STORY-054 design (docs/stories/story-054-new-benchmark-configuration-surface.md
    # Design constraints); each is an independently-faked test seam, not groupable into one
    # struct without losing that (matching the ui.main_window.api precedent)
    *,
    gateway: NewBenchmarkGateway,
    event_bus: EventBus,
    task_file_loader: TaskFileLoader,
    mode_visibility_policy: ModeVisibilityPolicy,
    native_pickers: NativePickers,
    workspace: WorkspaceController,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> QWidget:
    """Construct the mountable New Benchmark widget.

    Judge, Advanced Options, embedding status row, and Start-flow behaviour are
    stubbed (STORY-055); Performance Matrix content is stubbed (a new,
    not-yet-drafted future story) -- both still participate in section
    visibility via ``mode_visibility_policy``.

    Args:
        gateway: The adapter gateway exposing settings/provider-list/readiness/
            start-run (D-R-06).
        event_bus: The bus this widget rebuilds its provider cache from on
            ``_provider_registry_reloaded``.
        task_file_loader: Parses a dropped/picked task file into tasks.
        mode_visibility_policy: The section-visibility source of truth.
        native_pickers: OS file/folder dialogs for Add File/Add Folder.
        workspace: Switches to the Task Editor workspace for "Open in Task Editor".
        theme_manager: Resolves theme roles for badges and section styling.
        platform_kind: The host platform classification passed alongside
            ``theme_manager`` to every themed custom-painted primitive.

    Returns:
        The fully wired, mountable ``QWidget``, ready to be added to a parent layout.
    """
    mode_selector = ModeSelectorWidget()
    task_files_section = TaskFilesSectionWidget(
        task_file_loader=task_file_loader,
        native_pickers=native_pickers,
        workspace=workspace,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    test_models_section = TestModelsSectionWidget(
        provider_configs_source=gateway.provider_list,
        hide_embedding_models_initial=(
            gateway.get_setting("embedding.hide_from_test_models") or "true"
        )
        == "true",
        on_hide_embedding_changed=lambda value: gateway.set_setting(
            "embedding.hide_from_test_models", "true" if value else "false"
        ),
        event_bus=event_bus,
    )
    view = NewBenchmarkView(
        mode_selector=mode_selector,
        task_files_section=task_files_section,
        test_models_section=test_models_section,
    )
    controller = NewBenchmarkController(
        gateway=gateway,
        event_bus=event_bus,
        mode_visibility_policy=mode_visibility_policy,
        view=view,
    )
    controller.bind()
    return view
