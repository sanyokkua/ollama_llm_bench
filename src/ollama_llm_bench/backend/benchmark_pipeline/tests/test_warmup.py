"""Proves: STORY-075-AC-3, STORY-075-AC-4

`run_model_warmup`'s outcome classification against the circuit breaker and
adaptive-timeout services, its per-attempt budget sourced from the
role=INFERENCE adaptive-timeout ladder, and the two guard checks that skip a
warmup outright (a non-`CLOSED` breaker, an already-excluded target).
"""

from collections.abc import Callable
from concurrent.futures import Future

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.adaptive_timeout import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.warmup import (
    WARMUP_MAX_OUTPUT_TOKENS,
    WARMUP_PROMPT,
    run_model_warmup,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import make_cancellation_token
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
)
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry

_PROVIDER_ID: ProviderId = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME: ModelName = "llama3"


class _RecordingChatClient:
    """Minimal `LLMClient` double exposing only `chat`, scripted per test.

    Appends every `ChatRequest` it receives, then either returns a fixed
    `ChatResponse` or raises a fixed `AppError` on every call.
    """

    def __init__(
        self, *, response: ChatResponse | None = None, error: AppError | None = None
    ) -> None:
        self._response = response
        self._error = error
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        del token
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class _InlineWarmupRunner:
    """Runs a submitted warmup callable synchronously on the calling thread."""

    def submit(
        self, fn: Callable[[], ChatResponse], *, token: CancellationToken
    ) -> "Future[ChatResponse]":
        del token
        future: Future[ChatResponse] = Future()
        try:
            future.set_result(fn())
        except BaseException as exc:  # noqa: BLE001  # captured for the Future, not swallowed
            future.set_exception(exc)
        return future


@pytest.fixture
def inline_warmup_runner() -> _InlineWarmupRunner:
    """A `TaskRunner[ChatResponse]` double running every submission inline."""
    return _InlineWarmupRunner()


