"""Public factory for ``ui/results/`` (STORY-061).

Source of truth: ``docs/v3_specification/05_Result_Widget/implementation_structure.md``
§2 (public API), §8 (factory wiring example). ``compose.py`` wiring is explicitly out
of scope for this story (Phase 11 owns it) -- this factory only declares the
collaborators a later composition-root story wires. The four tab bodies mount into
this widget's empty tab-body host containers in STORY-062..065; this factory
constructs no tab sub-controller.
"""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.results._internal.controller import ResultController
from ollama_llm_bench.ui.results._internal.view import ResultView
from ollama_llm_bench.ui.results.models import ResultCollaborators

__all__: list[str] = ["make_result_widget"]


@icontract.require(
    lambda collaborators: all(
        c is not None
        for c in (
            collaborators.bus,
            collaborators.gateway,
            collaborators.native_pickers,
            collaborators.clipboard,
            collaborators.file_system_actions,
            collaborators.notifications,
            collaborators.export_filenames,
            collaborators.provider_source,
            collaborators.model_fetcher,
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_result_widget(*, collaborators: ResultCollaborators) -> QWidget:
    """Construct the mountable Result widget shell.

    Args:
        collaborators: The gateway, event bus, and OS-adapter helpers this
            widget's controller and footer depend on (D-R-06).

    Returns:
        A QWidget ready to mount into the Benchmark workspace right panel.
    """
    controller = ResultController(collaborators=collaborators)
    view = ResultView(platform_kind=collaborators.platform_kind)
    view.dropdown_changed.connect(controller.on_dropdown_changed)
    view.tab_changed.connect(controller.on_tab_changed)
    view.export_clicked.connect(controller.on_export_clicked)
    view.save_directly_toggled.connect(controller.on_save_directly_toggled)
    view.open_exports_folder_clicked.connect(controller.on_open_exports_folder_clicked)
    controller.bind(view)
    controller.load_initial_state()
    return view
