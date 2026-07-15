"""Integration tests for the Qt ``TaskRunner`` crossing a real ``QThreadPool`` worker-thread
boundary (STORY-041-AC-1, STORY-041-AC-2).

These submit real work onto a real ``QThreadPool`` and block on the returned
``concurrent.futures.Future``, so they belong in ``tests/integration/`` rather than the
module's colocated unit tests (``testing-standard-pyqt`` skill; ``07_TESTING_STANDARD.md``
layout) — a colocated unit test may only exercise the module in isolation, never a real
worker-thread crossing.
"""

import threading
from typing import TYPE_CHECKING

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_runnables import make_qt_task_runner
from ollama_llm_bench.backend.concurrency import make_cancellation_token
from ollama_llm_bench.backend.infra import make_system_clock

if TYPE_CHECKING:
    from concurrent.futures import Future

    from ollama_llm_bench.backend.concurrency.protocols import TaskRunner

_UNIT_RESULT_VALUE = 99
_FUTURE_TIMEOUT_S = 5.0


class _DistinctWorkerError(RuntimeError):
    """A distinguishing exception type raised by a submitted unit under test."""


def test_submit_completes_future_with_result_on_worker_thread(qtbot: QtBot) -> None:
    """Proves: STORY-041-AC-1

    Given a backend callable that returns a value,
    when it is submitted through the runnable and the returned ``Future.result()`` is
    read,
    then the result equals the callable's return value and the value was set on the
    worker thread — never inline on the calling thread.
    """
    # Arrange
    runner: TaskRunner[int] = make_qt_task_runner()
    token = make_cancellation_token(clock=make_system_clock())
    calling_thread_id = threading.get_ident()
    recorded_thread_ids: list[int] = []

    def _unit() -> int:
        recorded_thread_ids.append(threading.get_ident())
        return _UNIT_RESULT_VALUE

    # Act
    future: Future[int] = runner.submit(_unit, token=token)
    result = future.result(timeout=_FUTURE_TIMEOUT_S)

    # Assert
    assert result == _UNIT_RESULT_VALUE
    assert len(recorded_thread_ids) == 1
    assert recorded_thread_ids[0] != calling_thread_id


def test_submit_propagates_worker_exception_via_future(qtbot: QtBot) -> None:
    """Proves: STORY-041-AC-2

    Given a backend callable that raises an exception,
    when it is submitted and the returned ``Future.result()`` is read,
    then that exact exception is re-raised to the reader — captured on the ``Future``
    via ``set_exception``, never swallowed.
    """
    # Arrange
    runner: TaskRunner[int] = make_qt_task_runner()
    token = make_cancellation_token(clock=make_system_clock())

    def _failing_unit() -> int:
        raise _DistinctWorkerError("distinct worker failure")

    # Act
    future: Future[int] = runner.submit(_failing_unit, token=token)

    # Assert
    try:
        future.result(timeout=_FUTURE_TIMEOUT_S)
    except _DistinctWorkerError as exc:
        assert str(exc) == "distinct worker failure"
    else:
        raise AssertionError("expected _DistinctWorkerError to propagate from future.result()")
