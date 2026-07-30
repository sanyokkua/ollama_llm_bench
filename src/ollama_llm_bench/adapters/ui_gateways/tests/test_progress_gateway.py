"""Unit tests for the concrete ``ProgressGateway`` (STORY-107).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.4, §7b, §4 (the threading contract).

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` -- each gateway method hits a *different* collaborator by a
*different* method name, so a purpose-built fake lets each row assert both "the right
collaborator got the right call" and "no other collaborator/method was touched," per
this module's established test-plan convention (``test_new_benchmark_gateway.py``).
Every fake raises on a method the gateway must never call.
"""

from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
import threading
from typing import Final

import pytest

from ollama_llm_bench.adapters.ui_gateways import ProgressGateway, make_progress_gateway
from ollama_llm_bench.adapters.ui_gateways._internal.progress.gateway import (
    ManualProviderProbeCommand,
    RunLogWriteStatus,
)
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    Iso8601Utc,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    SettingKey,
)
from ollama_llm_bench.backend.infra.protocols import PlatformDetector
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.settings import SettingsService

_KEY_VERBOSITY: Final[SettingKey] = "ui.run_log_verbosity"
_KNOWN_RUN_ID: Final[RunId] = 42
_ANOTHER_RUN_ID: Final[RunId] = 7


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeBenchmarkFlowApi:
    """Records pause/resume_paused/stop/is_running calls; other methods must never fire."""

    def __init__(self, *, running: bool = False) -> None:
        self.pause_calls = 0
        self.resume_paused_calls = 0
        self.stop_calls = 0
        self.is_running_calls = 0
        self._running = running
        self.cancelled = False

    def start(self, request: object) -> RunId:
        raise AssertionError("ProgressGateway must never call BenchmarkFlowApi.start")

    def resume(self, run_id: RunId) -> None:
        raise AssertionError("ProgressGateway must never call BenchmarkFlowApi.resume")

    def pause(self) -> None:
        self.pause_calls += 1

    def resume_paused(self) -> None:
        self.resume_paused_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1
        self.cancelled = True

    def shutdown(self, timeout_ms: int) -> None:
        raise AssertionError("ProgressGateway must never call BenchmarkFlowApi.shutdown")

    def is_running(self) -> bool:
        self.is_running_calls += 1
        return self._running

    def current_run(self) -> BenchmarkRun | None:
        raise AssertionError("ProgressGateway must never call BenchmarkFlowApi.current_run")


class _FakeRunsStore:
    """Records get_run/rename_run/list_runs calls; other methods must never fire."""

    def __init__(
        self, *, run: BenchmarkRun | None = None, runs: tuple[BenchmarkRun, ...] = ()
    ) -> None:
        self._run = run
        self._runs = runs
        self.get_run_calls: list[RunId] = []
        self.rename_run_calls: list[tuple[RunId, str | None]] = []
        self.list_runs_calls = 0

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise AssertionError("ProgressGateway must never call RunsStore.create_run")

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        self.get_run_calls.append(run_id)
        assert self._run is not None
        return self._run

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        self.list_runs_calls += 1
        return self._runs

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise AssertionError("ProgressGateway must never call RunsStore.update_run_status")

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        self.rename_run_calls.append((run_id, run_name))

    def delete_run(self, run_id: RunId) -> None:
        raise AssertionError("ProgressGateway must never call RunsStore.delete_run")


class _FakeResultsStore:
    """Records list_results calls; other methods must never fire."""

    def __init__(self, *, results: tuple[BenchmarkResult, ...] = ()) -> None:
        self._results = results
        self.list_results_calls: list[RunId] = []

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        raise AssertionError("ProgressGateway must never call ResultsStore.create_results")

    def update_result(self, result_id: object, patch: object) -> None:
        raise AssertionError("ProgressGateway must never call ResultsStore.update_result")

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        self.list_results_calls.append(run_id)
        return self._results

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise AssertionError("ProgressGateway must never call ResultsStore.list_resumable_results")

    def reset_results(self, result_ids: tuple[object, ...]) -> int:
        raise AssertionError("ProgressGateway must never call ResultsStore.reset_results")

    def reset_results_for_retry(self, result_ids: tuple[object, ...]) -> int:
        raise AssertionError("ProgressGateway must never call ResultsStore.reset_results_for_retry")

    def recover_in_flight_results(self) -> int:
        raise AssertionError(
            "ProgressGateway must never call ResultsStore.recover_in_flight_results"
        )


class _FakeAppSettingsStore:
    """Records get_setting calls; other methods must never fire."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("ProgressGateway must never call AppSettingsStore.upsert_settings")

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("ProgressGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError("ProgressGateway must never call AppSettingsStore.get_schema_version")


class _FakeSettingsService:
    """Records set calls; every getter must never fire."""

    def __init__(self) -> None:
        self.set_calls: list[tuple[SettingKey, str]] = []

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        raise AssertionError("ProgressGateway must never call SettingsService.get_str")

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise AssertionError("ProgressGateway must never call SettingsService.get_bool")

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        raise AssertionError("ProgressGateway must never call SettingsService.get_int")

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise AssertionError("ProgressGateway must never call SettingsService.get_float")

    def set(self, key: SettingKey, value: str) -> None:
        self.set_calls.append((key, value))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("ProgressGateway must never call SettingsService.upsert")


class _FakePlatformDetector:
    """Supplies a tmp_path-backed app_data_root; nothing else is exercised."""

    def __init__(self, *, app_data_root: Path | None) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        assert self._app_data_root is not None
        return self._app_data_root


class _FakeClock:
    """A trivial Clock -- only used to construct a fresh CancellationToken."""

    def now_utc(self) -> Iso8601Utc:
        return "2026-07-30T00:00:00Z"

    def monotonic_ms(self) -> int:
        return 0


class _FakeProbeCommand:
    """Records the thread it ran on; never called at construction time."""

    def __init__(self) -> None:
        self.probe_calls = 0
        self.recorded_thread_ids: list[int] = []

    def probe(self) -> None:
        self.probe_calls += 1
        self.recorded_thread_ids.append(threading.get_ident())


class _FakeWriteStatus:
    """Records write_failed calls; returns a configured, fixed answer."""

    def __init__(self, *, failed: bool) -> None:
        self._failed = failed
        self.write_failed_calls = 0

    def write_failed(self) -> bool:
        self.write_failed_calls += 1
        return self._failed


class _ThreadTaskRunner:
    """Runs each submitted unit on a brand-new ``threading.Thread`` and returns an
    unresolved ``Future`` immediately -- a minimal stand-in for the real
    ``QThreadPool``-backed ``TaskRunner`` (``adapters/qt_runnables``), whose
    contract requires only "submitted work runs off the calling thread." Used
    instead of the real Qt-bound runner so this colocated adapter test needs no
    live ``QApplication`` (same reasoning ``test_main_window_gateway.py`` gives
    for using a plain-``threading`` fake over the Qt one).
    """

    def __init__(self) -> None:
        self.submit_calls: list[Callable[[], object]] = []

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        self.submit_calls.append(fn)
        future: Future[object] = Future()

        def _run() -> None:
            future.set_result(fn())

        threading.Thread(target=_run, daemon=True).start()
        return future


def _make_run(*, run_id: RunId = _KNOWN_RUN_ID) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=None,
        timestamp="2026-07-30T00:00:00Z",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_result(*, run_id: RunId = _KNOWN_RUN_ID) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=1,
        run_id=run_id,
        task_id="task-1",
        provider_id="11111111-1111-1111-1111-111111111111",
        provider_name="local-ollama",
        model_name="llama3",
        status=ResultStatus.PENDING,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_gateway(  # noqa: PLR0913  # test factory forwards every constructor dependency
    *,
    flow: BenchmarkFlowApi | None = None,
    runs_store: RunsStore | None = None,
    results_store: ResultsStore | None = None,
    app_settings: AppSettingsStore | None = None,
    settings: SettingsService | None = None,
    platform_detector: PlatformDetector | None = None,
    task_runner: object = None,
    clock: object = None,
    probe_command: ManualProviderProbeCommand | None = None,
    write_status: RunLogWriteStatus | None = None,
    tmp_path: Path | None = None,
) -> ProgressGateway:
    return make_progress_gateway(
        flow=flow if flow is not None else _FakeBenchmarkFlowApi(),
        runs_store=runs_store if runs_store is not None else _FakeRunsStore(run=_make_run()),
        results_store=results_store if results_store is not None else _FakeResultsStore(),
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        settings=settings if settings is not None else _FakeSettingsService(),
        platform_detector=platform_detector
        if platform_detector is not None
        else _FakePlatformDetector(app_data_root=tmp_path),
        task_runner=task_runner if task_runner is not None else _ThreadTaskRunner(),  # type: ignore[arg-type]
        clock=clock if clock is not None else _FakeClock(),  # type: ignore[arg-type]
        probe_command=probe_command if probe_command is not None else _FakeProbeCommand(),
        write_status=write_status if write_status is not None else _FakeWriteStatus(failed=False),
    )


# -- STORY-107-AC-1 -----------------------------------------------------------------------


def _case_pause_run() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)
    gateway.pause_run()
    assert flow.pause_calls == 1


def _case_resume_run() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)
    gateway.resume_run()
    assert flow.resume_paused_calls == 1


def _case_stop_run() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)
    gateway.stop_run("user clicked stop")
    assert flow.stop_calls == 1


def _case_run_metadata() -> None:
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    gateway = _make_gateway(runs_store=runs_store)
    result = gateway.run_metadata(_KNOWN_RUN_ID)
    assert runs_store.get_run_calls == [_KNOWN_RUN_ID]
    assert result is run


def _case_rename_run() -> None:
    runs_store = _FakeRunsStore(run=_make_run())
    gateway = _make_gateway(runs_store=runs_store)
    gateway.rename_run(_KNOWN_RUN_ID, "my run")
    assert runs_store.rename_run_calls == [(_KNOWN_RUN_ID, "my run")]


def _case_run_header() -> None:
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    gateway = _make_gateway(runs_store=runs_store)
    result = gateway.run_header(_KNOWN_RUN_ID)
    assert runs_store.get_run_calls == [_KNOWN_RUN_ID]
    assert result is run


def _case_task_counters() -> None:
    results = (_make_result(),)
    results_store = _FakeResultsStore(results=results)
    gateway = _make_gateway(results_store=results_store)
    result = gateway.task_counters(_KNOWN_RUN_ID)
    assert results_store.list_results_calls == [_KNOWN_RUN_ID]
    assert result == results


def _case_get_setting_returns_none_when_unset() -> None:
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)
    result = gateway.get_setting(_KEY_VERBOSITY)
    assert app_settings.get_setting_calls == [_KEY_VERBOSITY]
    assert result is None


def _case_get_setting_returns_the_stored_value_unchanged() -> None:
    app_settings = _FakeAppSettingsStore(values={_KEY_VERBOSITY: "verbose"})
    gateway = _make_gateway(app_settings=app_settings)
    result = gateway.get_setting(_KEY_VERBOSITY)
    assert result == "verbose"


def _case_set_setting() -> None:
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)
    gateway.set_setting(_KEY_VERBOSITY, "short")
    assert settings.set_calls == [(_KEY_VERBOSITY, "short")]


def _case_manual_provider_probe() -> None:
    probe_command = _FakeProbeCommand()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(probe_command=probe_command, task_runner=task_runner)
    gateway.manual_provider_probe()
    assert len(task_runner.submit_calls) == 1


def _case_list_runs() -> None:
    runs = (_make_run(), _make_run(run_id=_ANOTHER_RUN_ID))
    runs_store = _FakeRunsStore(runs=runs)
    gateway = _make_gateway(runs_store=runs_store)
    result = gateway.list_runs()
    assert runs_store.list_runs_calls == 1
    assert result == runs


def _case_is_run_active() -> None:
    flow = _FakeBenchmarkFlowApi(running=True)
    gateway = _make_gateway(flow=flow)
    result = gateway.is_run_active()
    assert flow.is_running_calls == 1
    assert result is True


def _case_run_log_write_failed() -> None:
    write_status = _FakeWriteStatus(failed=True)
    gateway = _make_gateway(write_status=write_status)
    result = gateway.run_log_write_failed()
    assert write_status.write_failed_calls == 1
    assert result is True


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("pause_run", _case_pause_run),
    ("resume_run", _case_resume_run),
    ("stop_run", _case_stop_run),
    ("run_metadata", _case_run_metadata),
    ("rename_run", _case_rename_run),
    ("run_header", _case_run_header),
    ("task_counters", _case_task_counters),
    ("get_setting_unset", _case_get_setting_returns_none_when_unset),
    ("get_setting_stored", _case_get_setting_returns_the_stored_value_unchanged),
    ("set_setting", _case_set_setting),
    ("manual_provider_probe", _case_manual_provider_probe),
    ("list_runs", _case_list_runs),
    ("is_run_active", _case_is_run_active),
    ("run_log_write_failed", _case_run_log_write_failed),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-107-AC-1

    For each of the fourteen ``ProgressGateway`` methods, calling it performs
    exactly the stated interaction against its injected collaborator and
    returns that collaborator's value unchanged. Table-driven (plus one extra
    row distinguishing "unset" from "stored" for ``get_setting``), because the
    variation across rows -- which collaborator, which method name -- is a
    finite enumerable set and is the point of the criterion.
    """
    _name, run_case = case
    run_case()


# -- load_past_log (part of STORY-107-AC-1's coverage; needs a real tmp_path, not a fake) ---


def test_load_past_log_returns_the_saved_file_contents(tmp_path: Path) -> None:
    """Proves: STORY-107-AC-1

    Given a run-log file already written under ``<app-data>/logs/run/``, when
    ``load_past_log(run_id)`` is called, then it returns that file's full text
    unchanged.
    """
    log_dir = tmp_path / "logs" / "run"
    log_dir.mkdir(parents=True)
    run_id_text = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    (log_dir / f"run_{run_id_text}_1700000000.log").write_text("line one\nline two\n")
    gateway = _make_gateway(tmp_path=tmp_path)

    result = gateway.load_past_log(run_id_text)  # type: ignore[arg-type]

    assert result == "line one\nline two\n"


def test_load_past_log_returns_empty_string_when_no_file_exists(tmp_path: Path) -> None:
    """Proves: STORY-107-AC-1

    Given no saved run-log file for ``run_id``, when ``load_past_log(run_id)``
    is called, then it returns an empty string rather than raising.
    """
    gateway = _make_gateway(tmp_path=tmp_path)

    result = gateway.load_past_log("no-such-run")  # type: ignore[arg-type]

    assert result == ""


# -- STORY-107-AC-2 -----------------------------------------------------------------------


