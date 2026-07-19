"""Public factory for ``ui/resume_benchmark/`` (STORY-056).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``.
``compose.py`` wiring is explicitly out of scope for this story (Phase 11 owns it) --
this factory only declares the collaborators a later composition-root story wires.
"""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController
from ollama_llm_bench.ui.resume_benchmark._internal.view import ResumeBenchmarkView
from ollama_llm_bench.ui.resume_benchmark.models import ResumeBenchmarkCollaborators

__all__: list[str] = ["make_resume_benchmark_widget"]


@icontract.require(
    lambda collaborators: all(
        c is not None
        for c in (
            collaborators.gateway,
            collaborators.event_bus,
            collaborators.native_pickers,
            collaborators.file_system_actions,
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_resume_benchmark_widget(*, collaborators: ResumeBenchmarkCollaborators) -> QWidget:
    """Construct the mountable Resume Benchmark widget.

    Args:
        collaborators: The gateway, event bus, and OS-adapter helpers this
            widget's controller depends on (D-R-06).

    Returns:
        A QWidget ready to mount into the workspace left panel.
    """
    controller = ResumeBenchmarkController(
        gateway=collaborators.gateway,
        event_bus=collaborators.event_bus,
        native_pickers=collaborators.native_pickers,
        file_system_actions=collaborators.file_system_actions,
    )
    view = ResumeBenchmarkView(
        controller=controller,
        theme_manager=collaborators.theme_manager,
        platform_kind=collaborators.platform_kind,
    )
    controller.bind(view)
    controller.load_initial_rows()
    return view
