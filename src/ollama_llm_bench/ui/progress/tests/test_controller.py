"""Colocated controller tests for ``ui/progress/`` (STORY-058-AC-3, EC-RUN-2, SPEC-098).

Per ``ui/main_window/_internal/close_handler.py``'s test-precedent docstring, a real
modal ``QMessageBox`` is never driven in these tests -- ``confirm_stop`` is
monkeypatched at its point of use (``ollama_llm_bench.ui.progress._internal.controller``)
instead.
"""

from typing import cast

from PySide6.QtWidgets import QLabel
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import BenchmarkRun, RunMode, RunStatus
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_PAUSED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_RESUMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_STAGE_CHANGED,
    RunFailedEvent,
    RunFinishedEvent,
    RunIdChangedEvent,
    RunPausedEvent,
    RunRenamedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStoppedEvent,
    StageChangedEvent,
)
from ollama_llm_bench.backend.log_formatting.testing import FakeLogFormatter
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.progress._internal import controller as controller_module
from ollama_llm_bench.ui.progress._internal.controller import (
    STATE_EMPTY,
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPING,
    STATE_VIEWING_PAST_RUN,
    ProgressController,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import RunStage
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus


def _run_started_event(run_id: int = 1) -> RunStartedEvent:
    return RunStartedEvent(
        run_id=run_id,
        run_name="Run 1",
        run_mode=RunMode.TASKS,
        started_at="2026-01-01T00:00:00Z",
        total_tasks=10,
        test_targets=(("prov-1", "model-1"),),
    )


def _make_run(*, run_id: int = 1, status: RunStatus) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name="Run 1",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=RunMode.TASKS,
        status=status,
        total_tasks=10,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
    )


def _make_bound_controller(
    *, gateway: FakeProgressGateway, event_bus: FakeEventBus, qtbot: QtBot
) -> tuple[ProgressController, ProgressView]:
    view = ProgressView()
    qtbot.addWidget(view)
    controller = ProgressController(gateway=gateway, event_bus=event_bus, reconcile_timeout_ms=80)
    controller.bind(view)
    return controller, view


