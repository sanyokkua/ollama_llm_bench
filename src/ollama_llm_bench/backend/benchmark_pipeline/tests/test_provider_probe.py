"""Proves: STORY-100-AC-1, STORY-100-AC-2, STORY-100-AC-3, STORY-100-AC-4

`run_provider_probe`'s state-gated admission, its outcome map against the circuit
breaker, the never-leaves-PROBING invariant over the full reachable outcome set
(driving the real `make_circuit_breaker`), and its per-row (not per-group)
invocation through `_internal.dispatcher.run_phase_with_stability`'s `before_row`
hook.
"""

from collections.abc import Callable
from concurrent.futures import Future
from typing import TYPE_CHECKING, cast

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import (
    run_phase_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.provider_probe import (
    run_provider_probe,
)
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    make_cancellation_token,
)
from ollama_llm_bench.backend.circuit_breaker import make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    BenchmarkRunSettingEntry,
    ChatRequest,
    ChatResponse,
    ModelName,
    ModelNameStr,
    ProviderId,
    ProviderIdStr,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import (
    AppError,
    ConfigurationError,
    HttpConnectionError,
    HttpTimeoutError,
    MissingEnvVarError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContextLengthError,
    ProviderRateLimitedError,
    ProviderServerError,
    TaskCancelledError,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry

if TYPE_CHECKING:
    from ollama_llm_bench.backend.concurrency.protocols import TaskRunner

_PROVIDER_ID: ProviderId = "22222222-2222-4222-8222-222222222222"
_MODEL_NAME: ModelName = "llama3"
_COOLDOWN_SECONDS = 10
_OK_RESPONSE = ChatResponse(text="OK", total_time_ms=1)

_BREAKER_SNAPSHOT: tuple[BenchmarkRunSettingEntry, ...] = (
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.enabled", setting_value="true"),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.failure_threshold", setting_value="1"),
    BenchmarkRunSettingEntry(
        setting_key="circuit_breaker.cooldown_seconds", setting_value=str(_COOLDOWN_SECONDS)
    ),
)


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


class _InlineProbeRunner:
    """Runs a submitted probe callable synchronously on the calling thread."""

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


def _registry_returning(mocker: MockerFixture, *, client: object) -> ProviderRegistry:
    """Build a `ProviderRegistry` double whose `get_client` resolves to `client`."""
    registry = mocker.Mock(spec=ProviderRegistry)
    registry.get_client.return_value = client
    return cast("ProviderRegistry", registry)


def _registry_raising(mocker: MockerFixture, *, error: AppError) -> ProviderRegistry:
    """Build a `ProviderRegistry` double whose `get_client` raises `error` itself,
    before any network call — the pre-call branch of the outcome map."""
    registry = mocker.Mock(spec=ProviderRegistry)
    registry.get_client.side_effect = error
    return cast("ProviderRegistry", registry)


