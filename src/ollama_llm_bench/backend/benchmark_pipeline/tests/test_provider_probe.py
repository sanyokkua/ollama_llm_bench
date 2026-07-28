"""Proves: STORY-100-AC-1, STORY-100-AC-2, STORY-100-AC-3, STORY-100-AC-4

`run_provider_probe`'s state-gated admission, its outcome map against the circuit
breaker, the never-leaves-PROBING invariant over the full reachable outcome set
(driving the real `make_circuit_breaker`), and its per-row (not per-group)
invocation through `_internal.dispatcher.run_phase_with_stability`'s `before_row`
hook.

Also proves (STORY-100 review-fix wave) that the probe's production wiring —
`_internal.stability_phase._run_inference_phase`/`_run_judge_phase`'s own
`before_row=_probe_before_row` lines — is actually present, by driving the real
`run_stability_phase` entry point (not a hand-rolled `before_row` closure) with a
real breaker already `PROBING`.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import (
    run_phase_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.provider_probe import (
    run_provider_probe,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_phase import (
    StabilityCollaborators,
    StabilityRunState,
    run_stability_phase,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    STABILITY_SETTING_ENTRIES,
    AlwaysPassSanityChecker,
    FakeClock,
    InlineCallableRunner,
    RecordingChatClient,
    SingleClientProviderRegistry,
    make_cancellation_token,
    make_task,
)
from ollama_llm_bench.backend.circuit_breaker import make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ModelName,
    ModelNameStr,
    ModelRole,
    ProviderId,
    ProviderIdStr,
    ResultPatch,
    ResultStatus,
    RunMode,
    RunStatus,
    Verdict,
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
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome, JudgePhaseResult
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.provider_registry.protocols import (
    ChatStream,
    ProviderRegistry,
)
from ollama_llm_bench.backend.settings.protocols import SettingsService

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
    client = RecordingChatClient(response=_OK_RESPONSE)
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
        runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
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
    client = RecordingChatClient(response=chat_response, error=chat_error)
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
        runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
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

    client = RecordingChatClient(response=chat_response, error=chat_error)
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
        runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
        token=make_cancellation_token(),
    )

    assert breaker.state(_PROVIDER_ID) is not CircuitState.PROBING


def test_probe_cancellation_reports_no_outcome(mocker: MockerFixture) -> None:
    """Proves: STORY-100-AC-3

    A cancellation observed mid-probe propagates `TaskCancelledError`
    uncontained and reports neither a success nor a failure to the breaker —
    the one exit path allowed to leave the provider `PROBING`.
    """
    client = RecordingChatClient(error=TaskCancelledError(message="stopped mid-probe"))
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
            runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
            token=make_cancellation_token(),
        )

    assert circuit_breaker.recorded_successes == []
    assert circuit_breaker.recorded_failures == []


# --- AC-4: per-row, not per-group, invocation through the dispatcher's hook ---


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
    probe_client = RecordingChatClient(response=_OK_RESPONSE)
    probe_provider_registry = _registry_returning(mocker, client=probe_client)
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=5)
    runner = InlineCallableRunner()
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


# --- Production-wiring constraint: the real `before_row=_probe_before_row` lines in
# `_internal.stability_phase._run_inference_phase`/`_run_judge_phase`, driven through
# the real `run_stability_phase` entry point rather than a hand-rolled closure ---

_INFERENCE_WIRING_PROVIDER_ID: ProviderId = "44444444-4444-4444-8444-444444444444"
_INFERENCE_WIRING_MODEL_NAME: ModelName = "wiring-model"
_JUDGE_WIRING_TEST_PROVIDER_ID: ProviderId = "55555555-5555-4555-8555-555555555555"
_JUDGE_WIRING_TEST_MODEL_NAME: ModelName = "row-test-model"
_JUDGE_WIRING_JUDGE_PROVIDER_ID: ProviderId = "66666666-6666-4666-8666-666666666666"
_JUDGE_WIRING_JUDGE_MODEL_NAME: ModelName = "judge-model"


class _OneChunkChatStream:
    """A minimal `ChatStream` double yielding a single canned chunk then a response."""

    def __init__(self, *, model: ModelName) -> None:
        self._yielded = False
        self._model = model

    def __iter__(self) -> "_OneChunkChatStream":
        return self

    def __next__(self) -> ChatChunk:
        if self._yielded:
            raise StopIteration
        self._yielded = True
        return ChatChunk(content="OK", delta_tokens=1)

    def trailing_response(self) -> ChatResponse:
        return ChatResponse(text=f"response for {self._model}", total_time_ms=1)


class _ProbeVsInferenceClient:
    """An `LLMClient` double distinguishing the probe's `chat` call from the
    row's own `chat_stream` inference call, recording each into a shared,
    test-owned call log as `("probe", model)`/`("inference", model)` — the
    load-bearing differentiator for
    `test_probe_wired_into_inference_phase_before_row`: only the dedicated
    probe ever calls `chat`, so a `chat` entry preceding the row's own
    `chat_stream` entry proves the `before_row` hook fired.
    """

    def __init__(self, *, call_log: list[tuple[str, str]]) -> None:
        self._call_log = call_log

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        del token
        self._call_log.append(("probe", request.model))
        return _OK_RESPONSE

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        del token
        self._call_log.append(("inference", request.model))
        return _OneChunkChatStream(model=request.model)


class _AlwaysResolvedJudgeEvaluator:
    """A `JudgeEvaluator` double that always resolves PASS on the first
    attempt — this test needs the judge row to settle normally, not to
    exercise the judge-timeout ladder `test_judge_timeout.py` already
    covers."""

    def evaluate(
        self,
        *,
        response: str,
        system_prompt_sent: str | None,
        task: BenchmarkTask,
        timeout_ms: int,
        token: CancellationToken,
    ) -> JudgePhaseResult:
        del response, system_prompt_sent, task, timeout_ms, token
        return JudgePhaseResult(
            outcome=JudgePhaseOutcome.RESOLVED,
            verdict=Verdict.PASS,
            reasoning="ok",
            time_ms=1,
            completion_tokens=1,
        )


def _make_wiring_run(
    *, judge_provider_id: ProviderId | None = None, judge_model_name: ModelName | None = None
) -> BenchmarkRun:
    """Build a minimal `BenchmarkRun`, optionally carrying a `ModelRole.JUDGE`
    entry distinct from its `ModelRole.TEST` entry (both wiring tests need a
    valid `run` argument; only the judge-phase test needs a resolvable judge
    target)."""
    models: tuple[BenchmarkRunModelEntry, ...] = ()
    if judge_provider_id is not None and judge_model_name is not None:
        models = (
            BenchmarkRunModelEntry(
                role=ModelRole.TEST,
                provider_id=_JUDGE_WIRING_TEST_PROVIDER_ID,
                model_name=_JUDGE_WIRING_TEST_MODEL_NAME,
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=judge_provider_id, model_name=judge_model_name
            ),
        )
    return BenchmarkRun(
        run_id=1,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.GRADED,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=models,
    )


def test_probe_wired_into_inference_phase_before_row(mocker: MockerFixture) -> None:
    """Proves: STORY-100-AC-4

    Driving `run_stability_phase(phase=Phase.INFERENCE, ...)` — the
    pipeline's real entry point, not a hand-rolled `before_row` closure —
    with a real `ProviderCircuitBreaker` already `PROBING` for the row's own
    provider proves `_run_inference_phase`'s `before_row=_probe_before_row`
    wiring is actually present: the probe's lightweight `client.chat` call
    is issued, against the row's own `(provider, model)` target, before the
    row's own `client.chat_stream` inference call. Deleting that wiring line
    means `should_skip` observes a still-`PROBING` provider with no
    lightweight probe call ever issued against it, so the row is skipped
    rather than dispatched: no `chat` call would ever precede a (never-made)
    `chat_stream` call — this test fails in that case (verified manually; see
    the story's Notes).
    """
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_BREAKER_SNAPSHOT, clock=clock)
    breaker.record_failure(_INFERENCE_WIRING_PROVIDER_ID)
    clock.advance_monotonic_ms((_COOLDOWN_SECONDS * 1000) + 1)
    assert breaker.state(_INFERENCE_WIRING_PROVIDER_ID) is CircuitState.PROBING

    call_log: list[tuple[str, str]] = []
    client = _ProbeVsInferenceClient(call_log=call_log)
    row = make_benchmark_result(
        result_id=1,
        task_id="task-1",
        provider_id=_INFERENCE_WIRING_PROVIDER_ID,
        model_name=_INFERENCE_WIRING_MODEL_NAME,
    )
    results_store = FakeResultsStore()
    results_store.create_results((row,))
    groups = ((_INFERENCE_WIRING_PROVIDER_ID, _INFERENCE_WIRING_MODEL_NAME, (row,)),)
    collaborators = StabilityCollaborators(
        bus=mocker.Mock(spec=EventBus),
        clock=clock,
        provider_registry=cast("ProviderRegistry", SingleClientProviderRegistry(client)),
        results_store=results_store,
        settings_service=mocker.Mock(spec=SettingsService),
        task_runner=InlineCallableRunner(),
    )

    run_stability_phase(
        phase=Phase.INFERENCE,
        groups=groups,
        run=_make_wiring_run(),
        tasks_by_id={"task-1": make_task(task_id="task-1")},
        sanity_checker=AlwaysPassSanityChecker(),
        judge_evaluator=None,
        token=make_cancellation_token(),
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=False,
        force_judge_on_prior_failure=False,
        collaborators=collaborators,
        state=StabilityRunState(),
        adaptive_timeout=make_adaptive_timeout_service(snapshot=STABILITY_SETTING_ENTRIES),
        circuit_breaker=breaker,
        retry_count=0,
        warmup_enabled=False,
    )

    assert call_log == [
        ("probe", _INFERENCE_WIRING_MODEL_NAME),
        ("inference", _INFERENCE_WIRING_MODEL_NAME),
    ]
    assert breaker.state(_INFERENCE_WIRING_PROVIDER_ID) is CircuitState.CLOSED


def test_probe_wired_into_judge_phase_targets_judge_pair_not_row_model(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-100-AC-4

    Driving `run_stability_phase(phase=Phase.JUDGE_CHECK, ...)` with a real
    `ProviderCircuitBreaker` already `PROBING` for the run's fixed judge
    provider — never the row's own test provider, which differs here —
    proves `_run_judge_phase`'s `before_row=_probe_before_row` wiring fires
    the probe against the judge pair: `get_client` is called with the judge
    provider id, and the probe's `chat` request names the judge model, never
    the row's own `(provider_id, model_name)`. The judge phase's own logic
    never calls `LLMClient.chat`/`get_client` directly (it goes through the
    injected `JudgeEvaluator` instead), so deleting the wiring line means
    `get_client` is never called at all here — this test fails in that case
    (verified manually; see the story's Notes).
    """
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_BREAKER_SNAPSHOT, clock=clock)
    breaker.record_failure(_JUDGE_WIRING_JUDGE_PROVIDER_ID)
    clock.advance_monotonic_ms((_COOLDOWN_SECONDS * 1000) + 1)
    assert breaker.state(_JUDGE_WIRING_JUDGE_PROVIDER_ID) is CircuitState.PROBING

    probe_client = RecordingChatClient(response=_OK_RESPONSE)
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = probe_client

    row = make_benchmark_result(
        result_id=1,
        task_id="task-1",
        provider_id=_JUDGE_WIRING_TEST_PROVIDER_ID,
        model_name=_JUDGE_WIRING_TEST_MODEL_NAME,
        status=ResultStatus.AWAITING_JUDGE_CHECK,
    )
    results_store = FakeResultsStore()
    results_store.create_results((row,))
    groups = ((_JUDGE_WIRING_TEST_PROVIDER_ID, _JUDGE_WIRING_TEST_MODEL_NAME, (row,)),)
    collaborators = StabilityCollaborators(
        bus=mocker.Mock(spec=EventBus),
        clock=clock,
        provider_registry=cast("ProviderRegistry", provider_registry),
        results_store=results_store,
        settings_service=mocker.Mock(spec=SettingsService),
        task_runner=InlineCallableRunner(),
    )

    run_stability_phase(
        phase=Phase.JUDGE_CHECK,
        groups=groups,
        run=_make_wiring_run(
            judge_provider_id=_JUDGE_WIRING_JUDGE_PROVIDER_ID,
            judge_model_name=_JUDGE_WIRING_JUDGE_MODEL_NAME,
        ),
        tasks_by_id={"task-1": make_task(task_id="task-1")},
        sanity_checker=AlwaysPassSanityChecker(),
        judge_evaluator=_AlwaysResolvedJudgeEvaluator(),
        token=make_cancellation_token(),
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=True,
        force_judge_on_prior_failure=False,
        collaborators=collaborators,
        state=StabilityRunState(),
        adaptive_timeout=make_adaptive_timeout_service(snapshot=STABILITY_SETTING_ENTRIES),
        circuit_breaker=breaker,
        retry_count=0,
        warmup_enabled=False,
    )

    provider_registry.get_client.assert_called_once_with(_JUDGE_WIRING_JUDGE_PROVIDER_ID)
    assert len(probe_client.requests) == 1
    assert probe_client.requests[0].model == _JUDGE_WIRING_JUDGE_MODEL_NAME
    assert breaker.state(_JUDGE_WIRING_JUDGE_PROVIDER_ID) is CircuitState.CLOSED
