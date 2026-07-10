"""Tests proving STORY-006-AC-1: the ``TaskRunner`` Protocol and its inline test runner.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter).
"""

from typing import get_type_hints

import pytest

from ollama_llm_bench.backend.concurrency import make_cancellation_token, make_inline_task_runner
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import CancelReason
from ollama_llm_bench.backend.errors import TaskCancelledError
from ollama_llm_bench.backend.infra.protocols import Clock

_UNIT_RESULT_VALUE = 42


def test_task_runner_protocol_declares_exactly_submit() -> None:
    """Proves: STORY-006-AC-1

    ``TaskRunner`` is a ``typing.Protocol`` declaring exactly one member,
    ``submit(fn, *, token) -> Future[T]``.
    """
    # Assert
    protocol_members = [name for name in vars(TaskRunner) if not name.startswith("_")]
    assert protocol_members == ["submit"]
    submit_hints = get_type_hints(TaskRunner.submit)
    assert set(submit_hints.keys()) == {"fn", "token", "return"}


def test_inline_task_runner_executes_synchronously_and_resolves_future(
    fake_clock: Clock,
) -> None:
    """Proves: STORY-006-AC-1

    The inline test ``TaskRunner`` implementation executes ``fn`` synchronously
    on the calling thread and returns a resolved ``Future`` carrying the
    result; a unit that raises has its exception captured on the ``Future``
    instead of propagating out of ``submit()``.
    """
    # Arrange
    runner: TaskRunner[int] = make_inline_task_runner()
    token = make_cancellation_token(clock=fake_clock)
    calls: list[str] = []

    def _unit() -> int:
        calls.append("ran")
        return _UNIT_RESULT_VALUE

    # Act
    future = runner.submit(_unit, token=token)

    # Assert
    assert calls == ["ran"]  # executed synchronously, before submit() returned
    assert future.done()
    assert future.result() == _UNIT_RESULT_VALUE


def test_inline_task_runner_captures_worker_exception_on_future(fake_clock: Clock) -> None:
    """Proves: STORY-006-AC-1

    A unit callable raising an exception has that exception captured on the
    returned ``Future`` (via ``set_exception``), never raised directly out of
    ``submit()``.
    """
    # Arrange
    runner: TaskRunner[int] = make_inline_task_runner()
    token = make_cancellation_token(clock=fake_clock)

    def _failing_unit() -> int:
        raise ValueError("boom")

    # Act
    future = runner.submit(_failing_unit, token=token)

    # Assert
    assert future.done()
    with pytest.raises(ValueError, match="boom"):
        future.result()


def test_inline_task_runner_captures_pre_submission_cancellation_on_future(
    fake_clock: Clock,
) -> None:
    """Proves: STORY-006-AC-1

    A unit submitted with an already-cancelled token never runs ``fn`` and
    captures ``TaskCancelledError`` on the returned ``Future`` instead of
    raising it out of ``submit()``.
    """
    # Arrange
    runner: TaskRunner[int] = make_inline_task_runner()
    token = make_cancellation_token(clock=fake_clock)
    token.cancel(reason=CancelReason.USER_STOP, hard=True)
    calls: list[str] = []

    def _unit() -> int:
        calls.append("ran")
        return _UNIT_RESULT_VALUE

    # Act
    future = runner.submit(_unit, token=token)

    # Assert
    assert calls == []  # never ran — cancellation checked before fn
    assert future.done()
    with pytest.raises(TaskCancelledError):
        future.result()
