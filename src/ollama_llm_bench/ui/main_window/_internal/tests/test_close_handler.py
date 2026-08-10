"""Unit tests for ``_internal/close_handler.py`` (STORY-053-AC-5, STORY-053-AC-6,
STORY-080-AC-1, STORY-080-AC-2, EC-RUN-4, EC-WS-2, EC-M-6, EC-M-7).

Per the module docstring on ``CloseHandler``, a real modal ``QMessageBox`` is never driven in
these tests -- ``CloseHandler._confirm_running_benchmark_quit`` and
``CloseHandler._confirm_unsaved_buffers`` are monkeypatched instead.
"""

from collections.abc import Callable
from typing import Final

import pytest

from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.backend.events import SIGNAL_RUN_STOPPED, RunStoppedEvent
from ollama_llm_bench.ui.main_window._internal.close_handler import CloseHandler
from ollama_llm_bench.ui.main_window._internal.tests.conftest import (
    FakeEventBus,
    FakeMainWindowGateway,
)


def _make_run_stopped_event() -> RunStoppedEvent:
    return RunStoppedEvent(
        run_id=1, stopped_at="2026-01-01T00:00:00Z", completed_tasks=1, total_tasks=2
    )


def _settle_via_run_stopped_event(
    *, event_bus: FakeEventBus, qtbot: object, shutdown_timeout_ms: int
) -> None:
    del qtbot, shutdown_timeout_ms
    event_bus.emit(SIGNAL_RUN_STOPPED, _make_run_stopped_event())


def _settle_via_bounded_timeout(
    *, event_bus: FakeEventBus, qtbot: object, shutdown_timeout_ms: int
) -> None:
    del event_bus
    qtbot.wait(shutdown_timeout_ms + 100)  # type: ignore[attr-defined]  # qtbot is untyped


_SETTLE_STRATEGIES: dict[str, Callable[..., None]] = {
    "run_stopped_event": _settle_via_run_stopped_event,
    "bounded_timeout": _settle_via_bounded_timeout,
}


@pytest.mark.parametrize(
    "settle_via",
    ["run_stopped_event", "bounded_timeout"],
    ids=["run_stopped_event", "bounded_timeout"],
)
def test_quit_with_running_run_confirms_and_shuts_down(  # noqa: PLR0913  # one
    # parametrize axis (`settle_via`) plus five independently-overridable fixtures
    settle_via: str,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    qtbot: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-053-AC-5

    Given a run is non-terminal,
    when the user requests a quit and confirms the running-benchmark prompt,
    then ``MainWindowGateway.shutdown(timeout_ms)`` is called and the shell proceeds to quit
    once ``_run_stopped`` is delivered or the bounded timeout elapses -- whichever settles
    first -- and ``on_confirmed_quit`` fires exactly once even if both later occur (EC-RUN-4).
    """
    # Arrange
    gateway.set_run_active(True)
    monkeypatch.setattr(CloseHandler, "_confirm_running_benchmark_quit", staticmethod(lambda: True))
    confirmed_quit_calls: list[None] = []
    shutdown_timeout_ms = 80
    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        on_confirmed_quit=lambda: confirmed_quit_calls.append(None),
        shutdown_timeout_ms=shutdown_timeout_ms,
    )

    # Act
    close_handler.request_close()
    _SETTLE_STRATEGIES[settle_via](
        event_bus=event_bus, qtbot=qtbot, shutdown_timeout_ms=shutdown_timeout_ms
    )
    # Simulate the opposite settlement path racing in afterward -- the idempotency guard
    # must still allow at most one `on_confirmed_quit` call.
    close_handler._on_stopped(_make_run_stopped_event())
    close_handler._on_timeout()

    # Assert
    assert gateway.shutdown_calls == [shutdown_timeout_ms]
    assert len(confirmed_quit_calls) == 1


@pytest.mark.parametrize(
    ("running_confirm_result", "expected_shutdown_calls", "expected_quit_calls"),
    [
        (False, [], 0),
        (True, [80], 1),
    ],
    ids=[
        "cancel_abandons_quit_with_no_shutdown_request",
        "confirm_requests_shutdown_then_settles_and_quits",
    ],
)
def test_running_benchmark_confirmation_outcome_per_ac1_table(  # noqa: PLR0913  # one
    # parametrize axis plus five independently-overridable fixtures/expected values
    running_confirm_result: bool,  # noqa: FBT001  # parametrize tuple element
    expected_shutdown_calls: list[int],
    expected_quit_calls: int,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-080-AC-1

    Given a benchmark is running and no dirty task buffers, when the user requests a quit,
    then Cancel at the running-benchmark prompt abandons the quit -- no pipeline shutdown is
    requested and ``on_confirmed_quit`` never runs -- while Confirm requests a bounded
    pipeline shutdown with the configured timeout and the quit proceeds only after that wait
    settles (EC-M-6).
    """
    # Arrange
    gateway.set_run_active(True)
    monkeypatch.setattr(
        CloseHandler,
        "_confirm_running_benchmark_quit",
        staticmethod(lambda: running_confirm_result),
    )
    confirmed_quit_calls: list[None] = []
    shutdown_timeout_ms = 80
    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        on_confirmed_quit=lambda: confirmed_quit_calls.append(None),
        shutdown_timeout_ms=shutdown_timeout_ms,
    )

    # Act
    close_handler.request_close()
    quit_calls_before_settle = len(confirmed_quit_calls)
    event_bus.emit(SIGNAL_RUN_STOPPED, _make_run_stopped_event())

    # Assert
    assert quit_calls_before_settle == 0
    assert gateway.shutdown_calls == expected_shutdown_calls
    assert len(confirmed_quit_calls) == expected_quit_calls


_CONFIRMATION_TABLE_PARAMS: Final[tuple[str, str, str, str, str]] = (
    "running_confirm_result",
    "buffers_confirm_result",
    "expected_call_order",
    "expected_quit_calls",
    "expected_save_all_calls",
)
_CONFIRMATION_TABLE_ROWS: Final[list[tuple[bool, str, list[str], int, int]]] = [
    (False, "save_all", ["confirm_running_benchmark_quit"], 0, 0),
    (True, "cancel", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 0, 0),
    (True, "discard_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 0),
    (True, "save_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 1),
]
_CONFIRMATION_TABLE_IDS: Final[list[str]] = [
    "cancel_at_running_prompt",
    "cancel_at_buffers_prompt",
    "confirm_discard_all_quits_without_saving",
    "confirm_save_all_saves_then_quits",
]


def _assert_quit_confirmation_outcome(  # noqa: PLR0913  # nine collaborators/expected
    # values shared verbatim by STORY-053-AC-6's and STORY-080-AC-2's tests; grouping them
    # into a struct would only move the parameter count, not reduce it
    *,
    running_confirm_result: bool,
    buffers_confirm_result: str,
    expected_call_order: list[str],
    expected_quit_calls: int,
    expected_save_all_calls: int,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run one row of the running-benchmark + unsaved-buffers confirmation table.

    Shared by ``test_quit_with_running_run_and_dirty_buffers_confirms_in_order``
    (STORY-053-AC-6) and ``test_confirmation_paths_produce_documented_outcomes_per_ac2_table``
    (STORY-080-AC-2) -- both prove the identical sequence over the identical four-row table;
    only the traceability tag on each caller differs.
    """
    # Arrange
    gateway.set_run_active(True)
    call_order: list[str] = []

    def _confirm_running() -> bool:
        call_order.append("confirm_running_benchmark_quit")
        return running_confirm_result

    def _confirm_buffers(_self: CloseHandler) -> str:
        call_order.append("confirm_unsaved_buffers")
        return buffers_confirm_result

    monkeypatch.setattr(
        CloseHandler, "_confirm_running_benchmark_quit", staticmethod(_confirm_running)
    )
    monkeypatch.setattr(CloseHandler, "_confirm_unsaved_buffers", _confirm_buffers)
    confirmed_quit_calls: list[None] = []
    save_all_calls: list[None] = []

    def _save_all() -> tuple[str, ...]:
        """Record the call and report every buffer as saved (STORY-114's contract)."""
        save_all_calls.append(None)
        return ()

    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        dirty_buffer_count=lambda: 3,
        save_all_buffers=_save_all,
        on_confirmed_quit=lambda: confirmed_quit_calls.append(None),
        shutdown_timeout_ms=80,
    )

    # Act
    close_handler.request_close()
    event_bus.emit(SIGNAL_RUN_STOPPED, _make_run_stopped_event())

    # Assert
    assert call_order == expected_call_order
    assert len(confirmed_quit_calls) == expected_quit_calls
    assert len(save_all_calls) == expected_save_all_calls


@pytest.mark.parametrize(
    _CONFIRMATION_TABLE_PARAMS, _CONFIRMATION_TABLE_ROWS, ids=_CONFIRMATION_TABLE_IDS
)
def test_quit_with_running_run_and_dirty_buffers_confirms_in_order(  # noqa: PLR0913  # five
    # parametrize axes plus four independently-overridable fixtures
    running_confirm_result: bool,  # noqa: FBT001  # parametrize tuple element
    buffers_confirm_result: str,
    expected_call_order: list[str],
    expected_quit_calls: int,
    expected_save_all_calls: int,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-053-AC-6

    Given both a non-terminal run and one or more dirty task buffers,
    when the user requests a quit,
    then the running-benchmark confirmation is shown before the unsaved-buffer confirmation,
    a cancel at either step aborts the entire quit (EC-WS-2, EC-M-7),
    and choosing "Save all" invokes the save-all hook exactly once before the quit proceeds,
    while "Discard all" never invokes it.

    This test also exercises STORY-080-AC-2's confirmation-path table and the
    ``save_all_buffers`` hook it adds -- see
    ``test_confirmation_paths_produce_documented_outcomes_per_ac2_table``, which runs the same
    four rows under STORY-080-AC-2's own traceability tag through the shared
    ``_assert_quit_confirmation_outcome`` helper.
    """
    _assert_quit_confirmation_outcome(
        running_confirm_result=running_confirm_result,
        buffers_confirm_result=buffers_confirm_result,
        expected_call_order=expected_call_order,
        expected_quit_calls=expected_quit_calls,
        expected_save_all_calls=expected_save_all_calls,
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        monkeypatch=monkeypatch,
    )


@pytest.mark.parametrize(
    _CONFIRMATION_TABLE_PARAMS, _CONFIRMATION_TABLE_ROWS, ids=_CONFIRMATION_TABLE_IDS
)
def test_confirmation_paths_produce_documented_outcomes_per_ac2_table(  # noqa: PLR0913
    # five parametrize axes plus four independently-overridable fixtures
    running_confirm_result: bool,  # noqa: FBT001  # parametrize tuple element
    buffers_confirm_result: str,
    expected_call_order: list[str],
    expected_quit_calls: int,
    expected_save_all_calls: int,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-080-AC-2

    Given a quit is requested while a benchmark is running and the dirty-buffer count is
    non-zero, each confirmation path produces its documented outcome (EC-M-7): Cancel at the
    running-benchmark prompt abandons the quit before the unsaved-changes prompt is ever
    shown, which is also the proof that the running-benchmark prompt always comes first;
    Confirm followed by Cancel at the unsaved-changes prompt abandons the quit without
    invoking the save-all hook; Confirm followed by Discard All quits without invoking it;
    Confirm followed by Save All invokes it exactly once before the quit proceeds.
    """
    _assert_quit_confirmation_outcome(
        running_confirm_result=running_confirm_result,
        buffers_confirm_result=buffers_confirm_result,
        expected_call_order=expected_call_order,
        expected_quit_calls=expected_quit_calls,
        expected_save_all_calls=expected_save_all_calls,
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        monkeypatch=monkeypatch,
    )


def test_save_all_holds_the_quit_when_a_file_cannot_be_saved(
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-114-AC-3

    Given the user chooses "Save all" and one dirty file still holds a hard
    validation error, when save-all returns that file's name, then the quit is
    held -- on_confirmed_quit is never called -- and the file is reported.
    """
    # Arrange
    gateway.set_run_active(False)
    monkeypatch.setattr(CloseHandler, "_confirm_unsaved_buffers", lambda _self: "save_all")
    reported: list[tuple[str, ...]] = []
    monkeypatch.setattr(CloseHandler, "_report_unsaveable_files", staticmethod(reported.append))
    confirmed_quit_calls: list[None] = []
    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        dirty_buffer_count=lambda: 2,
        save_all_buffers=lambda: ("broken.yaml",),
        on_confirmed_quit=lambda: confirmed_quit_calls.append(None),
    )

    # Act
    close_handler.request_close()

    # Assert
    assert (confirmed_quit_calls, reported) == ([], [("broken.yaml",)])
