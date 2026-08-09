"""STORY-118 -- the Generate Analysis dialog against the real ``QtEventBusDeliverer``.

Lives here rather than in ``ui/common_dialogs/tests/`` because it wires a real adapter
(``QtEventBusDeliverer``), which the UI gate-access architecture scan forbids in a colocated
``ui/**/tests/`` file.
"""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.domain import BenchmarkRun
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    SIGNAL_INFERENCE_PROGRESS,
    SIGNAL_RUN_ANALYSIS_RECEIVED,
    EventBus,
)
from ollama_llm_bench.ui.common_dialogs import (
    GenerateAnalysisCollaborators,
    make_generate_analysis_dialog,
)
from ollama_llm_bench.ui.common_dialogs._internal.generate_analysis_view import (
    GenerateAnalysisDialog,
)

_HANDLER_BY_SIGNAL = {
    SIGNAL_INFERENCE_ACTIVITY_CHANGED: "_on_inference_activity_changed",
    SIGNAL_INFERENCE_PROGRESS: "_on_inference_progress",
    SIGNAL_RUN_ANALYSIS_RECEIVED: "_on_run_analysis_received",
}


def test_dialog_constructs_against_the_real_event_bus(
    qtbot: QtBot,
    canned_run: BenchmarkRun,
    make_generate_analysis_collaborators: Callable[[EventBus], GenerateAnalysisCollaborators],
) -> None:
    """Proves: STORY-118-AC-1

    Constructing the dialog with a real ``QtEventBusDeliverer`` completes and raises no
    icontract ``ViolationError``. Before this story the three owner-less ``subscribe``
    calls tripped the deliverer's ``owner is not None`` precondition (08-J §2) and
    crashed the process the moment a user clicked Generate analysis.
    """
    # Arrange
    bus = make_qt_event_bus_deliverer()

    # Act
    dialog = make_generate_analysis_dialog(
        run=canned_run, collaborators=make_generate_analysis_collaborators(bus)
    )
    qtbot.addWidget(dialog)

    # Assert
    assert dialog is not None


@pytest.mark.parametrize("signal_name", sorted(_HANDLER_BY_SIGNAL))
def test_dialog_subscriptions_are_bound_to_dialog_lifetime(
    qtbot: QtBot,
    mocker: MockerFixture,
    signal_name: str,
    canned_run: BenchmarkRun,
    make_generate_analysis_collaborators: Callable[[EventBus], GenerateAnalysisCollaborators],
) -> None:
    """Proves: STORY-118-AC-2

    Each subscription follows the dialog's own lifetime: the handler runs while the dialog
    is alive and does not run once it is destroyed, without any explicit ``cancel()`` call.

    The handler is replaced on the CLASS before construction, because ``__init__`` captures
    ``self._on_...`` at subscribe time -- patching the instance afterwards would not reach
    the already-captured callable.

    Deliberately not registered with ``qtbot.addWidget``: this test destroys the dialog
    itself, and pytest-qt's teardown would then call ``close()`` on a freed C++ object.
    """
    # Arrange
    recorder = mocker.patch.object(
        GenerateAnalysisDialog, _HANDLER_BY_SIGNAL[signal_name], autospec=False
    )
    bus = make_qt_event_bus_deliverer()
    dialog = make_generate_analysis_dialog(
        run=canned_run, collaborators=make_generate_analysis_collaborators(bus)
    )

    # Act -- while alive
    bus.emit(signal_name, object())
    qtbot.waitUntil(lambda: recorder.call_count == 1, timeout=1000)
    calls_while_alive = recorder.call_count

    # Act -- after destruction, with no explicit cancel()
    # `destroyed` is watched by hand rather than with `qtbot.waitSignal`, whose cleanup
    # disconnects from the very object that just died and warns when it cannot.
    destroyed: list[bool] = []
    dialog.destroyed.connect(lambda *_args: destroyed.append(True))
    dialog.deleteLater()
    qtbot.waitUntil(lambda: bool(destroyed), timeout=1000)
    bus.emit(signal_name, object())
    qtbot.wait(50)

    # Assert
    assert (calls_while_alive, recorder.call_count) == (1, 1)
