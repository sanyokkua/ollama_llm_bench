"""Unit tests proving ``QtBenchmarkFlow`` is a thin, business-logic-free forwarding facade
over the backend ``BenchmarkFlowApi`` (STORY-042).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§11 (the ``BenchmarkFlowApi`` method surface and its idle no-op rules).
"""

from collections.abc import Callable
from typing import cast

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.adapters.qt_benchmark_flow import QtBenchmarkFlow, make_qt_benchmark_flow
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRun,
    ModelDescriptor,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
)

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_RUN_ID: RunId = 1
_TIMEOUT_MS = 2000


def _make_run_start_request() -> RunStartRequest:
    """A minimal, valid ``RunStartRequest`` naming one test target."""
    return RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _make_run() -> BenchmarkRun:
    """A minimal, valid ``BenchmarkRun`` for ``current_run()`` forwarding assertions."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=0,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
    )


@pytest.fixture
def facade_and_pipeline(mocker: MockerFixture) -> tuple[QtBenchmarkFlow, BenchmarkFlowApi]:
    """A real ``QtBenchmarkFlow`` wrapping a ``mocker.Mock(spec=BenchmarkFlowApi)``."""
    pipeline = cast("BenchmarkFlowApi", mocker.Mock(spec=BenchmarkFlowApi))
    facade = make_qt_benchmark_flow(pipeline=pipeline)
    return facade, pipeline


_FORWARDING_CASES: tuple[
    tuple[str, Callable[[QtBenchmarkFlow], object], Callable[[BenchmarkFlowApi], object], object],
    ...,
] = (
    (
        "start",
        lambda facade: facade.start(_make_run_start_request()),
        lambda pipeline: pipeline.start,
        _RUN_ID,
    ),
    (
        "resume",
        lambda facade: facade.resume(_RUN_ID),
        lambda pipeline: pipeline.resume,
        None,
    ),
    (
        "pause",
        lambda facade: facade.pause(),
        lambda pipeline: pipeline.pause,
        None,
    ),
    (
        "resume_paused",
        lambda facade: facade.resume_paused(),
        lambda pipeline: pipeline.resume_paused,
        None,
    ),
    (
        "stop",
        lambda facade: facade.stop(),
        lambda pipeline: pipeline.stop,
        None,
    ),
    (
        "shutdown",
        lambda facade: facade.shutdown(_TIMEOUT_MS),
        lambda pipeline: pipeline.shutdown,
        None,
    ),
    (
        "is_running",
        lambda facade: facade.is_running(),
        lambda pipeline: pipeline.is_running,
        True,
    ),
    (
        "current_run",
        lambda facade: facade.current_run(),
        lambda pipeline: pipeline.current_run,
        None,
    ),
)
_FORWARDING_CASE_IDS = [case[0] for case in _FORWARDING_CASES]


@pytest.mark.parametrize("case", _FORWARDING_CASES, ids=_FORWARDING_CASE_IDS)
def test_control_and_query_calls_forward_to_backend(
    facade_and_pipeline: tuple[QtBenchmarkFlow, BenchmarkFlowApi],
    case: tuple[
        str,
        Callable[[QtBenchmarkFlow], object],
        Callable[[BenchmarkFlowApi], object],
        object,
    ],
) -> None:
    """Proves: STORY-042-AC-2

    For each control/query method, calling it on the facade forwards to the
    identically-named backend ``BenchmarkFlowApi`` method exactly once and
    returns its result unchanged.
    """
    # Arrange
    _name, call_facade, select_mock_method, canned_return = case
    facade, pipeline = facade_and_pipeline
    mock_method = select_mock_method(pipeline)
    mock_method.return_value = canned_return  # type: ignore[attr-defined]  # Mock attribute

    # Act
    result = call_facade(facade)

    # Assert
    mock_method.assert_called_once()  # type: ignore[attr-defined]  # Mock attribute
    assert result == canned_return


def test_idle_pause_stop_are_noops_through_facade(
    facade_and_pipeline: tuple[QtBenchmarkFlow, BenchmarkFlowApi],
) -> None:
    """Proves: STORY-042-AC-4

    Given no run is active, calling ``pause()``, ``resume_paused()``, or
    ``stop()`` on the facade forwards to the backend and returns without
    raising — the idle no-op contract is preserved through the facade.
    """
    # Arrange
    facade, pipeline = facade_and_pipeline

    # Act (no exception)
    facade.pause()
    facade.resume_paused()
    facade.stop()

    # Assert
    cast("object", pipeline.pause).assert_called_once()  # type: ignore[attr-defined]
    cast("object", pipeline.resume_paused).assert_called_once()  # type: ignore[attr-defined]
    cast("object", pipeline.stop).assert_called_once()  # type: ignore[attr-defined]
