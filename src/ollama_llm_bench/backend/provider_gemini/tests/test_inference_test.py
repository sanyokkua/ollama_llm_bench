"""Tests proving STORY-020-AC-8: ``test_inference(model_name)``'s outcome
table, the never-raises contract, and the gate acquire/release discipline.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.8.2.

Table-driven (Pattern B) for the outcome map, plus Given/When/Then tests for
the gate-acquire/never-raise contract the table alone cannot express (gate
state before/after, and the ``GATE_BUSY`` no-call-issued rule).
"""

from collections.abc import Callable
import time
from typing import NamedTuple

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from ollama_llm_bench.backend.domain import InferenceActivity, InferenceActivityContext
from ollama_llm_bench.backend.domain.models import InferenceTestOutcome
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini.models import GeminiClientSettings
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_STREAM_PATH = "/v1beta/models/gemini-test-model:streamGenerateContent"
_MODEL_NAME = "gemini-test-model"
_INFERENCE_TEST_STALL_SECONDS = 3.0
_EXPECTED_TWO_CALLS = 2


def _stalling_handler(request: Request) -> Response:
    """Sleep well past the inference-test deadline used by the timeout test."""
    del request
    time.sleep(_INFERENCE_TEST_STALL_SECONDS)
    return Response("data: {}\n\n", content_type="text/event-stream")


def _success_body() -> str:
    return (
        'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]},'
        '"index":0}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":1}}\n\n'
    )


class _OutcomeCase(NamedTuple):
    """Strictly private, colocated-test-only bundle for one AC-8 table row."""

    status: int
    expected_outcome: InferenceTestOutcome


_CASES = (
    _OutcomeCase(status=401, expected_outcome=InferenceTestOutcome.AUTH_FAILED),
    _OutcomeCase(status=404, expected_outcome=InferenceTestOutcome.MODEL_NOT_FOUND),
    _OutcomeCase(status=500, expected_outcome=InferenceTestOutcome.PROVIDER_ERROR),
)


@pytest.mark.parametrize("case", _CASES, ids=["auth_failed", "model_not_found", "provider_error"])
def test_test_inference_classifies_outcome_by_failure_scenario(
    httpserver: HTTPServer,
    make_client: Callable[..., GeminiClient],
    case: _OutcomeCase,
) -> None:
    """Proves: STORY-020-AC-8

    Each ``test_inference`` failure scenario produces the matching
    ``InferenceTestOutcome`` per the story's AC-8 table; the method never
    raises regardless of the underlying failure.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_json(
        {"error": {"code": case.status, "message": "boom"}}, status=case.status
    )
    client = make_client()

    # Act
    result = client.test_inference(_MODEL_NAME)

    # Assert
    assert result.outcome is case.expected_outcome


def test_test_inference_classifies_timeout_outcome(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-8

    Given the canned-prompt call exceeds the inference-test deadline, when
    ``test_inference`` is called, then it returns ``TIMEOUT`` and never
    raises.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_handler(_stalling_handler)
    client = make_client(settings=GeminiClientSettings(inference_test_timeout_ms=200))

    # Act
    result = client.test_inference(_MODEL_NAME)

    # Assert
    assert result.outcome is InferenceTestOutcome.TIMEOUT


def test_test_inference_success_returns_verbatim_excerpt(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-8

    Given the canned-prompt call returns non-empty text, when
    ``test_inference`` is called, then it returns ``SUCCESS`` with the
    response excerpt verbatim and no ``last_error``.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_data(
        _success_body(), content_type="text/event-stream"
    )
    client = make_client()

    # Act
    result = client.test_inference(_MODEL_NAME)

    # Assert
    assert result.outcome is InferenceTestOutcome.SUCCESS
    assert result.response_excerpt == "ok"
    assert result.last_error is None


def test_test_inference_reports_gate_busy_without_issuing_a_call(
    httpserver: HTTPServer,
    make_client: Callable[..., GeminiClient],
    gate: FakeInferenceActivityStore,
) -> None:
    """Proves: STORY-020-AC-8

    Given the single-inference gate is already held by another activity,
    when ``test_inference`` is called, then it returns ``GATE_BUSY`` with
    ``latency_ms=None`` and no call is issued to the provider — the wire
    stub records zero requests.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_json(
        {"error": {"code": 500, "message": "should never be called"}}, status=500
    )
    client = make_client()
    lease = gate.try_acquire(
        InferenceActivity.READINESS_PROBE,
        InferenceActivityContext(activity=InferenceActivity.READINESS_PROBE, started_at=0),
    )
    assert lease is not None

    # Act
    result = client.test_inference(_MODEL_NAME)

    # Assert
    assert result.outcome is InferenceTestOutcome.GATE_BUSY
    assert result.latency_ms is None
    assert len(httpserver.log) == 0


def test_test_inference_releases_gate_in_finally_after_success(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-8

    Given a successful ``test_inference`` call, when it completes, then the
    ``PROVIDER_TEST`` gate has been released — a second ``test_inference``
    call immediately afterward is not itself reported ``GATE_BUSY``.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_data(
        _success_body(), content_type="text/event-stream"
    )
    client = make_client()

    # Act
    first = client.test_inference(_MODEL_NAME)
    second = client.test_inference(_MODEL_NAME)

    # Assert
    assert first.outcome is InferenceTestOutcome.SUCCESS
    assert second.outcome is InferenceTestOutcome.SUCCESS


def test_test_inference_releases_gate_in_finally_after_failure(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-8

    Given a failed ``test_inference`` call, when it completes, then the
    ``PROVIDER_TEST`` gate has still been released in ``finally`` — a
    second ``test_inference`` call immediately afterward is not itself
    reported ``GATE_BUSY``.
    """
    # Arrange
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_json(
        {"error": {"code": 500, "message": "boom"}}, status=500
    )
    client = make_client()

    # Act
    first = client.test_inference(_MODEL_NAME)
    second = client.test_inference(_MODEL_NAME)

    # Assert
    assert first.outcome is InferenceTestOutcome.PROVIDER_ERROR
    assert second.outcome is InferenceTestOutcome.PROVIDER_ERROR
    assert len(httpserver.log) == _EXPECTED_TWO_CALLS
