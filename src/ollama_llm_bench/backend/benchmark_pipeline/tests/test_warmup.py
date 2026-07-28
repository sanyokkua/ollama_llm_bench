"""Proves: STORY-075-AC-1, STORY-075-AC-2, STORY-075-AC-3, STORY-075-AC-4, STORY-075-AC-6

`run_model_warmup`'s outcome classification against the circuit breaker and
adaptive-timeout services, its per-attempt budget sourced from the
role=INFERENCE adaptive-timeout ladder, the two guard checks that skip a
warmup outright (a non-`CLOSED` breaker, an already-excluded target), and the
model-switch-boundary wiring through `run_stability_phase`/
`run_phase_with_stability` for the INFERENCE phase.
"""

from typing import cast

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.adaptive_timeout import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_phase import (
    StabilityCollaborators,
    StabilityRunState,
    run_stability_phase,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.warmup import (
    WARMUP_MAX_OUTPUT_TOKENS,
    WARMUP_PROMPT,
    run_model_warmup,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    InlineCallableRunner,
    RecordingChatClient,
    make_cancellation_token,
    make_task,
)
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    CancelReason,
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ModelName,
    ProviderId,
    ResultId,
    ResultPatch,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
    TaskCancelledError,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.provider_registry.protocols import (
    ChatStream,
    LLMClient,
    ProviderRegistry,
)

_PROVIDER_ID: ProviderId = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME: ModelName = "llama3"


@pytest.fixture
def inline_warmup_runner() -> TaskRunner[ChatResponse]:
    """A `TaskRunner[ChatResponse]` double running every submission inline."""
    return cast("TaskRunner[ChatResponse]", InlineCallableRunner())


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
    inline_warmup_runner: TaskRunner[ChatResponse],
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
    client = RecordingChatClient(response=response, error=error)
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
    client = RecordingChatClient(error=HttpTimeoutError(message="no response"))
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
        runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
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


def test_warmup_behaviour_unchanged_after_probe_extraction(mocker: MockerFixture) -> None:
    """Proves: STORY-100-AC-5

    After `run_model_warmup` is refactored onto the shared
    `_internal.lightweight_call.issue_lightweight_call` helper (STORY-100), its
    observable behaviour stays byte-identical to the pre-refactor shape: it
    still walks the full `1 + retry_count` attempt ladder (never the probe's
    single-attempt shape), still sources its request payload from the same
    `WARMUP_PROMPT`/`WARMUP_MAX_OUTPUT_TOKENS` constants (now re-exported from
    `_internal.lightweight_call`), and still never calls
    `circuit_breaker.record_success` on a ladder-exhausted timeout.
    """
    retry_count = 2
    client = RecordingChatClient(error=HttpTimeoutError(message="no response"))
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    adaptive_timeout = FakeAdaptiveTimeoutService(fixed_budget_seconds=9)
    circuit_breaker = FakeProviderCircuitBreaker()

    run_model_warmup(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        provider_registry=provider_registry,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=retry_count,
        runner=cast("TaskRunner[ChatResponse]", InlineCallableRunner()),
        token=make_cancellation_token(),
    )

    assert len(client.requests) == 1 + retry_count
    assert client.requests[0].messages == (ChatMessage(role=ChatRole.USER, content=WARMUP_PROMPT),)
    assert client.requests[0].max_output_tokens == WARMUP_MAX_OUTPUT_TOKENS
    assert circuit_breaker.recorded_successes == []
    assert circuit_breaker.recorded_failures == [_PROVIDER_ID]


@pytest.mark.parametrize("state", [CircuitState.TRIPPED, CircuitState.PROBING])
def test_non_closed_breaker_skips_warmup_with_no_chat_call(
    state: CircuitState, inline_warmup_runner: TaskRunner[ChatResponse], mocker: MockerFixture
) -> None:
    """Warmup never dispatches to a provider whose breaker is not `CLOSED`.

    A `TRIPPED` or `PROBING` breaker state — read via the read-only `state()`
    query, never `should_skip()`, so a `PROBING` provider's real-task probe
    slot stays reserved for the breaker's own post-cooldown probe (DD-71) —
    skips the warmup outright: zero chat calls, zero breaker records.
    """
    client = RecordingChatClient(response=ChatResponse(text="OK", total_time_ms=1))
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
    inline_warmup_runner: TaskRunner[ChatResponse], mocker: MockerFixture
) -> None:
    """Warmup never dispatches when the target is already role=INFERENCE excluded.

    Mirrors the breaker guard above: a target already excluded for
    `role=INFERENCE` never receives a warmup call and never touches the
    circuit breaker.
    """
    client = RecordingChatClient(response=ChatResponse(text="OK", total_time_ms=1))
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


# --- Task 2: the model-switch-boundary wiring through `run_stability_phase` ---

_GROUP_PROVIDER_ID: ProviderId = "33333333-3333-4333-8333-333333333333"
_MODEL_X: ModelName = "model-x"
_MODEL_Y: ModelName = "model-y"


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


