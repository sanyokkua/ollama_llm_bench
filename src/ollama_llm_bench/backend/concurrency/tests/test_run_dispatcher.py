"""Tests proving STORY-042's ``RunDispatcher`` seam and its inline test double.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§4a (the dispatcher thread, DD-38). This module's `RunDispatcher` Protocol and
`InlineRunDispatcher` are the scope-correction this story added to
`backend/concurrency/` and `backend/benchmark_pipeline/` so the real, persistent
`pipeline-dispatcher` thread is owned by `adapters/qt_benchmark_flow/` rather than
constructed ad hoc on every `start()`/`resume()` call.
"""

from typing import get_type_hints

from ollama_llm_bench.backend.concurrency import make_inline_run_dispatcher
from ollama_llm_bench.backend.concurrency.protocols import RunDispatcher


def test_run_dispatcher_protocol_declares_exactly_submit_and_shutdown() -> None:
    """Proves: STORY-042-AC-1

    ``RunDispatcher`` is a ``typing.Protocol`` declaring exactly
    ``submit(fn) -> None`` and ``shutdown(timeout_ms) -> None`` — the two
    operations the pipeline's lifecycle controller needs to hand its dispatch
    loop to a single, persistent, adapter-owned thread and later join it.
    """
    # Assert
    protocol_members = sorted(name for name in vars(RunDispatcher) if not name.startswith("_"))
    assert protocol_members == ["shutdown", "submit"]
    submit_hints = get_type_hints(RunDispatcher.submit)
    assert set(submit_hints.keys()) == {"fn", "return"}
    shutdown_hints = get_type_hints(RunDispatcher.shutdown)
    assert set(shutdown_hints.keys()) == {"timeout_ms", "return"}


def test_inline_run_dispatcher_runs_submitted_fn_synchronously() -> None:
    """Proves: STORY-042-AC-1

    The inline test ``RunDispatcher`` implementation runs a submitted
    callable immediately on the calling thread, before ``submit()`` returns —
    exactly the property that lets a `start()`/`resume()` test settle without
    a real background thread or a poll loop.
    """
    # Arrange
    dispatcher: RunDispatcher = make_inline_run_dispatcher()
    calls: list[str] = []

    def _dispatch_loop() -> None:
        calls.append("ran")

    # Act
    dispatcher.submit(_dispatch_loop)

    # Assert
    assert calls == ["ran"]


def test_inline_run_dispatcher_shutdown_is_a_no_op() -> None:
    """Proves: STORY-042-AC-3

    ``shutdown()`` on the inline test double never raises and returns
    immediately — every submitted unit has already completed synchronously
    by the time ``shutdown()`` could ever be called, so there is nothing left
    to wait for or join.
    """
    # Arrange
    dispatcher: RunDispatcher = make_inline_run_dispatcher()

    # Act / Assert (no exception)
    dispatcher.shutdown(1000)
