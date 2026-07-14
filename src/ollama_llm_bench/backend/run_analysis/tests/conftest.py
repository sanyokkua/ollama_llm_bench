"""Shared test helpers, fakes, and fixtures for ``backend/run_analysis/`` tests."""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunProviderEntry,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    RunStatusPatch,
    TaskOrigin,
    Verdict,
)
from ollama_llm_bench.backend.events.protocols import EventBus, Subscription
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, ProviderRegistry
from ollama_llm_bench.backend.run_analysis._internal.service import RunAnalysisServiceImpl
from ollama_llm_bench.backend.run_analysis._internal.timeout_cache import RunAdaptiveTimeoutCache
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

__all__: list[str] = [
    "FakeClock",
    "FakeEventBus",
    "FakeLLMClient",
    "FakeProviderRegistry",
    "FakeRunsStore",
    "FakeTasksStore",
    "StaticChatStream",
    "build_run_analysis_snapshot",
    "make_result",
    "make_run",
    "make_service",
    "make_task",
]


def build_run_analysis_snapshot(  # noqa: PLR0913  # test helper exposes every overridable key
    *,
    judge_run_analysis_enabled: bool = True,
    benchmark_min_timeout_seconds: int = 300,
    benchmark_max_timeout_seconds: int = 900,
    benchmark_retry_count: int = 3,
    benchmark_consecutive_max_timeouts_to_exclude: int = 3,
    judge_min_seconds: int = 20,
    judge_max_seconds: int = 120,
    judge_escalation_steps: int = 2,
    judge_consecutive_threshold: int = 3,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a valid run-settings snapshot: the 8 adaptive-timeout keys the
    ``AdaptiveTimeoutService`` factory requires, plus the run-analysis feature flag.

    Args:
        judge_run_analysis_enabled: ``feature.judge_run_analysis_enabled`` override.
        benchmark_min_timeout_seconds: ``benchmark.min_timeout_seconds`` override.
        benchmark_max_timeout_seconds: ``benchmark.max_timeout_seconds`` override.
        benchmark_retry_count: ``benchmark.retry_count`` override.
        benchmark_consecutive_max_timeouts_to_exclude:
            ``benchmark.consecutive_max_timeouts_to_exclude`` override.
        judge_min_seconds: ``eval.judge_timeout_min_seconds`` override.
        judge_max_seconds: ``eval.judge_timeout_max_seconds`` override.
        judge_escalation_steps: ``eval.judge_timeout_escalation_steps`` override.
        judge_consecutive_threshold: ``eval.judge_timeout_consecutive_threshold`` override.

    Returns:
        A tuple of ``BenchmarkRunSettingEntry`` rows covering every key this
        module's service consults from a run snapshot.
    """
    values: dict[str, str] = {
        "feature.judge_run_analysis_enabled": str(judge_run_analysis_enabled).lower(),
        "benchmark.min_timeout_seconds": str(benchmark_min_timeout_seconds),
        "benchmark.max_timeout_seconds": str(benchmark_max_timeout_seconds),
        "benchmark.retry_count": str(benchmark_retry_count),
        "benchmark.consecutive_max_timeouts_to_exclude": str(
            benchmark_consecutive_max_timeouts_to_exclude
        ),
        "eval.judge_timeout_min_seconds": str(judge_min_seconds),
        "eval.judge_timeout_max_seconds": str(judge_max_seconds),
        "eval.judge_timeout_escalation_steps": str(judge_escalation_steps),
        "eval.judge_timeout_consecutive_threshold": str(judge_consecutive_threshold),
    }
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
        for key, value in values.items()
    )


def make_run(  # noqa: PLR0913  # test helper exposes every field a service test may need to vary
    *,
    run_id: RunId = 1,
    run_mode: RunMode = RunMode.GRADED,
    status: RunStatus = RunStatus.COMPLETED,
    run_analysis: str | None = None,
    models: tuple[BenchmarkRunModelEntry, ...] = (),
    providers: tuple[BenchmarkRunProviderEntry, ...] = (),
    settings_snapshot: tuple[BenchmarkRunSettingEntry, ...] | None = None,
) -> BenchmarkRun:
    """Build a minimal, valid ``BenchmarkRun`` for service-level tests."""
    return BenchmarkRun(
        run_id=run_id,
        run_name="r",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=run_mode,
        status=status,
        total_tasks=1,
        completed_tasks=1,
        total_elapsed_ms=1000,
        run_analysis=run_analysis,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:05:00Z",
        models=models,
        providers=providers,
        settings_snapshot=(
            settings_snapshot if settings_snapshot is not None else build_run_analysis_snapshot()
        ),
    )


def make_task(*, task_id: str = "t1") -> BenchmarkTask:
    """Build a minimal, valid ``BenchmarkTask``."""
    return BenchmarkTask(task_id=task_id, task_origin=TaskOrigin.FILE, question="q?")


def make_result(  # noqa: PLR0913  # test helper exposes every field a service test may need to vary
    *,
    result_id: int = 1,
    run_id: RunId = 1,
    task_id: str = "t1",
    provider_id: str = "p1",
    model_name: str = "m1",
    status: ResultStatus = ResultStatus.COMPLETED,
    verdict: Verdict | None = None,
) -> BenchmarkResult:
    """Build a minimal, valid ``BenchmarkResult``."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id=task_id,
        provider_id=provider_id,
        provider_name=provider_id,
        model_name=model_name,
        status=status,
        verdict=verdict,
        created_at="2026-01-01T00:00:00Z",
        ttft_ms=100,
        total_time_ms=500,
        tokens_per_second=20.0,
    )