class _OrderingClient:
    """An `LLMClient` double recording every `chat`/`chat_stream` call's request
    model into a shared, test-owned call log — `("warmup", model)` for `chat`,
    `("inference", model)` for `chat_stream` — so AC-1/AC-2's ordering is
    directly assertable.
    """

    def __init__(self, *, call_log: list[tuple[str, str]]) -> None:
        self._call_log = call_log

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        del token
        self._call_log.append(("warmup", request.model))
        return ChatResponse(text="OK", total_time_ms=1)

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        del token
        self._call_log.append(("inference", request.model))
        return _OneChunkChatStream(model=request.model)


class _HardStopAtWarmupClient:
    """An `LLMClient` double whose `chat` hard-cancels the shared token and
    raises `TaskCancelledError`, simulating an in-flight warmup call aborted
    by Stop/Shutdown (§6.6). `chat_stream` must never be reached once this
    fires — recorded here so the test can assert zero task-inference calls.
    """

    def __init__(self, *, token: CancellationToken) -> None:
        self._token = token
        self.chat_stream_calls: list[str] = []

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        del token
        self._token.cancel(reason=CancelReason.USER_STOP, hard=True)
        raise TaskCancelledError(message="stopped mid-warmup")

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        del token
        self.chat_stream_calls.append(request.model)
        message = "chat_stream must not be called once a hard-stop fires at warmup"
        raise AssertionError(message)


class _SingleClientProviderRegistry:
    """A `ProviderRegistry` double resolving every provider id to one shared client."""

    def __init__(self, client: object) -> None:
        self._client = client

    def list_enabled(self) -> tuple[object, ...]:
        return ()

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        del provider_id
        return self._client  # type: ignore[return-value]  # structurally satisfies LLMClient

    def reload(self) -> None:
        return None


class _AlwaysPassSanityChecker:
    """A `SanityChecker` double that always passes."""

    def check(self, *, response: str, task: BenchmarkTask) -> bool:
        del response, task
        return True


class _RecordingResultsStore:
    """Wraps a `FakeResultsStore`, additionally logging every `update_result`
    call's `result_id` so AC-1 can prove a warmup never writes a result row."""

    def __init__(self, inner: FakeResultsStore) -> None:
        self._inner = inner
        self.updated_result_ids: list[ResultId] = []

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        self._inner.create_results(results)

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        self.updated_result_ids.append(result_id)
        self._inner.update_result(result_id, patch)

    def list_results(self, run_id: int) -> tuple[BenchmarkResult, ...]:
        return self._inner.list_results(run_id)

    def list_resumable_results(self, run_id: int) -> tuple[BenchmarkResult, ...]:
        return self._inner.list_resumable_results(run_id)

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        return self._inner.reset_results(result_ids)

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        return self._inner.reset_results_for_retry(result_ids)

    def recover_in_flight_results(self) -> int:
        return self._inner.recover_in_flight_results()


