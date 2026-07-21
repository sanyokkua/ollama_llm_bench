"""``pytest-qt`` tests for the Result widget's Run Analysis tab (STORY-065).

Constructs ``JudgeAnalysisTabView``/``JudgeAnalysisTabController`` directly -- the
sub-controller's own tests need no parent shell (mirrors ``test_details_tab.py``'s
sub-controller-only test pattern). Every ``FakeResultGateway``/``FakeEventBus`` test
double is reused verbatim from ``ui/results/tests/conftest.py``.
"""

from collections.abc import Callable
from typing import cast

import msgspec
from PySide6.QtWidgets import QLabel, QPushButton, QTextBrowser
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    InferenceActivityContext,
    InferenceActivityState,
    ResultStatus,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result
from ollama_llm_bench.ui.results._internal.run_analysis_tab.controller import (
    JudgeAnalysisTabController,
)
from ollama_llm_bench.ui.results._internal.run_analysis_tab.view import JudgeAnalysisTabView
from ollama_llm_bench.ui.results.protocols import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
)
from ollama_llm_bench.ui.results.tests.conftest import FakeEventBus, FakeResultGateway, make_run

_TOOLTIP_GATE_BUSY = (
    "Another inference activity is in flight; analysis can be generated when it finishes."
)


def _make_run_analysis_tab(
    gateway: FakeResultGateway, bus: FakeEventBus
) -> tuple[JudgeAnalysisTabView, JudgeAnalysisTabController]:
    controller = JudgeAnalysisTabController(gateway=gateway, bus=bus, clipboard=_NullClipboard())
    view = JudgeAnalysisTabView()
    view.bind_controller(controller)
    controller.bind(view)
    return view, controller


class _NullClipboard:
    def copy_text(self, text: str) -> None:  # pragma: no cover -- not exercised here
        raise NotImplementedError


# ---------------------------------------------------------------------------
# STORY-065-AC-1 / EC-RES-3
# ---------------------------------------------------------------------------


def test_full_narrative_and_metadata_rendered(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-1

    Covers: EC-RES-3

    Given a run whose ``run_analysis`` is set (by a same-session generation
    producing a very long narrative body), when the tab renders, then the
    full Markdown narrative is displayed with no length cap or truncation and
    the metadata line shows the generation time, duration, and the
    snapshot analysis-provider **display name** -- never the internal
    ``provider_id`` (a UUID4 in production; ``run_analysis_tab.md`` §5 and
    the app-wide rule forbid ever showing it to the user). ``provider_id`` is
    deliberately an opaque, non-name-shaped token here so a regression that
    interpolates the raw id back into the display string cannot hide behind
    an id that merely happens to look like a plausible name.
    """
    # Arrange
    run = make_run(1, status=RunStatus.COMPLETED)
    gateway = FakeResultGateway(runs=(run,))
    bus = FakeEventBus()
    view, controller = _make_run_analysis_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1)
    long_markdown = "\n\n".join(f"Paragraph {i} of the narrative body." for i in range(2000))
    provider_id = "prov-uuid-4f21"
    provider_name = "Anthropic (prod)"
    # Act
    dispatched = controller.regenerate_analysis(1, provider_id, "model-y")
    gateway.complete_regeneration(
        1,
        JudgeAnalysisGenerationResult(
            outcome=JudgeAnalysisGenerationOutcome.GENERATED,
            run_analysis_markdown=long_markdown,
            provider_name=provider_name,
        ),
    )
    # Assert
    assert dispatched
    narrative_body = cast(
        "QTextBrowser", view.findChild(QTextBrowser, "run_analysis_tab.narrative_body")
    )
    rendered_text = narrative_body.toPlainText()
    assert "Paragraph 0 of the narrative body." in rendered_text
    assert "Paragraph 1999 of the narrative body." in rendered_text
    metadata_label = cast("QLabel", view.findChild(QLabel, "run_analysis_tab.metadata_line"))
    metadata_text = metadata_label.text()
    assert "model: Anthropic (prod) / model-y" in metadata_text
    assert "Generated" in metadata_text
    assert provider_id not in metadata_text


def test_metadata_line_falls_back_to_bare_model_name_without_provider_name(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-065-AC-1

    Covers: EC-RES-3

    Given a completed generation whose result carries no ``provider_name``
    (the adapter has not resolved one), when the metadata line renders, then
    it shows the bare model name alone -- with no fallback to the internal
    ``provider_id`` under any circumstance.
    """
    # Arrange
    run = make_run(1, status=RunStatus.COMPLETED)
    gateway = FakeResultGateway(runs=(run,))
    bus = FakeEventBus()
    view, controller = _make_run_analysis_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_context(run_id=1)
    provider_id = "prov-uuid-9a03"
    # Act
    dispatched = controller.regenerate_analysis(1, provider_id, "model-y")
    gateway.complete_regeneration(
        1,
        JudgeAnalysisGenerationResult(
            outcome=JudgeAnalysisGenerationOutcome.GENERATED,
            run_analysis_markdown="A short narrative.",
        ),
    )
    # Assert
    assert dispatched
    metadata_label = cast("QLabel", view.findChild(QLabel, "run_analysis_tab.metadata_line"))
    metadata_text = metadata_label.text()
    assert "model: model-y" in metadata_text
    assert "/" not in metadata_text.split("model: ", 1)[1]
    assert provider_id not in metadata_text


# ---------------------------------------------------------------------------
# STORY-065-AC-2 -- table-driven over the four tab states
# ---------------------------------------------------------------------------


def _post_setup_none(
    _gateway: FakeResultGateway, _bus: FakeEventBus, _controller: JudgeAnalysisTabController
) -> None:
    """No extra step -- the initial ``set_run_context`` render is asserted as-is."""


def _post_setup_generating(
    _gateway: FakeResultGateway, bus: FakeEventBus, _controller: JudgeAnalysisTabController
) -> None:
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(
            state=InferenceActivityState(
                current=InferenceActivity.JUDGE_ANALYSIS,
                context=InferenceActivityContext(
                    activity=InferenceActivity.JUDGE_ANALYSIS, started_at=0, run_id=1
                ),
            )
        ),
    )