class _BlockingProbeCommand:
    """Records the probing thread's identity, then blocks until released.

    ``started`` fires the moment ``probe`` begins running (on whatever thread
    that is); the test asserts ``manual_provider_probe()`` already returned to
    the calling thread *before* ``started`` is even set, by racing the two.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.recorded_thread_ids: list[int] = []

    def probe(self) -> None:
        self.recorded_thread_ids.append(threading.get_ident())
        self.started.set()
        self.release.wait(timeout=5.0)


def test_manual_provider_probe_runs_on_a_worker_thread() -> None:
    """Proves: STORY-107-AC-2

    Given a gateway wired to a probe collaborator that records the thread it
    ran on and then blocks, when ``manual_provider_probe()`` is called from
    this test's own thread, then it returns before the probe completes and
    the probe itself runs on a distinct ``TaskRunner`` worker thread, never on
    the calling (graphical) thread.
    """
    probe_command = _BlockingProbeCommand()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(probe_command=probe_command, task_runner=task_runner)
    calling_thread_id = threading.get_ident()

    try:
        gateway.manual_provider_probe()

        assert probe_command.started.wait(timeout=2.0), "the probe never started"

        assert probe_command.recorded_thread_ids == [probe_command.recorded_thread_ids[0]]
        assert probe_command.recorded_thread_ids[0] != calling_thread_id
    finally:
        probe_command.release.set()


# -- STORY-107-AC-3 -----------------------------------------------------------------------


def test_stop_run_sets_the_token_and_returns_promptly() -> None:
    """Proves: STORY-107-AC-3

    Given a run is active, when ``stop_run(reason)`` is called, then the call
    returns immediately (no wait, no polling loop) and the flow API's
    ``stop()`` -- which is what actually marks the run's ``CancellationToken``
    cancelled and never terminates an in-flight worker mid-statement, per the
    pipeline's own already-delivered cooperative-cancellation contract -- was
    invoked exactly once with no argument (``reason`` is accepted for
    ``08-E`` §7b.4 signature parity but never forwarded, since
    ``BenchmarkFlowApi.stop()`` takes none -- ``CancelReason`` is a closed
    enum, never free text, DD-42).
    """
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)

    gateway.stop_run("user clicked stop")

    assert flow.stop_calls == 1
    assert flow.cancelled is True


# -- STORY-107-AC-4 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Proves: STORY-107-AC-4

    Given fake flow, run-registry, runs-store, results-store, run-log-reader,
    settings, and probe collaborators that record every call, when
    ``make_progress_gateway(...)`` is called, then the factory returns a
    gateway and no method was invoked on any collaborator.
    """
    flow = _FakeBenchmarkFlowApi()
    runs_store = _FakeRunsStore(run=_make_run())
    results_store = _FakeResultsStore()
    app_settings = _FakeAppSettingsStore()
    settings = _FakeSettingsService()
    platform_detector = _FakePlatformDetector(app_data_root=None)
    task_runner = _ThreadTaskRunner()
    clock = _FakeClock()
    probe_command = _FakeProbeCommand()
    write_status = _FakeWriteStatus(failed=False)

    gateway = make_progress_gateway(
        flow=flow,
        runs_store=runs_store,
        results_store=results_store,
        app_settings=app_settings,
        settings=settings,
        platform_detector=platform_detector,
        task_runner=task_runner,
        clock=clock,
        probe_command=probe_command,
        write_status=write_status,
    )

    assert gateway is not None
    assert flow.pause_calls == 0
    assert flow.resume_paused_calls == 0
    assert flow.stop_calls == 0
    assert flow.is_running_calls == 0
    assert runs_store.get_run_calls == []
    assert runs_store.rename_run_calls == []
    assert runs_store.list_runs_calls == 0
    assert results_store.list_results_calls == []
    assert app_settings.get_setting_calls == []
    assert settings.set_calls == []
    assert task_runner.submit_calls == []
    assert probe_command.probe_calls == 0
    assert write_status.write_failed_calls == 0