def _make_minimal_run() -> BenchmarkRun:
    """Build a minimal `BenchmarkRun` — unused by the INFERENCE stability
    path beyond being a required parameter (no judge-target resolution or
    settings read happens on this branch)."""
    return BenchmarkRun(
        run_id=1,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=3,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _make_group_rows() -> tuple[BenchmarkResult, BenchmarkResult, BenchmarkResult]:
    """Two groups: `(provider, model-x)` with two rows, `(provider, model-y)` with one."""
    return (
        make_benchmark_result(
            result_id=1,
            task_id="task-1",
            provider_id=_GROUP_PROVIDER_ID,
            model_name=_MODEL_X,
        ),
        make_benchmark_result(
            result_id=2,
            task_id="task-2",
            provider_id=_GROUP_PROVIDER_ID,
            model_name=_MODEL_X,
        ),
        make_benchmark_result(
            result_id=3,
            task_id="task-3",
            provider_id=_GROUP_PROVIDER_ID,
            model_name=_MODEL_Y,
        ),
    )


def _run_inference_stability_phase(
    *,
    client: object,
    results_store: _RecordingResultsStore,
    token: CancellationToken,
    warmup_enabled: bool,
    mocker: MockerFixture,
) -> None:
    """Drive `run_stability_phase(phase=Phase.INFERENCE, ...)` over
    `_make_group_rows`'s two groups, with grading fully disabled so each row
    settles `COMPLETED` after inference alone."""
    row_1, row_2, row_3 = _make_group_rows()
    results_store.create_results((row_1, row_2, row_3))
    tasks_by_id = {
        "task-1": make_task(task_id="task-1"),
        "task-2": make_task(task_id="task-2"),
        "task-3": make_task(task_id="task-3"),
    }
    groups = (
        (_GROUP_PROVIDER_ID, _MODEL_X, (row_1, row_2)),
        (_GROUP_PROVIDER_ID, _MODEL_Y, (row_3,)),
    )
    collaborators = StabilityCollaborators(
        bus=mocker.Mock(),
        clock=FakeClock(),
        provider_registry=_SingleClientProviderRegistry(client),  # type: ignore[arg-type]  # structurally satisfies ProviderRegistry
        results_store=results_store,
        settings_service=mocker.Mock(),
        task_runner=InlineCallableRunner(),
    )
    run_stability_phase(
        phase=Phase.INFERENCE,
        groups=groups,
        run=_make_minimal_run(),
        tasks_by_id=tasks_by_id,
        sanity_checker=_AlwaysPassSanityChecker(),
        judge_evaluator=None,
        token=token,
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=False,
        force_judge_on_prior_failure=False,
        collaborators=collaborators,
        state=StabilityRunState(),
        adaptive_timeout=FakeAdaptiveTimeoutService(),
        circuit_breaker=FakeProviderCircuitBreaker(),
        retry_count=0,
        warmup_enabled=warmup_enabled,
    )


def test_warmup_fires_once_before_first_task_inference_when_enabled(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-075-AC-1

    With warmup enabled, the INFERENCE phase issues exactly one warmup call
    at the start of each `(provider, model)` group — before that group's
    first task row's inference call — and never writes a `BenchmarkResult`
    row for the warmup itself, only for the three task rows.
    """
    call_log: list[tuple[str, str]] = []
    client = _OrderingClient(call_log=call_log)
    results_store = _RecordingResultsStore(FakeResultsStore())
    token = make_cancellation_token()

    _run_inference_stability_phase(
        client=client,
        results_store=results_store,
        token=token,
        warmup_enabled=True,
        mocker=mocker,
    )

    assert call_log == [
        ("warmup", _MODEL_X),
        ("inference", _MODEL_X),
        ("inference", _MODEL_X),
        ("warmup", _MODEL_Y),
        ("inference", _MODEL_Y),
    ]
    assert results_store.updated_result_ids == [1, 2, 3]


def test_warmup_off_issues_no_warmup_and_runs_first_task_directly(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-075-AC-2

    With warmup disabled (the frozen-snapshot `benchmark.warmup_enabled`
    read), the INFERENCE phase never issues a warmup call for either group —
    each group's first row's inference call runs directly.
    """
    call_log: list[tuple[str, str]] = []
    client = _OrderingClient(call_log=call_log)
    results_store = _RecordingResultsStore(FakeResultsStore())
    token = make_cancellation_token()

    _run_inference_stability_phase(
        client=client,
        results_store=results_store,
        token=token,
        warmup_enabled=False,
        mocker=mocker,
    )

    assert call_log == [
        ("inference", _MODEL_X),
        ("inference", _MODEL_X),
        ("inference", _MODEL_Y),
    ]
    assert results_store.updated_result_ids == [1, 2, 3]


def test_hard_stop_at_warmup_halts_run_and_reports_no_breaker_outcome(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-075-AC-6

    A hard cancellation (Stop/Shutdown) that fires while the warmup's own
    in-flight `chat` call is aborting propagates `TaskCancelledError` out of
    `run_stability_phase` uncontained: the group's task rows never run their
    own inference call, and the circuit breaker records neither a failure
    nor a success for the aborted warmup.
    """
    token = make_cancellation_token()
    client = _HardStopAtWarmupClient(token=token)
    results_store = _RecordingResultsStore(FakeResultsStore())
    row_1, row_2, row_3 = _make_group_rows()
    results_store.create_results((row_1, row_2, row_3))
    tasks_by_id = {
        "task-1": make_task(task_id="task-1"),
        "task-2": make_task(task_id="task-2"),
        "task-3": make_task(task_id="task-3"),
    }
    groups = (
        (_GROUP_PROVIDER_ID, _MODEL_X, (row_1, row_2)),
        (_GROUP_PROVIDER_ID, _MODEL_Y, (row_3,)),
    )
    circuit_breaker = FakeProviderCircuitBreaker()
    collaborators = StabilityCollaborators(
        bus=mocker.Mock(),
        clock=FakeClock(),
        provider_registry=_SingleClientProviderRegistry(client),  # type: ignore[arg-type]  # structurally satisfies ProviderRegistry
        results_store=results_store,
        settings_service=mocker.Mock(),
        task_runner=InlineCallableRunner(),
    )

    with pytest.raises(TaskCancelledError):
        run_stability_phase(
            phase=Phase.INFERENCE,
            groups=groups,
            run=_make_minimal_run(),
            tasks_by_id=tasks_by_id,
            sanity_checker=_AlwaysPassSanityChecker(),
            judge_evaluator=None,
            token=token,
            keyword_enabled=False,
            cosine_enabled=False,
            judge_enabled=False,
            force_judge_on_prior_failure=False,
            collaborators=collaborators,
            state=StabilityRunState(),
            adaptive_timeout=FakeAdaptiveTimeoutService(),
            circuit_breaker=circuit_breaker,
            retry_count=0,
            warmup_enabled=True,
        )

    assert client.chat_stream_calls == []
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []
