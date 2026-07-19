"""Public factory for ``ui/progress/`` (STORY-058).

Source of truth: ``docs/v3_specification/04_Progress_Widget/implementation_structure.md``
§2, §7. ``compose.py`` wiring of the concrete ``ProgressGateway`` is out of scope for
this story (Phase 11 owns it) -- this factory only declares the collaborators a later
composition-root story wires, matching the ``ui/resume_benchmark``/``ui/new_benchmark``
precedent.
"""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.ui.progress._internal.controller import ProgressController
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = ["make_progress_widget"]


@icontract.require(lambda bus: bus is not None, "bus is a required collaborator")
@icontract.require(lambda gateway: gateway is not None, "gateway is a required collaborator")
@icontract.require(
    lambda log_formatter: log_formatter is not None,
    "log_formatter is a required collaborator",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_progress_widget(
    *,
    bus: EventBus,
    gateway: ProgressGateway,
    log_formatter: LogFormatter,
) -> QWidget:
    """Build the Progress Widget shell, header, counters, and stability regions.

    Args:
        bus: The application ``EventBus``; every live update arrives here.
        gateway: The widget's own adapter gateway (D-R-06), wrapping the
            benchmark-flow controls, run-registry/run/results reads, the
            past-log reader, the run-log settings, and the manual
            provider-probe command (08-E §7b.4, plus STORY-058's ``list_runs``/
            ``is_run_active`` extensions).
        log_formatter: Renders one event into an HTML log line at a
            verbosity. Retained on the factory signature per
            ``implementation_structure.md`` §2 so the public surface never has
            to change shape across STORY-058 -> STORY-060, even though this
            story's own code paths (no Log region yet) do not call it.

    Returns:
        The mountable, unshown ``QWidget`` the caller places in the Benchmark
        workspace centre panel.
    """
    view = ProgressView()
    controller = ProgressController(gateway=gateway, event_bus=bus, log_formatter=log_formatter)
    controller.bind(view)
    return view