class _RecordingAdaptiveTimeout:
    """Wraps a `FakeAdaptiveTimeoutService`, additionally logging every
    `next_budget` query call.

    The shared fake's own call logs (`recorded_successes`/`recorded_timeouts`)
    cover only its write methods — this wrapper adds the read-call log
    STORY-075-AC-4 needs, forwarding every call through to the inner fake.
    """

    def __init__(self, inner: FakeAdaptiveTimeoutService) -> None:
        self._inner = inner
        self.next_budget_calls: list[tuple[ProviderId, ModelName, AdaptiveTimeoutRole, int]] = []

    @property
    def recorded_successes(
        self,
    ) -> list[tuple[ProviderId, ModelName, AdaptiveTimeoutRole, int]]:
        return self._inner.recorded_successes

    @property
    def recorded_timeouts(self) -> list[tuple[ProviderId, ModelName, AdaptiveTimeoutRole]]:
        return self._inner.recorded_timeouts

    def next_budget(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        attempt_index: int = 1,
    ) -> int:
        self.next_budget_calls.append((provider_id, model_name, role, attempt_index))
        return self._inner.next_budget(provider_id, model_name, role, attempt_index=attempt_index)

    def record_success(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        observed_ms: int,
    ) -> None:
        self._inner.record_success(provider_id, model_name, role, observed_ms)

    def record_timeout(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> None:
        self._inner.record_timeout(provider_id, model_name, role)

    def is_excluded(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> bool:
        return self._inner.is_excluded(provider_id, model_name, role)

    def model_state(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> AdaptiveTimeoutModelState:
        return self._inner.model_state(provider_id, model_name, role)


@pytest.mark.parametrize(
    ("chat_behaviour", "expected_failure_count"),
    [
        ("success", 0),
        ("model_error", 0),
        ("timeout", 1),
        ("transport_error", 1),
    ],
)
def test_warmup_outcome_drives_circuit_breaker_and_never_excludes_model(
    chat_behaviour: str,
    expected_failure_count: int,
    inline_warmup_runner: _InlineWarmupRunner,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-075-AC-3

    Every warmup outcome — a normal completion, a model-side error, a
    ladder-exhausted timeout, and a connection/transport error — drives the
    circuit breaker per its provider-liveness meaning, and none of them ever
    touches the adaptive-timeout model-exclusion counter.
    """
    response = ChatResponse(text="OK", total_time_ms=5) if chat_behaviour == "success" else None
    error: AppError | None = {
        "model_error": ModelNotAvailableError(message="model not available"),
        "timeout": HttpTimeoutError(message="no response"),
        "transport_error": HttpConnectionError(message="connection reset"),
    }.get(chat_behaviour)
    client = _RecordingChatClient(response=response, error=error)
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    circuit_breaker = FakeProviderCircuitBreaker()

    run_model_warmup(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        runner=inline_warmup_runner,
        token=make_cancellation_token(),
    )

    assert len(circuit_breaker.recorded_failures) == expected_failure_count
    assert circuit_breaker.recorded_successes == []
    assert adaptive_timeout.recorded_timeouts == []
    assert adaptive_timeout.recorded_successes == []


def test_warmup_budget_read_from_role_inference_ladder(mocker: MockerFixture) -> None:
    """Proves: STORY-075-AC-4

    The warmup call's per-attempt timeout is read from the target's
    role=INFERENCE adaptive-timeout ladder (37s here), never a separate fixed
    warmup deadline; a ladder-exhausted timeout drives the client through the
    full `1 + retry_count` attempt ladder, consulting `next_budget` with
    `role=INFERENCE` at each 1-based attempt index.
    """
    retry_count = 1
    client = _RecordingChatClient(error=HttpTimeoutError(message="no response"))
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    adaptive_timeout = _RecordingAdaptiveTimeout(
        FakeAdaptiveTimeoutService(fixed_budget_seconds=37)
    )
    circuit_breaker = FakeProviderCircuitBreaker()

    run_model_warmup(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=retry_count,
        runner=_InlineWarmupRunner(),
        token=make_cancellation_token(),
    )

    assert len(client.requests) == 1 + retry_count
    first_request = client.requests[0]
    assert first_request.timeout_ms == 37 * 1000
    assert first_request.max_output_tokens == WARMUP_MAX_OUTPUT_TOKENS
    assert first_request.messages == (ChatMessage(role=ChatRole.USER, content=WARMUP_PROMPT),)
    assert [call[3] for call in adaptive_timeout.next_budget_calls] == [1, 2]
    assert {call[2] for call in adaptive_timeout.next_budget_calls} == {
        AdaptiveTimeoutRole.INFERENCE
    }
    assert circuit_breaker.recorded_failures == [_PROVIDER_ID]


@pytest.mark.parametrize("state", [CircuitState.TRIPPED, CircuitState.PROBING])
def test_non_closed_breaker_skips_warmup_with_no_chat_call(
    state: CircuitState, inline_warmup_runner: _InlineWarmupRunner, mocker: MockerFixture
) -> None:
    """Warmup never dispatches to a provider whose breaker is not `CLOSED`.

    A `TRIPPED` or `PROBING` breaker state — read via the read-only `state()`
    query, never `should_skip()`, so a `PROBING` provider's real-task probe
    slot stays reserved for the breaker's own post-cooldown probe (DD-71) —
    skips the warmup outright: zero chat calls, zero breaker records.
    """
    client = _RecordingChatClient(response=ChatResponse(text="OK", total_time_ms=1))
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_state(_PROVIDER_ID, state)

    run_model_warmup(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        runner=inline_warmup_runner,
        token=make_cancellation_token(),
    )

    assert client.requests == []
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []


def test_already_excluded_target_skips_warmup_with_no_chat_call(
    inline_warmup_runner: _InlineWarmupRunner, mocker: MockerFixture
) -> None:
    """Warmup never dispatches when the target is already role=INFERENCE excluded.

    Mirrors the breaker guard above: a target already excluded for
    `role=INFERENCE` never receives a warmup call and never touches the
    circuit breaker.
    """
    client = _RecordingChatClient(response=ChatResponse(text="OK", total_time_ms=1))
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    adaptive_timeout = FakeAdaptiveTimeoutService()
    adaptive_timeout.set_excluded(_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.INFERENCE)
    circuit_breaker = FakeProviderCircuitBreaker()

    run_model_warmup(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        runner=inline_warmup_runner,
        token=make_cancellation_token(),
    )

    assert client.requests == []
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []
