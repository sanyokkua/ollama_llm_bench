"""Shared fixtures and factories for benchmark_pipeline's colocated tests."""

from collections.abc import Callable
from concurrent.futures import Future
from datetime import UTC, datetime
from typing import cast

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    Difficulty,
    GateLease,
    InferenceActivity,
    Iso8601Utc,
    RequiredTerms,
    ResultPatch,
    TaskOrigin,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore


def make_task(  # noqa: PLR0913  # test builder must expose every unit-relevant field
    *,
    task_id: str = "task-1",
    question: str = "What is the capital of France?",
    category: str = "geography",
    golden_answer: str | None = "Paris",
    cosine_enabled: bool = True,
    required_terms: RequiredTerms | None = None,
    task_origin: TaskOrigin = TaskOrigin.FILE,
) -> BenchmarkTask:
    """Build a minimal, valid `BenchmarkTask` for a pipeline unit test."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=task_origin,
        cosine_enabled=cosine_enabled,
        question=question,
        category=category,
        golden_answer=golden_answer,
        difficulty=Difficulty.MEDIUM,
        required_terms=required_terms if required_terms is not None else RequiredTerms(),
    )


class FakeClock:
    """A minimal, fully controllable `Clock` double (matches the project-wide
    per-module convention already used by `backend/evaluation/tests/conftest.py`).
    """

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        return self._monotonic_ms


def make_cancellation_token() -> CancellationToken:
    """Build a fresh, uncancelled `CancellationToken` backed by a `FakeClock`."""
    return CancellationToken(clock=FakeClock())


@pytest.fixture
def fake_clock() -> Clock:
    """A deterministic `Clock` fixture, fresh per test."""
    return FakeClock()


class _InlineTaskRunner:
    """Runs a unit synchronously on the calling thread — a shared test double.

    Distinct from `test_serial_execution.py`'s own private copy of the same
    shape; that file's colocated copy stays as-is (no cross-test coupling
    needed), this fixture exists for tests spanning multiple test modules
    within this package that need the same inline-runner behaviour.
    """

    def submit(
        self, fn: Callable[[], ResultPatch], *, token: CancellationToken
    ) -> Future[ResultPatch]:
        future: Future[ResultPatch] = Future()
        future.set_result(fn())
        return future


@pytest.fixture
def inline_task_runner() -> _InlineTaskRunner:
    """A `TaskRunner` double that runs every submitted unit synchronously."""
    return _InlineTaskRunner()


@pytest.fixture
def fake_results_store() -> FakeResultsStore:
    """A fresh, empty `FakeResultsStore` per test."""
    return FakeResultsStore()


@pytest.fixture
def fake_runs_store(mocker: MockerFixture) -> RunsStore:
    """A `RunsStore` double with `create_run` defaulted to return run id `1`."""
    store = mocker.Mock(spec=RunsStore)
    store.create_run.return_value = 1
    return cast("RunsStore", store)


@pytest.fixture
def fake_tasks_store(mocker: MockerFixture) -> TasksStore:
    """A `TasksStore` double with `list_tasks` defaulted to an empty tuple."""
    store = mocker.Mock(spec=TasksStore)
    store.list_tasks.return_value = ()
    return cast("TasksStore", store)


@pytest.fixture
def fake_inference_activity_store(mocker: MockerFixture) -> InferenceActivityStore:
    """An `InferenceActivityStore` double granting the gate by default."""
    store = mocker.Mock(spec=InferenceActivityStore)
    store.try_acquire.return_value = GateLease(
        activity=InferenceActivity.BENCHMARK_RUN, lease_id=1, acquired_at=0
    )
    return cast("InferenceActivityStore", store)


class _RecordingEventBus:
    """A minimal `EventBus` double recording every emitted signal name, in order."""

    def __init__(self) -> None:
        self._emitted: list[str] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> None:
        del signal_name, handler, owner  # unused: no test in this package subscribes

    def emit(self, signal_name: str, payload: object) -> None:
        del payload
        self._emitted.append(signal_name)

    def emitted_signal_names(self) -> list[str]:
        """Return every emitted signal name, in emission order."""
        return list(self._emitted)


@pytest.fixture
def fake_event_bus() -> _RecordingEventBus:
    """A fresh `EventBus` recorder per test."""
    return _RecordingEventBus()


@pytest.fixture
def fake_embedding_service(mocker: MockerFixture) -> EmbeddingService:
    """An `EmbeddingService` double; individual tests override its return values."""
    return cast("EmbeddingService", mocker.Mock(spec=EmbeddingService))


@pytest.fixture
def fake_provider_registry(mocker: MockerFixture) -> ProviderRegistry:
    """A `ProviderRegistry` double with `list_enabled` defaulted to empty."""
    registry = mocker.Mock(spec=ProviderRegistry)
    registry.list_enabled.return_value = ()
    return cast("ProviderRegistry", registry)


@pytest.fixture
def fake_settings_service(mocker: MockerFixture) -> SettingsService:
    """A `SettingsService` double: every grading toggle off, generous timeouts."""
    service = mocker.Mock(spec=SettingsService)
    service.get_bool.return_value = False
    service.get_int.return_value = 30
    return cast("SettingsService", service)


@pytest.fixture
def fake_run_snapshot_builder(mocker: MockerFixture) -> RunSnapshotBuilder:
    """A `RunSnapshotBuilder` double carrying every `eval.*` key the evaluation
    module's factories require present (`REQUIRED_EVALUATION_SETTING_KEYS`)."""
    builder = mocker.Mock(spec=RunSnapshotBuilder)
    builder.build_snapshot.return_value = (
        BenchmarkRunSettingEntry(setting_key="eval.sanity_min_chars", setting_value="1"),
        BenchmarkRunSettingEntry(setting_key="eval.sanity_error_markers", setting_value=""),
        BenchmarkRunSettingEntry(
            setting_key="eval.keyword_semantic_pass_threshold", setting_value="0.8"
        ),
        BenchmarkRunSettingEntry(
            setting_key="eval.judge_max_completion_tokens", setting_value="512"
        ),
        BenchmarkRunSettingEntry(setting_key="eval.judge_max_parse_retries", setting_value="2"),
        BenchmarkRunSettingEntry(
            setting_key="eval.force_judge_on_prior_failure", setting_value="false"
        ),
    )
    return cast("RunSnapshotBuilder", builder)
