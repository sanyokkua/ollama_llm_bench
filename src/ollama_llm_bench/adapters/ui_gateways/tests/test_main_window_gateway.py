"""Unit tests for the concrete ``MainWindowGateway`` (STORY-105).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.1, §12, §4 (the threading contract);
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a.

No ``QApplication`` is constructed anywhere in this file: the gateway holds no Qt symbol,
and ``make_run_dispatcher()`` (used for STORY-105-AC-2) returns a plain
``threading.Thread`` + ``queue.Queue`` dispatcher that needs no live Qt application to
run (see ``adapters/qt_benchmark_flow/_internal/dispatcher_thread.py``'s docstring).

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` — each gateway method hits a *different* collaborator by a
*different* method name (the deliberate asymmetries this story documents: the three
nullable getters read ``AppSettingsStore.get_setting`` while the setters write through
``SettingsService.set``; ``get_theme`` reads ``SettingsService.get_str``; ``is_run_active``
maps to ``flow.is_running()``), so a single shared ``Mock(spec=Protocol)`` per
collaborator would not let each row assert both "the right collaborator got the right
call" and "no other collaborator/method was touched" as precisely as a purpose-built fake.
Every fake raises on a method the gateway must never call, so a wrong-collaborator wiring
bug fails loudly instead of silently no-op'ing.
"""

from collections.abc import Callable
import threading
from typing import Final

import pytest

from ollama_llm_bench.adapters.qt_benchmark_flow import make_run_dispatcher
from ollama_llm_bench.adapters.ui_gateways import MainWindowGateway, make_main_window_gateway
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import RunDispatcher
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkRun,
    ProviderHealth,
    ProviderId,
    ReadinessState,
    RunId,
    RunStartRequest,
    SettingKey,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