def _post_setup_failed_no_prior(
    gateway: FakeResultGateway, _bus: FakeEventBus, controller: JudgeAnalysisTabController
) -> None:
    controller.regenerate_analysis(1, "provider-x", "model-y")
    gateway.complete_regeneration(
        1,
        JudgeAnalysisGenerationResult(
            outcome=JudgeAnalysisGenerationOutcome.FAILED,
            error_message="The analysis model could not be reached.",
        ),
    )


@pytest.mark.parametrize(
    ("run_status", "post_setup", "expected_message"),
    [
        (
            RunStatus.INCOMPLETE,
            _post_setup_none,
            "Run-level analysis is generated when the benchmark finishes.",
        ),
        (
            RunStatus.COMPLETED,
            _post_setup_none,
            "Run-level analysis was not requested for this run. Click Generate analysis to produce it now.",
        ),
        (RunStatus.COMPLETED, _post_setup_generating, "Generating run-level analysis..."),
        (
            RunStatus.COMPLETED,
            _post_setup_failed_no_prior,
            "Run-level analysis could not be generated. See the run log for details.",
        ),
    ],
    ids=["absent_running", "absent_not_requested", "generating", "failed_no_prior"],
)
def test_tab_state_per_condition(
    qtbot: QtBot,
    run_status: RunStatus,
    post_setup: Callable[[FakeResultGateway, FakeEventBus, JudgeAnalysisTabController], None],
    expected_message: str,
) -> None:
    """Proves: STORY-065-AC-2

    For each of the four tab states -- ``run_analysis`` absent on a still-running
    run, ``run_analysis`` absent on a finished run with no generation requested,
    a generation in flight for this run, and the most recent generation having
    failed with no prior narrative -- the body renders the state's specified
    empty-state message, with the narrative body hidden in every case.
    """
    # Arrange
    run = make_run(1, status=run_status)
    gateway = FakeResultGateway(runs=(run,))
    bus = FakeEventBus()
    view, controller = _make_run_analysis_tab(gateway, bus)
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1)
    # Act
    post_setup(gateway, bus, controller)
    # Assert
    empty_label = cast("QLabel", view.findChild(QLabel, "run_analysis_tab.empty_message"))
    narrative_body = cast(
        "QTextBrowser", view.findChild(QTextBrowser, "run_analysis_tab.narrative_body")
    )
    assert empty_label.text() == expected_message
    assert narrative_body.isVisible() is False


# ---------------------------------------------------------------------------
# STORY-065-AC-3 / EC-PROV-4e
# ---------------------------------------------------------------------------