def test_stop_requires_confirmation_before_stop_run(
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-058-AC-3

    Given the run is executing, when the user clicks Stop, then the Stop
    confirmation modal is shown before any pipeline call, and only on Confirm
    is `ProgressGateway.stop_run(...)` invoked. Declining leaves the run
    running with no `stop_run` call (EC-RUN-2: a click that does not commit
    never disturbs the in-flight task).
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    monkeypatch.setattr(controller_module, "confirm_stop", lambda *, parent: False)

    # Act
    view.stop_clicked.emit()

    # Assert
    assert fake_gateway.recorded_stop_run_reasons == []

    # Act -- now confirm
    monkeypatch.setattr(controller_module, "confirm_stop", lambda *, parent: True)
    view.stop_clicked.emit()

    # Assert
    assert fake_gateway.recorded_stop_run_reasons == [None]

    # Cleanup -- settle the SPEC-098 draining timer this confirmed click armed
    # so it cannot fire during a later, unrelated test's event-loop pump.
    fake_event_bus.emit(
        SIGNAL_RUN_STOPPED,
        RunStoppedEvent(run_id=1, stopped_at="x", completed_tasks=0, total_tasks=10),
    )


def test_pause_click_requests_pause_and_never_calls_stop(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-3

    Covers EC-RUN-2. A Pause click calls `ProgressGateway.pause_run()` exactly once; it never
    calls `stop_run` and never disturbs the in-flight task directly
    (widget-level: it only requests the pause and waits for `_run_paused`).
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())

    # Act
    view.pause_resume_clicked.emit()

    # Assert
    assert fake_gateway.recorded_pause_run_calls == 1
    assert fake_gateway.recorded_stop_run_reasons == []

    # Cleanup -- settle the SPEC-098 draining timer this click armed so it
    # cannot fire during a later, unrelated test's event-loop pump.
    fake_event_bus.emit(
        SIGNAL_RUN_PAUSED,
        RunPausedEvent(run_id=1, paused_at="x", completed_tasks=0, total_tasks=10),
    )


@pytest.mark.parametrize("settle_via", ["terminal_event", "bounded_timeout"])
def test_pause_draining_settles_via_event_or_timeout(
    settle_via: str, qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: SPEC-098

    On entering the Pausing draining sub-state, a bounded reconciliation
    timer is armed; whichever settles first -- the `_run_paused` event or the
    timeout -- decides the outcome, and the other settlement is a no-op
    (first-callback-wins). Both settlements land on `STATE_PAUSED`: the
    timeout path reconciles a lost `_run_paused` event to Paused (not a
    generic Running/ViewingPastRun fallback) because `is_run_active()` still
    reports the run active and the draining intent was a Pause.
    """
    # Arrange
    controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    fake_gateway.set_run_header(_make_run(status=RunStatus.INCOMPLETE))
    fake_gateway.set_is_run_active(active=True)

    # Act
    view.pause_resume_clicked.emit()
    if settle_via == "terminal_event":
        fake_event_bus.emit(
            SIGNAL_RUN_PAUSED,
            RunPausedEvent(run_id=1, paused_at="x", completed_tasks=1, total_tasks=10),
        )
        qtbot.wait(150)
    else:
        qtbot.wait(150)

    # Assert -- both settlement paths land on Paused (see docstring)
    assert controller._state == STATE_PAUSED


@pytest.mark.parametrize("settle_via", ["terminal_event", "bounded_timeout"])
def test_stop_draining_settles_via_event_or_timeout(
    settle_via: str,
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: SPEC-098

    On entering the Stopping draining sub-state, a bounded reconciliation
    timer is armed; whichever settles first -- the `_run_stopped` event or
    the timeout (reconciled via `is_run_active()` + `run_header().status`) --
    decides the outcome, and the other settlement is a no-op.
    """
    # Arrange
    controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    monkeypatch.setattr(controller_module, "confirm_stop", lambda *, parent: True)
    fake_gateway.set_run_header(_make_run(status=RunStatus.STOPPED))
    fake_gateway.set_is_run_active(active=False)

    # Act
    view.stop_clicked.emit()
    assert controller._state == STATE_STOPPING
    if settle_via == "terminal_event":
        fake_event_bus.emit(
            SIGNAL_RUN_STOPPED,
            RunStoppedEvent(run_id=1, stopped_at="x", completed_tasks=1, total_tasks=10),
        )
        qtbot.wait(150)
    else:
        qtbot.wait(150)

    # Assert
    assert controller._state == STATE_VIEWING_PAST_RUN


def test_run_resumed_transitions_to_running(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_resumed` transitions the widget state back to "Running" (Pause/Stop
    re-enabled, matching `select_header`'s "Running" row).
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    fake_event_bus.emit(
        SIGNAL_RUN_PAUSED,
        RunPausedEvent(run_id=1, paused_at="x", completed_tasks=0, total_tasks=10),
    )

    # Act
    fake_event_bus.emit(
        SIGNAL_RUN_RESUMED,
        RunResumedEvent(run_id=1, resumed_at="x", completed_tasks=0, total_tasks=10),
    )

    # Assert
    assert controller._state == STATE_RUNNING


def test_run_finished_transitions_to_viewing_past_run(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_finished` transitions the widget to "ViewingPastRun" (terminal:
    rename pencil hidden, Pause/Stop disabled) and settles any pending
    reconciliation.
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())

    # Act
    fake_event_bus.emit(
        SIGNAL_RUN_FINISHED,
        RunFinishedEvent(
            run_id=1,
            finished_at="x",
            run_status=RunStatus.COMPLETED,
            total_tasks=10,
            completed_tasks=10,
            counts_by_result_status={},
            total_elapsed_ms=1000,
        ),
    )

    # Assert
    assert controller._state == STATE_VIEWING_PAST_RUN


def test_run_failed_transitions_to_viewing_past_run(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_failed` transitions the widget to "ViewingPastRun" and settles any
    pending reconciliation.
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())

    # Act
    fake_event_bus.emit(
        SIGNAL_RUN_FAILED,
        RunFailedEvent(
            run_id=1,
            failed_at="x",
            error_kind="internal",  # type: ignore[arg-type]  # opaque str accepted by ErrorKind's StrEnum at runtime
            error_message="boom",
            completed_tasks=1,
            total_tasks=10,
        ),
    )

    # Assert
    assert controller._state == STATE_VIEWING_PAST_RUN


def test_run_renamed_updates_run_name_only_for_matching_run(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_renamed` updates the displayed run name only when the event's
    `run_id` matches the run currently displayed; a rename of a different
    run is ignored.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event(run_id=1))
    view.show()

    # Act -- a rename of an unrelated run is ignored
    fake_event_bus.emit(SIGNAL_RUN_RENAMED, RunRenamedEvent(run_id=99, new_name="Other Run"))
    label = cast("QLabel", view.findChild(QLabel, "progress.header.run_name"))
    assert label.text() == "Run 1"

    # Act -- a rename of the displayed run updates the header
    fake_event_bus.emit(SIGNAL_RUN_RENAMED, RunRenamedEvent(run_id=1, new_name="Renamed Run"))

    # Assert
    assert label.text() == "Renamed Run"


def test_run_id_changed_to_none_transitions_empty(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_id_changed` with `run_id=None` (selection cleared) transitions the
    widget to "Empty".
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )

    # Act
    fake_event_bus.emit(SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=None))

    # Assert
    assert controller._state == STATE_EMPTY


def test_run_id_changed_to_past_run_loads_its_header(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_id_changed` to a past run (while Empty) loads that run's header and
    transitions the widget to "ViewingPastRun".
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_gateway.set_run_header(_make_run(run_id=7, status=RunStatus.COMPLETED))

    # Act
    fake_event_bus.emit(SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=7))

    # Assert
    assert controller._state == STATE_VIEWING_PAST_RUN


def test_run_id_changed_ignored_while_a_run_is_active(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    `_run_id_changed` is ignored while the widget is displaying an active run
    (not Empty/ViewingPastRun) -- the live run stays on screen.
    """
    # Arrange
    controller, _view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())

    # Act
    fake_event_bus.emit(SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=None))

    # Assert -- state is unchanged (still the active run's state)
    assert controller._state != STATE_EMPTY


def test_rename_pencil_click_opens_rename_dialog(
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-058-AC-2

    Clicking the header rename pencil opens the Rename Run dialog
    (`ui.common_dialogs.make_rename_run_dialog`), seeded with the current
    run's metadata.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    fake_gateway.set_run(_make_run(status=RunStatus.INCOMPLETE))
    fake_dialog = mocker.Mock()
    make_dialog_mock = mocker.patch(
        "ollama_llm_bench.ui.common_dialogs.make_rename_run_dialog", return_value=fake_dialog
    )

    # Act
    view.rename_clicked.emit()

    # Assert
    make_dialog_mock.assert_called_once()
    fake_dialog.exec.assert_called_once()


def test_rename_pencil_click_is_a_noop_with_no_run_selected(
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-058-AC-2

    Clicking the rename pencil before any run has started (no `run_id`) is a
    no-op -- no dialog is constructed.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    make_dialog_mock = mocker.patch("ollama_llm_bench.ui.common_dialogs.make_rename_run_dialog")

    # Act
    view.rename_clicked.emit()

    # Assert
    make_dialog_mock.assert_not_called()


# -- Real-wiring badge coverage (defect fix: the badge must reflect the five
# terminal/paused RunStage values the pipeline never emits via _stage_changed) --

_TERMINAL_STAGE_CASES: list[tuple[str, object, RunStage]] = [
    (
        SIGNAL_RUN_PAUSED,
        RunPausedEvent(run_id=1, paused_at="x", completed_tasks=1, total_tasks=10),
        RunStage.PAUSED,
    ),
    (
        SIGNAL_RUN_STOPPED,
        RunStoppedEvent(run_id=1, stopped_at="x", completed_tasks=1, total_tasks=10),
        RunStage.STOPPED,
    ),
    (
        SIGNAL_RUN_FINISHED,
        RunFinishedEvent(
            run_id=1,
            finished_at="x",
            run_status=RunStatus.COMPLETED,
            total_tasks=10,
            completed_tasks=10,
            counts_by_result_status={},
            total_elapsed_ms=1000,
        ),
        RunStage.COMPLETED,
    ),
    (
        SIGNAL_RUN_FAILED,
        RunFailedEvent(
            run_id=1,
            failed_at="x",
            error_kind="internal",  # type: ignore[arg-type]  # opaque str accepted by ErrorKind's StrEnum at runtime
            error_message="boom",
            completed_tasks=1,
            total_tasks=10,
        ),
        RunStage.FAILED,
    ),
]


@pytest.mark.parametrize(
    ("signal_name", "terminal_event", "expected_stage"),
    _TERMINAL_STAGE_CASES,
    ids=[case[2].value for case in _TERMINAL_STAGE_CASES],
)
def test_badge_reflects_terminal_or_paused_stage_via_real_wiring(  # noqa: PLR0913  # one
    # parametrize table (3 columns) plus three independently-overridable fixtures
    signal_name: str,
    terminal_event: object,
    expected_stage: RunStage,
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-058-AC-1

    Constructed via the real `make_progress_widget` wiring (not by calling
    `view.apply_counters(...)` directly), firing the real bus events
    `_run_started` then a terminal/paused event drives the header's
    `StageBadgeWidget` -- read back through `ProgressView.stage_badge`, the
    real rendered widget -- to the matching `RunStage`. The backend `Phase`
    enum never emits these five values via `_stage_changed`; only
    `ProgressController` pushes them here on the matching terminal/paused
    event.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    widget = make_progress_widget(
        bus=fake_event_bus, gateway=fake_gateway, log_formatter=log_formatter
    )
    qtbot.addWidget(widget)
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())

    # Act
    fake_event_bus.emit(signal_name, terminal_event)

    # Assert
    assert cast("ProgressView", widget).stage_badge.stage == expected_stage


@pytest.mark.parametrize(
    ("live_stage_before_pause", "expected_resumed_stage"),
    [(None, RunStage.INITIALIZING), ("INFERENCE", RunStage.INFERENCE)],
    ids=["no-live-stage-observed-yet", "resumes-to-last-live-stage"],
)
def test_badge_resume_restores_live_stage_via_real_wiring(
    live_stage_before_pause: str | None,
    expected_resumed_stage: RunStage,
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-058-AC-1

    `_run_resumed`, fired through the real bus wiring, restores the badge --
    read back through `ProgressView.stage_badge` -- to the last-known live
    `_stage_changed` stage, or `RunStage.INITIALIZING` when the run paused
    before any stage-changed event arrived (state_machine.md §1).
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    widget = make_progress_widget(
        bus=fake_event_bus, gateway=fake_gateway, log_formatter=log_formatter
    )
    qtbot.addWidget(widget)
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    if live_stage_before_pause is not None:
        fake_event_bus.emit(
            SIGNAL_STAGE_CHANGED,
            StageChangedEvent(
                run_id=1, stage=live_stage_before_pause, stage_index=2, stage_count=5
            ),
        )
    fake_event_bus.emit(
        SIGNAL_RUN_PAUSED,
        RunPausedEvent(run_id=1, paused_at="x", completed_tasks=0, total_tasks=10),
    )

    # Act
    fake_event_bus.emit(
        SIGNAL_RUN_RESUMED,
        RunResumedEvent(run_id=1, resumed_at="x", completed_tasks=0, total_tasks=10),
    )

    # Assert
    assert cast("ProgressView", widget).stage_badge.stage == expected_resumed_stage


# -- Draining status line (description.md §3.4; SPEC-098) -------------------------


def test_pausing_draining_status_line_shown_and_cleared_on_run_paused(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-2

    Clicking Pause shows the exact `description.md` §3.4 draining status line
    ("Pausing — finishing the current call…"); the settling `_run_paused`
    event clears it.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    view.show()
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    status_label = cast("QLabel", view.findChild(QLabel, "progress.header.draining_status"))
    assert not status_label.isVisible()

    # Act
    view.pause_resume_clicked.emit()

    # Assert
    assert status_label.isVisible()
    assert status_label.text() == "Pausing — finishing the current call…"

    # Act -- settle
    fake_event_bus.emit(
        SIGNAL_RUN_PAUSED,
        RunPausedEvent(run_id=1, paused_at="x", completed_tasks=0, total_tasks=10),
    )

    # Assert
    assert not status_label.isVisible()


def test_stopping_draining_status_line_shown_and_cleared_on_run_stopped(
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-058-AC-2

    Confirming Stop shows the exact `description.md` §3.4 draining status
    line ("Stopping — cancelling the current call…"); the settling
    `_run_stopped` event clears it.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    view.show()
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    monkeypatch.setattr(controller_module, "confirm_stop", lambda *, parent: True)
    status_label = cast("QLabel", view.findChild(QLabel, "progress.header.draining_status"))

    # Act
    view.stop_clicked.emit()

    # Assert
    assert status_label.isVisible()
    assert status_label.text() == "Stopping — cancelling the current call…"

    # Act -- settle
    fake_event_bus.emit(
        SIGNAL_RUN_STOPPED,
        RunStoppedEvent(run_id=1, stopped_at="x", completed_tasks=0, total_tasks=10),
    )

    # Assert
    assert not status_label.isVisible()


def test_draining_status_line_clears_on_reconcile_timeout(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: SPEC-098

    The bounded reconciliation timeout clears the draining status line even
    when the terminal event never arrives, so the label cannot stick on
    "Pausing…" forever.
    """
    # Arrange
    _controller, view = _make_bound_controller(
        gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot
    )
    view.show()
    fake_event_bus.emit(SIGNAL_RUN_STARTED, _run_started_event())
    fake_gateway.set_run_header(_make_run(status=RunStatus.INCOMPLETE))
    fake_gateway.set_is_run_active(active=True)
    status_label = cast("QLabel", view.findChild(QLabel, "progress.header.draining_status"))

    # Act
    view.pause_resume_clicked.emit()
    assert status_label.isVisible()
    qtbot.wait(150)

    # Assert
    assert not status_label.isVisible()
