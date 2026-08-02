"""Unit tests for ``_internal/close_handler.py`` (STORY-053-AC-5, STORY-053-AC-6,
EC-RUN-4, EC-WS-2).

Per the module docstring on ``CloseHandler``, a real modal ``QMessageBox`` is never driven in
these tests -- ``CloseHandler._confirm_running_benchmark_quit`` and
``CloseHandler._confirm_unsaved_buffers`` are monkeypatched instead.
"""

from collections.abc import Callable

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
    (
        "running_confirm_result",
        "buffers_confirm_result",
        "expected_call_order",
        "expected_quit_calls",
        "expected_save_all_calls",
    ),
    [
        (False, "save_all", ["confirm_running_benchmark_quit"], 0, 0),
        (True, "cancel", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 0, 0),
        (True, "discard_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 0),
        (True, "save_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 1),
    ],
    ids=[
        "cancel_at_running_prompt",
        "cancel_at_buffers_prompt",
        "confirm_discard_all_quits_without_saving",
        "confirm_save_all_saves_then_quits",
    ],
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
    """Proves: STORY-053-AC-6, STORY-080-AC-1, STORY-080-AC-2 (EC-M-6, EC-M-7)

    Given both a non-terminal run and one or more dirty task buffers,
    when the user requests a quit,
    then the running-benchmark confirmation is shown before the unsaved-buffer confirmation,
    a cancel at either step aborts the entire quit (EC-WS-2, EC-M-7),
    and choosing "Save all" invokes the save-all hook exactly once before the quit proceeds,
    while "Discard all" never invokes it.
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
    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        dirty_buffer_count=lambda: 3,
        save_all_buffers=lambda: save_all_calls.append(None),
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
