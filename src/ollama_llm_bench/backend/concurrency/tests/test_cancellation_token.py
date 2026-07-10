"""Tests proving STORY-006-AC-2 through STORY-006-AC-5: ``CancellationToken``.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§5 (the ``CancellationToken``); ``docs/v3_specification/11_Services_and_Algorithms/
16_CONCURRENCY_MODEL.md`` §6.3 (the single ``CancellationToken``).
"""

import threading

import pytest

from ollama_llm_bench.backend.concurrency import make_cancellation_token
from ollama_llm_bench.backend.domain.models import CancelLevel, CancelReason
from ollama_llm_bench.backend.errors import TaskCancelledError
from ollama_llm_bench.backend.infra.protocols import Clock

_WAIT_TIMEOUT_SECONDS = 5.0
_SHORT_TIMEOUT_SECONDS = 0.05


def test_cancellation_level_is_monotonic_never_downgraded(fake_clock: Clock) -> None:
    """Proves: STORY-006-AC-2

    A fresh ``CancellationToken`` starts at level ``NONE``; a soft cancel
    transitions it to ``SOFT``; a subsequent hard cancel transitions it to
    ``HARD``; a further soft cancel call after reaching ``HARD`` leaves the
    level at ``HARD`` (never downgraded).
    """
    # Arrange
    token = make_cancellation_token(clock=fake_clock)

    # Assert — starts at NONE
    assert token.snapshot() == (CancelLevel.NONE, None)

    # Act — soft cancel
    token.cancel(reason=CancelReason.USER_PAUSE, hard=False)

    # Assert — transitions to SOFT
    assert token.snapshot() == (CancelLevel.SOFT, CancelReason.USER_PAUSE)

    # Act — hard cancel
    token.cancel(reason=CancelReason.USER_STOP, hard=True)

    # Assert — transitions to HARD
    assert token.snapshot() == (CancelLevel.HARD, CancelReason.USER_STOP)

    # Act — a further soft cancel after HARD
    token.cancel(reason=CancelReason.AUTO_PAUSE, hard=False)

    # Assert — level and reason stay at the HARD cancel, never downgraded
    assert token.snapshot() == (CancelLevel.HARD, CancelReason.USER_STOP)


def test_raise_if_cancelled_and_level_query_properties(fake_clock: Clock) -> None:
    """Proves: STORY-006-AC-3

    Before any ``cancel()`` call, ``raise_if_cancelled()`` returns normally
    and both ``is_cancelled``/``is_hard_cancelled`` are ``False``. After a
    soft cancel, ``raise_if_cancelled()`` raises ``TaskCancelledError`` and
    ``is_cancelled`` is ``True`` while ``is_hard_cancelled`` stays ``False``.
    After a hard cancel, both are ``True``.
    """
    # Arrange
    token = make_cancellation_token(clock=fake_clock)

    # Assert — pre-cancellation state
    is_cancelled_before: bool = token.is_cancelled
    is_hard_cancelled_before: bool = token.is_hard_cancelled
    assert is_cancelled_before is False
    assert is_hard_cancelled_before is False
    token.raise_if_cancelled()  # must not raise

    # Act — soft cancel
    token.cancel(reason=CancelReason.USER_PAUSE, hard=False)

    # Assert — SOFT: is_cancelled True, is_hard_cancelled False, raises
    is_cancelled_after_soft: bool = token.is_cancelled
    is_hard_cancelled_after_soft: bool = token.is_hard_cancelled
    assert is_cancelled_after_soft is True
    assert is_hard_cancelled_after_soft is False
    with pytest.raises(TaskCancelledError):
        token.raise_if_cancelled()

    # Act — hard cancel
    token.cancel(reason=CancelReason.USER_STOP, hard=True)

    # Assert — HARD: both True, still raises
    is_cancelled_after_hard: bool = token.is_cancelled
    is_hard_cancelled_after_hard: bool = token.is_hard_cancelled
    assert is_cancelled_after_hard is True
    assert is_hard_cancelled_after_hard is True
    with pytest.raises(TaskCancelledError):
        token.raise_if_cancelled()