class FakeClock:
    """A fully controllable ``Clock`` double."""

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms

    def now_utc(self) -> Iso8601Utc:
        """Return a fixed ISO-8601 UTC instant; wall-clock value is irrelevant here."""
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        """Return the fake's current monotonic millisecond counter."""
        return self._monotonic_ms

    def advance_monotonic_ms(self, delta_ms: int) -> None:
        """Move the monotonic counter forward by ``delta_ms``."""
        self._monotonic_ms += delta_ms


class _NoopSubscription:
    """A ``Subscription`` double; never cancelled in this module's tests."""

    def cancel(self) -> None:
        """No-op."""


class FakeEventBus:
    """An in-memory ``EventBus`` double recording every emitted signal/payload pair."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Unused by this module's tests; returns a no-op subscription."""
        del signal_name, handler, owner
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emission."""
        self.emitted.append((signal_name, payload))


class StaticChatStream:
    """A ``ChatStream`` double yielding canned chunks, then a trailing response."""

    def __init__(self, *, chunks: tuple[ChatChunk, ...] = (), response: ChatResponse) -> None:
        self._chunks = chunks
        self._response = response

    def __iter__(self) -> "StaticChatStream":
        return self

    def __next__(self) -> ChatChunk:
        if not self._chunks:
            raise StopIteration
        chunk, *rest = self._chunks
        self._chunks = tuple(rest)
        return chunk

    def trailing_response(self) -> ChatResponse:
        """Return the canned completed response."""
        return self._response


class FakeLLMClient:
    """A controllable ``LLMClient`` double whose ``chat_stream`` behavior is queued.

    Each queued item is either a ``ChatStream`` (returned) or a ``BaseException``
    instance (raised) — consumed in FIFO order, one per ``chat_stream`` call.
    """

    def __init__(self) -> None:
        self.chat_stream_calls: list[ChatRequest] = []
        self._queue: list[ChatStream | BaseException] = []

    def queue_chat_stream(self, item: ChatStream | BaseException) -> None:
        """Queue the next ``chat_stream`` call's outcome."""
        self._queue.append(item)

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        """Pop and apply the next queued outcome."""
        del token
        self.chat_stream_calls.append(request)
        if not self._queue:
            raise AssertionError("FakeLLMClient.chat_stream called with no queued behavior")
        item = self._queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def list_models(self) -> tuple[ModelName, ...]:
        """Unused by this module's tests."""
        raise NotImplementedError

    def probe_health(self) -> ProviderHealth:
        """Unused by this module's tests."""
        raise NotImplementedError

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Unused by this module's tests."""
        raise NotImplementedError

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Unused by this module's tests."""
        raise NotImplementedError

    def embed(self, text: str) -> tuple[float, ...]:
        """Unused by this module's tests."""
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        """Fixed capability answer; unused by this module's assertions."""
        return True

    def supports_reasoning_effort(self) -> bool:
        """Fixed capability answer; unused by this module's assertions."""
        return False

    def supports_thinking(self) -> bool:
        """Fixed capability answer; unused by this module's assertions."""
        return False

    def close(self) -> None:
        """Unused by this module's tests."""