def test_failed_regeneration_preserves_prior_narrative(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-3

    Covers: EC-PROV-4e

    Given a regeneration fails while a prior good narrative is stored, when
    the failure arrives, then the prior narrative stays rendered and
    ``run_analysis`` is not overwritten, with a soft error banner shown above
    the body.
    """
    # Arrange
    run = msgspec.structs.replace(
        make_run(1, status=RunStatus.COMPLETED), run_analysis="Prior good narrative."
    )
    gateway = FakeResultGateway(runs=(run,))
    bus = FakeEventBus()
    view, controller = _make_run_analysis_tab(gateway, bus)
    qtbot.addWidget(view)
    view.show()
    qtbot.wait(0)
    controller.set_run_context(run_id=1)
    # Act
    controller.regenerate_analysis(1, "provider-x", "model-y")
    gateway.complete_regeneration(
        1,
        JudgeAnalysisGenerationResult(
            outcome=JudgeAnalysisGenerationOutcome.FAILED,
            error_message="Timed out waiting for a response.",
        ),
    )
    # Assert
    assert gateway.get_run(1).run_analysis == "Prior good narrative."
    narrative_body = cast(
        "QTextBrowser", view.findChild(QTextBrowser, "run_analysis_tab.narrative_body")
    )
    error_banner = cast("QLabel", view.findChild(QLabel, "run_analysis_tab.error_banner"))
    assert "Prior good narrative." in narrative_body.toPlainText()
    assert narrative_body.isVisible() is True
    assert error_banner.isVisible() is True
    assert error_banner.text() == "Timed out waiting for a response."


# ---------------------------------------------------------------------------
# STORY-065-AC-4 / EC-RUN-12 / EC-RUN-14
# ---------------------------------------------------------------------------


def test_generate_button_label_and_gate_binding(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-4

    Covers: EC-RUN-12, EC-RUN-14

    Given the selected run is terminal with completed results and the
    inference gate is ``IDLE``, when the tab renders the toolbar, then the
    Generate/Regenerate button is enabled with the label matching whether
    ``run_analysis`` is present; and when a ``_inference_activity_changed``
    reports the gate held by another activity, then the button is disabled
    with the matching tooltip (EC-RUN-12), re-enabling once the gate returns
    to ``IDLE`` -- the same signal shape a watchdog auto-release produces
    (EC-RUN-14).
    """
    # Arrange
    run_without_analysis = make_run(1, status=RunStatus.COMPLETED)
    run_with_analysis = msgspec.structs.replace(
        make_run(2, status=RunStatus.COMPLETED), run_analysis="Existing narrative."
    )
    gateway = FakeResultGateway(runs=(run_without_analysis, run_with_analysis))
    gateway.set_results(1, (make_result(result_id=1, run_id=1, status=ResultStatus.COMPLETED),))
    gateway.set_results(2, (make_result(result_id=2, run_id=2, status=ResultStatus.COMPLETED),))
    bus = FakeEventBus()
    view, controller = _make_run_analysis_tab(gateway, bus)
    qtbot.addWidget(view)
    controller.set_run_terminal_state(is_terminal=True)
    controller.set_run_context(run_id=1)
    generate_button = cast(
        "QPushButton", view.findChild(QPushButton, "run_analysis_tab.generate_button")
    )
    # Assert: no run_analysis yet -- "Generate analysis", enabled
    assert generate_button.text() == "Generate analysis"
    assert generate_button.isEnabled() is True
    # Act: switch to the run that already has a narrative
    controller.set_run_context(run_id=2)
    # Assert: label switches to "Regenerate analysis", still enabled
    assert generate_button.text() == "Regenerate analysis"
    assert generate_button.isEnabled() is True
    # Act: the gate is acquired by another activity (not JUDGE_ANALYSIS)
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(
            state=InferenceActivityState(
                current=InferenceActivity.PROVIDER_TEST,
                context=InferenceActivityContext(
                    activity=InferenceActivity.PROVIDER_TEST, started_at=0
                ),
            )
        ),
    )
    # Assert: disabled with the gate-busy tooltip
    assert generate_button.isEnabled() is False
    assert generate_button.toolTip() == _TOOLTIP_GATE_BUSY
    # Act: the gate returns to IDLE (mirrors a watchdog auto-release, EC-RUN-14)
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(state=InferenceActivityState(current=InferenceActivity.IDLE)),
    )
    # Assert: re-enabled
    assert generate_button.isEnabled() is True