def test_wait_returns_early_on_cross_thread_cancel(fake_clock: Clock) -> None:
    """Proves: STORY-006-AC-4

    ``wait(timeout)`` blocks for up to ``timeout`` seconds but returns early,
    before the timeout elapses, as soon as another thread calls ``cancel()``;
    called on an already-cancelled token it returns immediately.
    """
    # Arrange
    token = make_cancellation_token(clock=fake_clock)
    waiter_result: list[bool] = []

    def _wait_then_record() -> None:
        waiter_result.append(token.wait(timeout=_WAIT_TIMEOUT_SECONDS))

    waiter_thread = threading.Thread(target=_wait_then_record)

    # Act — start waiting on one thread, cancel from this (the "main") thread
    waiter_thread.start()
    token.cancel(reason=CancelReason.USER_PAUSE)
    waiter_thread.join(timeout=_WAIT_TIMEOUT_SECONDS)

    # Assert — the waiter woke up early, reporting cancellation
    assert waiter_thread.is_alive() is False
    assert waiter_result == [True]

    # Act / Assert — an already-cancelled token returns immediately
    assert token.wait(timeout=_SHORT_TIMEOUT_SECONDS) is True


def test_hard_cancel_hooks_invoked_once_removable_and_isolate_failures(
    fake_clock: Clock,
) -> None:
    """Proves: STORY-006-AC-5

    ``add_hard_cancel_hook`` registers a hook that a subsequent hard cancel
    invokes exactly once; ``remove_hard_cancel_hook`` prevents a hook from
    being invoked by a later hard cancel; a hook that raises is caught inside
    the token so it does not prevent the other hooks from running or prevent
    ``cancel()`` from returning to its caller.
    """
    # Arrange
    token = make_cancellation_token(clock=fake_clock)
    first_hook_calls: list[str] = []
    second_hook_calls: list[str] = []
    removed_hook_calls: list[str] = []

    def _first_hook() -> None:
        first_hook_calls.append("called")

    def _raising_hook() -> None:
        raise RuntimeError("hook blew up")

    def _second_hook() -> None:
        second_hook_calls.append("called")

    def _removed_hook() -> None:
        removed_hook_calls.append("called")

    token.add_hard_cancel_hook(_first_hook)
    token.add_hard_cancel_hook(_raising_hook)
    token.add_hard_cancel_hook(_second_hook)
    token.add_hard_cancel_hook(_removed_hook)
    token.remove_hard_cancel_hook(_removed_hook)

    # Act — cancel() must return normally despite the raising hook
    token.cancel(reason=CancelReason.USER_STOP, hard=True)

    # Assert — every still-registered hook ran exactly once; the removed
    # hook never ran; a second hard cancel does not re-invoke anything.
    assert first_hook_calls == ["called"]
    assert second_hook_calls == ["called"]
    assert removed_hook_calls == []

    token.cancel(reason=CancelReason.APP_SHUTDOWN, hard=True)
    assert first_hook_calls == ["called"]
    assert second_hook_calls == ["called"]


def test_add_hard_cancel_hook_invokes_immediately_when_already_hard_cancelled(
    fake_clock: Clock,
) -> None:
    """Proves: STORY-006-AC-5

    Registering a hook on a token that is already hard-cancelled invokes it
    immediately rather than silently registering it for an event that has
    already happened.
    """
    # Arrange
    token = make_cancellation_token(clock=fake_clock)
    token.cancel(reason=CancelReason.USER_STOP, hard=True)
    late_hook_calls: list[str] = []

    def _late_hook() -> None:
        late_hook_calls.append("called")

    # Act
    token.add_hard_cancel_hook(_late_hook)

    # Assert
    assert late_hook_calls == ["called"]
