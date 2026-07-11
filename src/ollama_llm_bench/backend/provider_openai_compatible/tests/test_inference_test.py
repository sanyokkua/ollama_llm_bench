"""Tests proving STORY-018-AC-9: ``test_inference(model_name)``'s outcome table,
the never-raises contract, and the gate acquire/release discipline.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.8.2.

Table-driven (Pattern B) for the outcome map, plus two Given/When/Then tests for
the gate-acquire/never-raise contract that the table alone cannot express (gate
state before/after, and the ``GATE_BUSY`` no-call-issued rule).
"""

from collections.abc import Callable
import json
import time
from typing import NamedTuple

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from ollama_llm_bench.backend.domain import InferenceActivity, InferenceActivityContext
from ollama_llm_bench.backend.domain.models import InferenceTestOutcome
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_INFERENCE_TEST_STALL_SECONDS = 3.0


def _stalling_handler(request: Request) -> Response:
    """Sleep well past the inference-test deadline used by the timeout test."""
    del request
    time.sleep(_INFERENCE_TEST_STALL_SECONDS)
    return Response("data: [DONE]\n\n", content_type="text/event-stream")


_UNUSED_STATUS = 0  # placeholder for the unreachable-host case; never sent to the wire stub
_MODEL_NAME = "test-model"


class _OutcomeCase(NamedTuple):
    """Strictly private, colocated-test-only bundle for one AC-9 table row."""

    status: int
    body: dict[str, object] | None
    unreachable: bool
    expected_outcome: InferenceTestOutcome


def _success_body() -> dict[str, object]:
    chunk = {
        "id": "1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
    }
    return {"__sse__": "".join([f"data: {json.dumps(chunk)}\n\n", "data: [DONE]\n\n"])}


_CASES = (
    _OutcomeCase(
        status=401,
        body={"error": {"message": "invalid key", "code": "invalid_api_key"}},
        unreachable=False,
        expected_outcome=InferenceTestOutcome.AUTH_FAILED,
    ),
    _OutcomeCase(
        status=404,
        body={"error": {"message": "model not found", "code": "model_not_found"}},
        unreachable=False,
        expected_outcome=InferenceTestOutcome.MODEL_NOT_FOUND,
    ),
    _OutcomeCase(
        status=500,
        body={"error": {"message": "internal error", "code": "server_error"}},
        unreachable=False,
        expected_outcome=InferenceTestOutcome.PROVIDER_ERROR,
    ),
    _OutcomeCase(
        status=_UNUSED_STATUS,
        body=None,
        unreachable=True,
        expected_outcome=InferenceTestOutcome.REACHABILITY_FAILED,
    ),
)


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=["auth_failed", "model_not_found", "provider_error", "reachability_failed"],
)
def test_test_inference_classifies_outcome_by_failure_scenario(
    httpserver: HTTPServer,
    make_client: Callable[..., OpenAICompatibleClient],
    case: _OutcomeCase,
) -> None:
    """Proves: STORY-018-AC-9

    Each ``test_inference`` failure scenario produces the matching
    ``InferenceTestOutcome`` per the story's AC-9 table; the method never
    raises regardless of the underlying failure.
    """
    # Arrange
    if case.unreachable:
        client = make_client(base_url="http://127.0.0.1:1/")
    else:
        assert case.body is not None
        httpserver.expect_request("/chat/completions", method="POST").respond_with_json(
            case.body, status=case.status
        )
        client = make_client()

    # Act
    result = client.test_inference("test-model")

    # Assert
    assert result.outcome is case.expected_outcome
    assert result.response_excerpt is None


def test_test_inference_classifies_timeout_outcome(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-9

    Given the canned-prompt call exceeds the inference-test deadline, when
    ``test_inference`` is called, then it returns ``TIMEOUT`` and never
    raises.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_handler(
        _stalling_handler
    )
    client = make_client(settings=OpenAICompatibleClientSettings(inference_test_timeout_ms=200))

    # Act
    result = client.test_inference(_MODEL_NAME)

    # Assert
    assert result.outcome is InferenceTestOutcome.TIMEOUT


def test_test_inference_success_returns_verbatim_excerpt(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-9

    Given the canned-prompt call returns non-empty text, when
    ``test_inference`` is called, then it returns ``SUCCESS`` with the
    response excerpt verbatim and no ``last_error``.
    """
    # Arrange
    payload = _success_body()["__sse__"]
    assert isinstance(payload, str)
    httpserver.expect_request("/chat/completions", method="POST").respond_with_data(
        payload, content_type="text/event-stream"
    )
    client = make_client()

    # Act
    result = client.test_inference("test-model")

    # Assert
    assert result.outcome is InferenceTestOutcome.SUCCESS
    assert result.response_excerpt == "ok"
    assert result.last_error is None


def test_test_inference_reports_gate_busy_without_issuing_a_call(
    httpserver: HTTPServer,
    make_client: Callable[..., OpenAICompatibleClient],
    gate: FakeInferenceActivityStore,
) -> None:
    """Proves: STORY-018-AC-9

    Given the single-inference gate is already held by another activity,
    when ``test_inference`` is called, then it returns ``GATE_BUSY`` with
    ``latency_ms=None`` and no call is issued to the provider — the wire
    stub records zero requests.
    """
    # Arrange: mark the endpoint as "any call is a test failure" by leaving
    # a canned response registered but asserting afterward it was never hit.
    httpserver.expect_request("/chat/completions", method="POST").respond_with_json(
        {"error": {"message": "should never be called"}}, status=500
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
    httpserver: HTTPServer,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-9

    Given a successful ``test_inference`` call, when it completes, then the
    ``PROVIDER_TEST`` gate has been released — a second ``test_inference``
    call immediately afterward is not itself reported ``GATE_BUSY``.
    """
    # Arrange
    payload = _success_body()["__sse__"]
    assert isinstance(payload, str)
    httpserver.expect_request("/chat/completions", method="POST").respond_with_data(
        payload, content_type="text/event-stream"
    )
    client = make_client()

    # Act
    first = client.test_inference("test-model")
    second = client.test_inference("test-model")

    # Assert
    assert first.outcome is InferenceTestOutcome.SUCCESS
    assert second.outcome is InferenceTestOutcome.SUCCESS