class FakeProviderRegistry:
    """A ``ProviderRegistry`` double returning one fixed ``LLMClient``."""

    def __init__(self, *, client: FakeLLMClient) -> None:
        self._client = client
        self.get_client_calls: list[ProviderId] = []

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Unused by this module's tests."""
        raise NotImplementedError

    def get_client(self, provider_id: ProviderId) -> FakeLLMClient:
        """Record the call and return the fixed client."""
        self.get_client_calls.append(provider_id)
        return self._client

    def reload(self) -> None:
        """Unused by this module's tests."""
        raise NotImplementedError


class FakeRunsStore:
    """A ``RunsStore`` double serving one fixed ``BenchmarkRun``."""

    def __init__(self, *, run: BenchmarkRun) -> None:
        self._run = run

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Unused by this module's tests."""
        raise NotImplementedError

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Return the fixed run regardless of ``run_id``."""
        del run_id
        return self._run

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Unused by this module's tests."""
        raise NotImplementedError

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Unused by this module's tests."""
        raise NotImplementedError

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        """Unused by this module's tests."""
        raise NotImplementedError

    def delete_run(self, run_id: RunId) -> None:
        """Unused by this module's tests."""
        raise NotImplementedError


class FakeTasksStore:
    """A ``TasksStore`` double serving one fixed task tuple."""

    def __init__(self, *, tasks: tuple[BenchmarkTask, ...] = ()) -> None:
        self._tasks = tasks

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Unused by this module's tests."""
        raise NotImplementedError

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return the fixed tasks regardless of ``run_id``."""
        del run_id
        return self._tasks


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh, controllable ``Clock`` double."""
    return FakeClock()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    """A fresh, recording ``EventBus`` double."""
    return FakeEventBus()


@pytest.fixture
def fake_inference_activity_store(
    fake_clock: FakeClock, fake_event_bus: FakeEventBus
) -> FakeInferenceActivityStore:
    """A fresh ``InferenceActivityStore`` fake, always idle at construction."""
    return FakeInferenceActivityStore(clock=fake_clock, event_bus=fake_event_bus)


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    """A fresh, controllable ``LLMClient`` double."""
    return FakeLLMClient()


@pytest.fixture
def fake_provider_registry(fake_llm_client: FakeLLMClient) -> FakeProviderRegistry:
    """A fresh ``ProviderRegistry`` double wired to ``fake_llm_client``."""
    return FakeProviderRegistry(client=fake_llm_client)


@pytest.fixture
def fake_runs_store() -> FakeRunsStore:
    """A ``RunsStore`` double serving a single default GRADED, COMPLETED run."""
    return FakeRunsStore(run=make_run())


@pytest.fixture
def fake_results_store() -> FakeResultsStore:
    """A ``ResultsStore`` double with no seeded rows."""
    return FakeResultsStore()


@pytest.fixture
def fake_tasks_store() -> FakeTasksStore:
    """A ``TasksStore`` double with no seeded rows."""
    return FakeTasksStore()


def make_service(  # noqa: PLR0913  # test factory forwards every constructor dependency
    *,
    runs_store: RunsStore,
    results_store: ResultsStore,
    tasks_store: TasksStore,
    provider_registry: ProviderRegistry,
    inference_activity_store: InferenceActivityStore,
    event_bus: EventBus,
    clock: Clock,
    timeout_cache: RunAdaptiveTimeoutCache | None = None,
) -> RunAnalysisServiceImpl:
    """Construct a ``RunAnalysisServiceImpl`` directly against test doubles.

    Bypasses ``make_run_analysis_service`` (which is not yet defined until
    Task 10) so Task 9's service-level tests can exercise the concrete
    implementation, including its ``inside_pipeline`` extension, ahead of the
    public factory's existence. ``timeout_cache`` may be pre-populated by a
    caller that needs to inspect/drive the real ``AdaptiveTimeoutService``
    before or after the ``generate()`` call under test.
    """
    return RunAnalysisServiceImpl(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        provider_registry=provider_registry,
        inference_activity_store=inference_activity_store,
        event_bus=event_bus,
        clock=clock,
        timeout_cache=timeout_cache if timeout_cache is not None else RunAdaptiveTimeoutCache(),
    )