@pytest.mark.parametrize(
    ("state", "expected_chat_calls", "expected_successes"),
    [
        pytest.param(CircuitState.CLOSED, 0, [], id="closed"),
        pytest.param(CircuitState.TRIPPED, 0, [], id="tripped"),
        pytest.param(CircuitState.PROBING, 1, [_PROVIDER_ID], id="probing"),
    ],
)
def test_probe_is_skipped_unless_probing(
    state: CircuitState,
    expected_chat_calls: int,
    expected_successes: list[ProviderId],
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-100-AC-1

    A `CLOSED` or `TRIPPED` breaker state makes the probe return immediately
    with zero `client.chat` calls and no breaker method invoked; a `PROBING`
    state issues exactly one lightweight liveness call and (per the
    `ChatResponse` outcome) closes the breaker.
    """
    client = _RecordingChatClient(response=_OK_RESPONSE)
    provider_registry = _registry_returning(mocker, client=client)
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_state(_PROVIDER_ID, state)

    run_provider_probe(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        runner=_InlineProbeRunner(),
        token=make_cancellation_token(),
    )

    assert len(client.requests) == expected_chat_calls
    assert circuit_breaker.recorded_successes == expected_successes
    assert circuit_breaker.recorded_failures == []


@pytest.mark.parametrize(
    ("chat_response", "chat_error", "get_client_error", "expected_successes", "expected_failures"),
    [
        pytest.param(_OK_RESPONSE, None, None, [_PROVIDER_ID], [], id="chat_response"),
        pytest.param(
            None, ProviderAuthError(message="401"), None, [_PROVIDER_ID], [], id="provider_auth"
        ),
        pytest.param(
            None,
            ModelNotAvailableError(message="404"),
            None,
            [_PROVIDER_ID],
            [],
            id="model_not_available",
        ),
        pytest.param(
            None,
            ProviderBadRequestError(message="400"),
            None,
            [_PROVIDER_ID],
            [],
            id="bad_request",
        ),
        pytest.param(
            None,
            ProviderContextLengthError(message="too long"),
            None,
            [_PROVIDER_ID],
            [],
            id="context_length",
        ),
        pytest.param(
            None, ProviderServerError(message="500"), None, [_PROVIDER_ID], [], id="server_error"
        ),
        pytest.param(
            None,
            ProviderRateLimitedError(message="429"),
            None,
            [_PROVIDER_ID],
            [],
            id="rate_limited",
        ),
        pytest.param(
            None,
            None,
            ConfigurationError(message="bad config"),
            [],
            [_PROVIDER_ID],
            id="configuration_error",
        ),
        pytest.param(
            None,
            None,
            MissingEnvVarError(message="missing key"),
            [],
            [_PROVIDER_ID],
            id="missing_env_var",
        ),
        pytest.param(
            None, HttpTimeoutError(message="timeout"), None, [], [_PROVIDER_ID], id="timeout"
        ),
        pytest.param(
            None,
            HttpConnectionError(message="down"),
            None,
            [],
            [_PROVIDER_ID],
            id="connection_error",
        ),
    ],
)
def test_probe_outcome_maps_to_close_or_retrip(  # noqa: PLR0913  # every parameter is
    # a distinct column of the outcome-map table this test is parametrized over
    chat_response: ChatResponse | None,
    chat_error: AppError | None,
    get_client_error: AppError | None,
    expected_successes: list[ProviderId],
    expected_failures: list[ProviderId],
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-100-AC-2

    Every reachable single-attempt outcome maps onto exactly one breaker
    call per ADR-0013's outcome table: a response or any other
    provider-response `AppError` closes the breaker (`record_success`); a
    transport failure or a pre-call `ConfigurationError`/`MissingEnvVarError`
    re-trips it (`record_failure`).
    """
    client = _RecordingChatClient(response=chat_response, error=chat_error)
    provider_registry = (
        _registry_raising(mocker, error=get_client_error)
        if get_client_error is not None
        else _registry_returning(mocker, client=client)
    )
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_state(_PROVIDER_ID, CircuitState.PROBING)

    run_provider_probe(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        runner=_InlineProbeRunner(),
        token=make_cancellation_token(),
    )

    assert circuit_breaker.recorded_successes == expected_successes
    assert circuit_breaker.recorded_failures == expected_failures


@pytest.mark.parametrize(
    ("chat_response", "chat_error", "get_client_error"),
    [
        pytest.param(_OK_RESPONSE, None, None, id="chat_response"),
        pytest.param(None, ProviderAuthError(message="401"), None, id="provider_auth"),
        pytest.param(None, ModelNotAvailableError(message="404"), None, id="model_not_available"),
        pytest.param(None, ProviderBadRequestError(message="400"), None, id="bad_request"),
        pytest.param(
            None, ProviderContextLengthError(message="too long"), None, id="context_length"
        ),
        pytest.param(None, ProviderServerError(message="500"), None, id="server_error"),
        pytest.param(None, ProviderRateLimitedError(message="429"), None, id="rate_limited"),
        pytest.param(
            None, None, ConfigurationError(message="bad config"), id="configuration_error"
        ),
        pytest.param(None, None, MissingEnvVarError(message="missing key"), id="missing_env_var"),
        pytest.param(None, HttpTimeoutError(message="timeout"), None, id="timeout"),
        pytest.param(None, HttpConnectionError(message="down"), None, id="connection_error"),
    ],
)
def test_probe_never_leaves_breaker_probing(
    chat_response: ChatResponse | None,
    chat_error: AppError | None,
    get_client_error: AppError | None,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-100-AC-3

    Structural regression: driving the real `make_circuit_breaker` (via a
    `FakeClock`-controlled trip-then-cooldown-elapse) to `PROBING`, every
    reachable outcome of the probe's single attempt leaves the breaker in a
    settled, non-`PROBING` state.
    """
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_BREAKER_SNAPSHOT, clock=clock)
    breaker.record_failure(_PROVIDER_ID)
    clock.advance_monotonic_ms((_COOLDOWN_SECONDS * 1000) + 1)
    assert breaker.state(_PROVIDER_ID) is CircuitState.PROBING

    client = _RecordingChatClient(response=chat_response, error=chat_error)
    provider_registry = (
        _registry_raising(mocker, error=get_client_error)
        if get_client_error is not None
        else _registry_returning(mocker, client=client)
    )
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)

    run_provider_probe(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=breaker,
        retry_count=0,
        runner=_InlineProbeRunner(),
        token=make_cancellation_token(),
    )

    assert breaker.state(_PROVIDER_ID) is not CircuitState.PROBING


def test_probe_cancellation_reports_no_outcome(mocker: MockerFixture) -> None:
    """Proves: STORY-100-AC-3

    A cancellation observed mid-probe propagates `TaskCancelledError`
    uncontained and reports neither a success nor a failure to the breaker —
    the one exit path allowed to leave the provider `PROBING`.
    """
    client = _RecordingChatClient(error=TaskCancelledError(message="stopped mid-probe"))
    provider_registry = _registry_returning(mocker, client=client)
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_state(_PROVIDER_ID, CircuitState.PROBING)

    with pytest.raises(TaskCancelledError):
        run_provider_probe(
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            provider_registry=provider_registry,
            adaptive_timeout=adaptive_timeout,
            circuit_breaker=circuit_breaker,
            retry_count=0,
            runner=_InlineProbeRunner(),
            token=make_cancellation_token(),
        )

    assert circuit_breaker.recorded_successes == []
    assert circuit_breaker.recorded_failures == []


# --- AC-4: per-row, not per-group, invocation through the dispatcher's hook ---


class _InlineRowRunner:
    """Runs any submitted callable synchronously — serves both
    `run_phase_with_stability`'s per-attempt runner use and the probe's own
    `TaskRunner[ChatResponse]` use of the same instance, cast per call site
    (mirrors `test_warmup.py`'s `_InlineStabilityRunner`)."""

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        del token
        future: Future[object] = Future()
        try:
            future.set_result(fn())
        except BaseException as exc:  # noqa: BLE001  # captured for the Future, not swallowed
            future.set_exception(exc)
        return future


def _failing_attempt_builder(timeout_ms: int) -> Callable[[], object]:
    del timeout_ms

    def _run() -> object:
        raise HttpConnectionError(message="row 1 unreachable")

    return _run


def _success_attempt_builder(timeout_ms: int) -> Callable[[], object]:
    del timeout_ms
    return lambda: "ok"


def test_probe_fires_per_row_not_per_group(mocker: MockerFixture) -> None:
    """Proves: STORY-100-AC-4

    In a single `(provider, model)` group with three rows, where the first
    row trips the breaker and the cooldown elapses before the dispatcher
    reaches the second row, the probe fires again — from the per-row
    `before_row` hook — before every subsequent row, not only once from a
    per-group hook a single-group run would never revisit.
    """
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_BREAKER_SNAPSHOT, clock=clock)
    probe_client = _RecordingChatClient(response=_OK_RESPONSE)
    probe_provider_registry = _registry_returning(mocker, client=probe_client)
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    runner = _InlineRowRunner()
    token = make_cancellation_token()
    results_store = FakeResultsStore()

    row_1 = make_benchmark_result(
        result_id=1, task_id="task-1", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
    )
    row_2 = make_benchmark_result(
        result_id=2, task_id="task-2", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
    )
    row_3 = make_benchmark_result(
        result_id=3, task_id="task-3", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
    )
    results_store.create_results((row_1, row_2, row_3))
    groups = ((_PROVIDER_ID, _MODEL_NAME, (row_1, row_2, row_3)),)

    probe_call_log: list[tuple[ProviderIdStr, ModelNameStr]] = []

    def _before_row(provider_id: ProviderIdStr, model_name: ModelNameStr) -> None:
        probe_call_log.append((provider_id, model_name))
        run_provider_probe(
            provider_id=provider_id,
            model_name=model_name,
            provider_registry=probe_provider_registry,
            adaptive_timeout=adaptive_timeout,
            circuit_breaker=breaker,
            retry_count=0,
            runner=cast("TaskRunner[ChatResponse]", runner),
            token=token,
        )

    def _stability_target_for(result: BenchmarkResult) -> tuple[ProviderId, ModelName]:
        return result.provider_id, result.model_name

    _attempt_builders: dict[int, Callable[[int], Callable[[], object]]] = {
        1: _failing_attempt_builder,
        2: _success_attempt_builder,
        3: _success_attempt_builder,
    }

    def _build_attempt_for(result: BenchmarkResult) -> Callable[[int], Callable[[], object]]:
        return _attempt_builders[result.result_id]

    def _finalize_success_for(result: BenchmarkResult) -> Callable[[object], ResultPatch]:
        del result
        return lambda raw: ResultPatch(status=ResultStatus.COMPLETED, raw_response=str(raw))

    def _on_timeout_exhausted_for(result: BenchmarkResult) -> Callable[[], ResultPatch]:
        del result
        return lambda: ResultPatch(status=ResultStatus.FAILED_TIMEOUT)

    def _after_row(result: BenchmarkResult, patch: ResultPatch, remaining: int) -> None:
        del result, patch, remaining
        clock.advance_monotonic_ms((_COOLDOWN_SECONDS * 1000) + 1)

    run_phase_with_stability(
        groups=groups,
        runner=cast("TaskRunner[object]", runner),
        token=token,
        results_store=results_store,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=0,
        clock=clock,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=breaker,
        stability_target_for=_stability_target_for,
        build_attempt_for=_build_attempt_for,
        finalize_success_for=_finalize_success_for,
        on_timeout_exhausted_for=_on_timeout_exhausted_for,
        after_row=_after_row,
        before_row=_before_row,
    )

    assert probe_call_log == [
        (_PROVIDER_ID, _MODEL_NAME),
        (_PROVIDER_ID, _MODEL_NAME),
        (_PROVIDER_ID, _MODEL_NAME),
    ]
    assert len(probe_client.requests) == 1
    assert breaker.state(_PROVIDER_ID) is CircuitState.CLOSED