_KEY_WINDOW_GEOMETRY: Final[SettingKey] = "ui.window_geometry"
_KEY_SPLITTER_SIZES: Final[SettingKey] = "ui.splitter_sizes"
_KEY_ACTIVE_WORKSPACE: Final[SettingKey] = "ui.active_workspace"
_KEY_THEME: Final[SettingKey] = "ui.theme"


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeAppSettingsStore:
    """Records every ``get_setting`` call; the other three methods must never be hit."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("MainWindowGateway must never write through AppSettingsStore")

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("MainWindowGateway must never write through AppSettingsStore")

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("MainWindowGateway must never write through AppSettingsStore")

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("MainWindowGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError(
            "MainWindowGateway must never call AppSettingsStore.get_schema_version"
        )


class _FakeSettingsService:
    """Records ``get_str``/``set`` calls; the numeric getters and ``upsert`` must never fire."""

    def __init__(self, *, str_values: dict[SettingKey, str] | None = None) -> None:
        self._str_values: dict[SettingKey, str] = dict(str_values or {})
        self.get_str_calls: list[SettingKey] = []
        self.set_calls: list[tuple[SettingKey, str]] = []

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        self.get_str_calls.append(key)
        return self._str_values[key]

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise AssertionError("MainWindowGateway must never call SettingsService.get_bool")

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        raise AssertionError("MainWindowGateway must never call SettingsService.get_int")

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise AssertionError("MainWindowGateway must never call SettingsService.get_float")

    def set(self, key: SettingKey, value: str) -> None:
        self.set_calls.append((key, value))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("MainWindowGateway must never call SettingsService.upsert")


class _FakeReadinessService:
    """Records ``snapshot``/``probe_all`` calls; ``probe`` (single-provider) must never fire."""

    def __init__(self, *, snapshot: AppReadinessSnapshot) -> None:
        self._snapshot = snapshot
        self.snapshot_calls = 0
        self.probe_all_calls = 0

    def snapshot(self) -> AppReadinessSnapshot:
        self.snapshot_calls += 1
        return self._snapshot

    def probe_all(self) -> AppReadinessSnapshot:
        self.probe_all_calls += 1
        return self._snapshot

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise AssertionError("MainWindowGateway must never call ReadinessService.probe directly")


class _FakeBenchmarkFlowApi:
    """Records ``is_running``/``shutdown`` calls; the run-control methods must never fire."""

    def __init__(self, *, is_running: bool = False) -> None:
        self._is_running = is_running
        self.is_running_calls = 0
        self.shutdown_calls: list[int] = []

    def start(self, request: RunStartRequest) -> RunId:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.start")

    def resume(self, run_id: RunId) -> None:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.resume")

    def pause(self) -> None:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.pause")

    def resume_paused(self) -> None:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.resume_paused")

    def stop(self) -> None:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.stop")

    def shutdown(self, timeout_ms: int) -> None:
        self.shutdown_calls.append(timeout_ms)

    def is_running(self) -> bool:
        self.is_running_calls += 1
        return self._is_running

    def current_run(self) -> BenchmarkRun | None:
        raise AssertionError("MainWindowGateway must never call BenchmarkFlowApi.current_run")


class _FakeRunDispatcher:
    """Records every ``submit`` call without running the submitted callable."""

    def __init__(self) -> None:
        self.submit_calls: list[Callable[[], None]] = []

    def submit(self, fn: Callable[[], None]) -> None:
        self.submit_calls.append(fn)

    def shutdown(self, timeout_ms: int) -> None:
        raise AssertionError("MainWindowGateway must never call RunDispatcher.shutdown")


def _make_snapshot() -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
    )


def _make_gateway(
    *,
    app_settings: AppSettingsStore | None = None,
    settings: SettingsService | None = None,
    readiness: ReadinessService | None = None,
    flow: BenchmarkFlowApi | None = None,
    dispatcher: RunDispatcher | None = None,
) -> MainWindowGateway:
    return make_main_window_gateway(
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        settings=settings if settings is not None else _FakeSettingsService(),
        readiness=readiness
        if readiness is not None
        else _FakeReadinessService(snapshot=_make_snapshot()),
        flow=flow if flow is not None else _FakeBenchmarkFlowApi(),
        dispatcher=dispatcher if dispatcher is not None else _FakeRunDispatcher(),
    )


# -- STORY-105-AC-1 -----------------------------------------------------------------------


def _case_get_window_geometry_returns_none_when_unset() -> None:
    # Arrange -- an empty store: the key was never persisted.
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_window_geometry()

    # Assert
    assert app_settings.get_setting_calls == [_KEY_WINDOW_GEOMETRY]
    assert result is None


def _case_set_window_geometry_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_window_geometry("geometry-blob")

    # Assert
    assert settings.set_calls == [(_KEY_WINDOW_GEOMETRY, "geometry-blob")]


def _case_get_splitter_sizes_returns_the_stored_value_unchanged() -> None:
    # Arrange
    app_settings = _FakeAppSettingsStore(values={_KEY_SPLITTER_SIZES: "100,200"})
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_splitter_sizes()

    # Assert
    assert app_settings.get_setting_calls == [_KEY_SPLITTER_SIZES]
    assert result == "100,200"


def _case_set_splitter_sizes_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_splitter_sizes("100,200")

    # Assert
    assert settings.set_calls == [(_KEY_SPLITTER_SIZES, "100,200")]


def _case_get_active_workspace_returns_none_when_unset() -> None:
    # Arrange
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_active_workspace()

    # Assert
    assert app_settings.get_setting_calls == [_KEY_ACTIVE_WORKSPACE]
    assert result is None


def _case_set_active_workspace_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_active_workspace("task_editor")

    # Assert
    assert settings.set_calls == [(_KEY_ACTIVE_WORKSPACE, "task_editor")]


def _case_get_theme_resolves_through_settings_service() -> None:
    # Arrange -- get_theme must go through SettingsService.get_str, not the store,
    # because the resolved theme is never absent (the default layer floors it).
    settings = _FakeSettingsService(str_values={_KEY_THEME: "dark"})
    gateway = _make_gateway(settings=settings)

    # Act
    result = gateway.get_theme()

    # Assert
    assert settings.get_str_calls == [_KEY_THEME]
    assert result == "dark"


def _case_set_theme_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_theme("light")

    # Assert
    assert settings.set_calls == [(_KEY_THEME, "light")]


def _case_readiness_snapshot_returns_the_current_snapshot_without_probing() -> None:
    # Arrange
    canned_snapshot = _make_snapshot()
    readiness = _FakeReadinessService(snapshot=canned_snapshot)
    gateway = _make_gateway(readiness=readiness)

    # Act
    result = gateway.readiness_snapshot()

    # Assert
    assert readiness.snapshot_calls == 1
    assert readiness.probe_all_calls == 0
    assert result is canned_snapshot


def _case_reprobe_submits_a_probe_to_the_dispatcher_and_returns_none() -> None:
    # Arrange
    readiness = _FakeReadinessService(snapshot=_make_snapshot())
    dispatcher = _FakeRunDispatcher()
    gateway = _make_gateway(readiness=readiness, dispatcher=dispatcher)

    # Act -- reprobe() is statically typed -> None; there is no return value to
    # capture (that "returns None" half of the criterion is enforced by mypy).
    gateway.reprobe()

    # Assert -- exactly one callable handed to the dispatcher, no wait for it to run.
    assert len(dispatcher.submit_calls) == 1
    assert readiness.probe_all_calls == 0

    # Running the submitted callable is what bridges to ReadinessService.probe_all —
    # proving reprobe() wired the *right* work into the dispatcher, not a no-op closure.
    dispatcher.submit_calls[0]()
    assert readiness.probe_all_calls == 1


def _case_is_run_active_maps_to_flow_is_running() -> None:
    # Arrange -- the gateway method name and the flow method name deliberately differ.
    flow = _FakeBenchmarkFlowApi(is_running=True)
    gateway = _make_gateway(flow=flow)

    # Act
    result = gateway.is_run_active()

    # Assert
    assert flow.is_running_calls == 1
    assert result is True


def _case_shutdown_calls_flow_shutdown_with_the_given_timeout() -> None:
    # Arrange
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)

    # Act
    gateway.shutdown(4321)

    # Assert
    assert flow.shutdown_calls == [4321]


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("get_window_geometry", _case_get_window_geometry_returns_none_when_unset),
    ("set_window_geometry", _case_set_window_geometry_writes_through_settings_service),
    ("get_splitter_sizes", _case_get_splitter_sizes_returns_the_stored_value_unchanged),
    ("set_splitter_sizes", _case_set_splitter_sizes_writes_through_settings_service),
    ("get_active_workspace", _case_get_active_workspace_returns_none_when_unset),
    ("set_active_workspace", _case_set_active_workspace_writes_through_settings_service),
    ("get_theme", _case_get_theme_resolves_through_settings_service),
    ("set_theme", _case_set_theme_writes_through_settings_service),
    ("readiness_snapshot", _case_readiness_snapshot_returns_the_current_snapshot_without_probing),
    ("reprobe", _case_reprobe_submits_a_probe_to_the_dispatcher_and_returns_none),
    ("is_run_active", _case_is_run_active_maps_to_flow_is_running),
    ("shutdown", _case_shutdown_calls_flow_shutdown_with_the_given_timeout),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-105-AC-1

    For each of the twelve ``MainWindowGateway`` methods, calling it performs
    exactly the stated interaction against its injected collaborator (the right
    collaborator, the right method, the right key/value) and returns that
    collaborator's value unchanged. Table-driven, one row per method, because the
    variation across all twelve rows — which collaborator, which method name, which
    settings key — is a finite enumerable set and is the point of the criterion.
    """
    # Arrange / Act / Assert -- each case is a fully self-contained scenario so
    # every row exercises its own fresh collaborators with no shared mutable state.
    _name, run_case = case
    run_case()


