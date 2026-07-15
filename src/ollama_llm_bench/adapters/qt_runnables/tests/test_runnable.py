"""Unit tests for ``_BackendUnitRunnable`` and ``QtTaskRunner`` construction (STORY-041).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter — fixed ``maxThreadCount = 4``), §5 (the
``CancellationToken`` is carried through unchanged).

``test_cancellation_token_is_passed_into_callable_unchanged`` calls ``run()`` directly as a
plain method — no ``QThreadPool`` involved, so no ``QApplication`` is required for that test.
``test_pool_max_thread_count_is_four`` constructs the real ``QtTaskRunner`` via the public
factory, which requires a live ``QApplication`` (provided by the ``qtbot`` fixture).
"""

from concurrent.futures import Future
from typing import TYPE_CHECKING
from unittest.mock import Mock

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_runnables._internal.runnable import _BackendUnitRunnable
from ollama_llm_bench.adapters.qt_runnables._internal.task_runner import QtTaskRunner
from ollama_llm_bench.adapters.qt_runnables.api import make_qt_task_runner
from ollama_llm_bench.backend.concurrency import CancellationToken

if TYPE_CHECKING:
    from ollama_llm_bench.backend.concurrency.protocols import TaskRunner

_UNIT_RESULT_VALUE = 7
_EXPECTED_MAX_THREAD_COUNT = 4


def test_cancellation_token_is_passed_into_callable_unchanged() -> None:
    """Proves: STORY-041-AC-3

    Given a submitted unit,
    when the runnable invokes the backend callable,
    then the same ``CancellationToken`` passed to ``submit`` is passed into the callable
    unchanged — proven here by asserting ``raise_if_cancelled`` was called exactly once on
    that exact token instance (identity, not just equality).
    """
    # Arrange
    token = Mock(spec=CancellationToken)
    future: Future[int] = Future()
    received_tokens: list[CancellationToken] = []

    def _fn() -> int:
        received_tokens.append(token)
        return _UNIT_RESULT_VALUE

    runnable = _BackendUnitRunnable(fn=_fn, token=token, future=future)

    # Act
    runnable.run()

    # Assert
    token.raise_if_cancelled.assert_called_once()
    assert received_tokens == [token]
    assert received_tokens[0] is token


def test_pool_max_thread_count_is_four(qtbot: QtBot) -> None:
    """Proves: STORY-041-AC-4

    Given the ``TaskRunner`` is constructed,
    then its underlying ``QThreadPool`` reports ``maxThreadCount == 4`` — the fixed pool
    size configured once at construction.
    """
    # Arrange / Act
    runner: TaskRunner[int] = make_qt_task_runner()

    # Assert
    assert isinstance(runner, QtTaskRunner)
    assert runner._pool.maxThreadCount() == _EXPECTED_MAX_THREAD_COUNT