# -- STORY-105-AC-2 -----------------------------------------------------------------------

_PROBE_RELEASE_TIMEOUT_S: Final[float] = 3.0
_WAIT_TIMEOUT_S: Final[float] = 5.0

# The name `_ThreadRunDispatcher` gives its thread (DD-38,
# `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a). Asserting on it is what
# distinguishes "ran on the dispatcher" from "ran on any background thread".
_DISPATCHER_THREAD_NAME: Final[str] = "pipeline-dispatcher"


class _BlockingReadinessService:
    """Records the probing thread's identity, then blocks until released.

    ``started`` fires the moment ``probe_all`` begins running (on whatever thread
    that turns out to be); ``finished`` fires only after the internal wait
    returns — either because the test released it, or (in a buggy inline
    implementation) because the internal wait's own bounded timeout elapsed.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = threading.Event()
        self.recorded_thread_ids: list[int] = []
        self.recorded_thread_names: list[str] = []

    def snapshot(self) -> AppReadinessSnapshot:
        raise AssertionError("this test only exercises probe_all via reprobe()")

    def probe_all(self) -> AppReadinessSnapshot:
        self.recorded_thread_ids.append(threading.get_ident())
        self.recorded_thread_names.append(threading.current_thread().name)
        self.started.set()
        self.release.wait(timeout=_PROBE_RELEASE_TIMEOUT_S)
        self.finished.set()
        return _make_snapshot()

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise AssertionError("this test only exercises probe_all via reprobe()")


def test_reprobe_runs_the_probe_on_the_dispatcher_thread() -> None:
    """Proves: STORY-105-AC-2

    Given a gateway wired to a real ``RunDispatcher`` (a plain
    ``threading.Thread`` + ``queue.Queue``, needing no live ``QApplication``) and a
    readiness service that records the thread it was probed on and then blocks,
    when ``reprobe()`` is called from this test's own thread,
    then ``reprobe()`` returns before the probe completes and the probe itself runs
    on the dispatcher thread, never on the calling (graphical) thread.
    """
    # Arrange
    dispatcher = make_run_dispatcher()
    readiness = _BlockingReadinessService()
    gateway = _make_gateway(readiness=readiness, dispatcher=dispatcher)
    calling_thread_id = threading.get_ident()

    try:
        # Act
        gateway.reprobe()

        # Assert 1 -- reprobe() already returned control to this thread. Had the
        # probe run inline on the calling thread, this line would only be reached
        # after the probe's own internal wait had already timed out and set
        # `finished` -- so `finished` being unset here proves reprobe() did not
        # run the probe on this thread before returning.
        assert not readiness.finished.is_set()

        # Assert 2 -- the probe does start shortly after, on some other thread.
        assert readiness.started.wait(timeout=_WAIT_TIMEOUT_S), (
            "the readiness probe never started on the dispatcher thread"
        )
        assert not readiness.finished.is_set()

        # Act -- release the probe and let it settle.
        readiness.release.set()
        assert readiness.finished.wait(timeout=_WAIT_TIMEOUT_S), (
            "the readiness probe never finished after being released"
        )

        # Assert 3 -- it ran exactly once, on a thread other than this test's own.
        assert readiness.recorded_thread_ids == [readiness.recorded_thread_ids[0]]
        assert readiness.recorded_thread_ids[0] != calling_thread_id

        # Assert 4 -- and that other thread is specifically the pipeline dispatcher,
        # not merely "some" background thread. Without this, submitting to a
        # `TaskRunner` worker pool -- the very thing AC-2 was amended to forbid --
        # would still satisfy Assert 3.
        assert readiness.recorded_thread_names == [_DISPATCHER_THREAD_NAME]
    finally:
        readiness.release.set()
        dispatcher.shutdown(timeout_ms=5000)


# -- STORY-105-AC-3 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Proves: STORY-105-AC-3

    Given fake settings, readiness, and flow collaborators that record every call,
    when ``make_main_window_gateway(...)`` is called,
    then the factory returns a gateway and no method was invoked on any of the
    three collaborators -- construction performs no backend read, no probe, and no
    network call.
    """
    # Arrange
    app_settings = _FakeAppSettingsStore()
    settings = _FakeSettingsService()
    readiness = _FakeReadinessService(snapshot=_make_snapshot())
    flow = _FakeBenchmarkFlowApi()
    dispatcher = _FakeRunDispatcher()

    # Act
    gateway = make_main_window_gateway(
        app_settings=app_settings,
        settings=settings,
        readiness=readiness,
        flow=flow,
        dispatcher=dispatcher,
    )

    # Assert
    assert gateway is not None
    assert app_settings.get_setting_calls == []
    assert settings.get_str_calls == []
    assert settings.set_calls == []
    assert readiness.snapshot_calls == 0
    assert readiness.probe_all_calls == 0
    assert flow.is_running_calls == 0
    assert flow.shutdown_calls == []
    assert dispatcher.submit_calls == []
