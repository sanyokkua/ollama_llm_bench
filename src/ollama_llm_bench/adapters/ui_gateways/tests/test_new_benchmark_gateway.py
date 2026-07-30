"""Unit tests for the concrete ``NewBenchmarkGateway`` (STORY-106).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.2, §7b, §4 (the threading contract).

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` — each gateway method hits a *different* collaborator by a
*different* method name (``get_setting``/``set_setting`` split across
``AppSettingsStore.get_setting``/``SettingsService.set``, ``provider_list`` maps to
``ProviderRegistry.list_enabled``, ``readiness_snapshot`` to
``ReadinessService.snapshot``, ``start_run`` to ``BenchmarkFlowApi.start``,
``notify_error`` to an unredacted ``NotificationService.show_error`` — see STORY-106-AC-3
and ``08-E`` §22: UI/display surfaces do not apply redaction), so a single shared
``Mock(spec=Protocol)`` per collaborator would not let each row assert both "the right
collaborator got the right call" and "no other collaborator/method was touched" as
precisely as a purpose-built fake. Every fake raises on a method the gateway must never
call, so a wrong-collaborator wiring bug fails loudly instead of silently no-op'ing.
``FakeNotificationService`` is reused from ``adapters.notification_service.testing``
rather than hand-written, per this module's test-plan convention.
"""

from collections.abc import Callable
from typing import Final

import pytest

from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.ui_gateways import NewBenchmarkGateway, make_new_benchmark_gateway
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkRun,
    ModelDescriptor,
    ProviderConfig,
    ProviderHealth,
    ProviderType,
    ReadinessState,
    RunId,
    RunMode,
    RunStartRequest,
    SettingKey,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.provider_registry import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

_KEY_LAST_MODE: Final[SettingKey] = "benchmark.last_mode"
_KNOWN_RUN_ID: Final[RunId] = 42
_ANOTHER_RUN_ID: Final[RunId] = 7


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeAppSettingsStore:
    """Records every ``get_setting`` call; the other methods must never be hit."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("NewBenchmarkGateway must never write through AppSettingsStore")

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("NewBenchmarkGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError(
            "NewBenchmarkGateway must never call AppSettingsStore.get_schema_version"
        )


class _FakeSettingsService:
    """Records ``set`` calls; every getter must never fire."""

    def __init__(self) -> None:
        self.set_calls: list[tuple[SettingKey, str]] = []

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        raise AssertionError("NewBenchmarkGateway must never call SettingsService.get_str")

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise AssertionError("NewBenchmarkGateway must never call SettingsService.get_bool")

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        raise AssertionError("NewBenchmarkGateway must never call SettingsService.get_int")

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise AssertionError("NewBenchmarkGateway must never call SettingsService.get_float")

    def set(self, key: SettingKey, value: str) -> None:
        self.set_calls.append((key, value))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("NewBenchmarkGateway must never call SettingsService.upsert")


class _FakeProviderRegistry:
    """Records ``list_enabled`` calls; the client-routing methods must never fire."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...]) -> None:
        self._providers = providers
        self.list_enabled_calls = 0

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        self.list_enabled_calls += 1
        return self._providers

    def get_client(self, provider_id: str) -> LLMClient:
        raise AssertionError("NewBenchmarkGateway must never call ProviderRegistry.get_client")

    def reload(self) -> None:
        raise AssertionError("NewBenchmarkGateway must never call ProviderRegistry.reload")


class _FakeReadinessService:
    """Records ``snapshot`` calls; ``probe_all``/``probe`` must never fire."""

    def __init__(self, *, snapshot: AppReadinessSnapshot) -> None:
        self._snapshot = snapshot
        self.snapshot_calls = 0

    def snapshot(self) -> AppReadinessSnapshot:
        self.snapshot_calls += 1
        return self._snapshot

    def probe_all(self) -> AppReadinessSnapshot:
        raise AssertionError("NewBenchmarkGateway must never call ReadinessService.probe_all")

    def probe(self, provider_id: str) -> ProviderHealth:
        raise AssertionError("NewBenchmarkGateway must never call ReadinessService.probe")


class _FakeBenchmarkFlowApi:
    """Records ``start`` calls; every other lifecycle method must never fire."""

    def __init__(self, *, run_id: RunId) -> None:
        self._run_id = run_id
        self.start_calls: list[RunStartRequest] = []

    def start(self, request: RunStartRequest) -> RunId:
        self.start_calls.append(request)
        return self._run_id

    def resume(self, run_id: RunId) -> None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.resume")

    def pause(self) -> None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.pause")

    def resume_paused(self) -> None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.resume_paused")

    def stop(self) -> None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.stop")

    def shutdown(self, timeout_ms: int) -> None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.shutdown")

    def is_running(self) -> bool:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.is_running")

    def current_run(self) -> BenchmarkRun | None:
        raise AssertionError("NewBenchmarkGateway must never call BenchmarkFlowApi.current_run")


def _make_snapshot() -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
    )


def _make_provider(*, name: str = "local-ollama") -> ProviderConfig:
    return ProviderConfig(
        provider_id="11111111-1111-1111-1111-111111111111",
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _make_request() -> RunStartRequest:
    return RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(
            ModelDescriptor(
                provider_id="11111111-1111-1111-1111-111111111111",
                model_name="llama3",
            ),
        ),
    )


def _make_gateway(  # noqa: PLR0913  # test factory forwards every constructor dependency
    *,
    app_settings: AppSettingsStore | None = None,
    settings: SettingsService | None = None,
    provider_registry: ProviderRegistry | None = None,
    readiness: ReadinessService | None = None,
    flow: BenchmarkFlowApi | None = None,
    notification: FakeNotificationService | None = None,
) -> NewBenchmarkGateway:
    return make_new_benchmark_gateway(
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        settings=settings if settings is not None else _FakeSettingsService(),
        provider_registry=provider_registry
        if provider_registry is not None
        else _FakeProviderRegistry(providers=()),
        readiness=readiness
        if readiness is not None
        else _FakeReadinessService(snapshot=_make_snapshot()),
        flow=flow if flow is not None else _FakeBenchmarkFlowApi(run_id=1),
        notification=notification if notification is not None else FakeNotificationService(),
    )


# -- STORY-106-AC-1 -----------------------------------------------------------------------


def _case_get_setting_returns_none_when_unset() -> None:
    # Arrange -- an empty store: the key was never persisted.
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_setting(_KEY_LAST_MODE)

    # Assert
    assert app_settings.get_setting_calls == [_KEY_LAST_MODE]
    assert result is None


def _case_get_setting_returns_the_stored_value_unchanged() -> None:
    # Arrange
    app_settings = _FakeAppSettingsStore(values={_KEY_LAST_MODE: "graded"})
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_setting(_KEY_LAST_MODE)

    # Assert
    assert app_settings.get_setting_calls == [_KEY_LAST_MODE]
    assert result == "graded"


def _case_set_setting_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_setting(_KEY_LAST_MODE, "tasks")

    # Assert
    assert settings.set_calls == [(_KEY_LAST_MODE, "tasks")]


def _case_provider_list_returns_the_registry_order_unchanged() -> None:
    # Arrange
    providers = (_make_provider(name="alpha"), _make_provider(name="beta"))
    provider_registry = _FakeProviderRegistry(providers=providers)
    gateway = _make_gateway(provider_registry=provider_registry)

    # Act
    result = gateway.provider_list()

    # Assert
    assert provider_registry.list_enabled_calls == 1
    assert result == providers


def _case_readiness_snapshot_returns_the_current_snapshot_without_probing() -> None:
    # Arrange
    canned_snapshot = _make_snapshot()
    readiness = _FakeReadinessService(snapshot=canned_snapshot)
    gateway = _make_gateway(readiness=readiness)

    # Act
    result = gateway.readiness_snapshot()

    # Assert
    assert readiness.snapshot_calls == 1
    assert result is canned_snapshot


def _case_start_run_passes_the_request_and_returns_the_run_id() -> None:
    # Arrange
    flow = _FakeBenchmarkFlowApi(run_id=_KNOWN_RUN_ID)
    request = _make_request()
    gateway = _make_gateway(flow=flow)

    # Act
    result = gateway.start_run(request)

    # Assert
    assert flow.start_calls == [request]
    assert result == _KNOWN_RUN_ID


def _case_notify_error_passes_the_message_to_notification_unchanged() -> None:
    # Arrange
    notification = FakeNotificationService()
    gateway = _make_gateway(notification=notification)

    # Act
    gateway.notify_error("plain message")

    # Assert
    assert notification.error_calls == [("plain message", False)]


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("get_setting_unset", _case_get_setting_returns_none_when_unset),
    ("get_setting_stored", _case_get_setting_returns_the_stored_value_unchanged),
    ("set_setting", _case_set_setting_writes_through_settings_service),
    ("provider_list", _case_provider_list_returns_the_registry_order_unchanged),
    ("readiness_snapshot", _case_readiness_snapshot_returns_the_current_snapshot_without_probing),
    ("start_run", _case_start_run_passes_the_request_and_returns_the_run_id),
    ("notify_error", _case_notify_error_passes_the_message_to_notification_unchanged),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-106-AC-1

    For each of the six ``NewBenchmarkGateway`` methods, calling it performs exactly
    the stated interaction against its injected collaborator (the right collaborator,
    the right method, the right key/value) and returns that collaborator's value
    unchanged. Table-driven, one row per method (plus one extra row distinguishing
    "unset" from "stored" for ``get_setting``), because the variation across rows --
    which collaborator, which method name -- is a finite enumerable set and is the
    point of the criterion.
    """
    # Arrange / Act / Assert -- each case is a fully self-contained scenario so every
    # row exercises its own fresh collaborators with no shared mutable state.
    _name, run_case = case
    run_case()


# -- STORY-106-AC-2 -----------------------------------------------------------------------


def test_start_run_returns_the_run_id_without_waiting() -> None:
    """Proves: STORY-106-AC-2

    Given a gateway wired to a flow API whose start entry point records that it was
    called and returns a known run id, when ``start_run(request)`` is called from the
    graphical thread, then it returns that run id immediately -- ``start`` is a plain
    method call with no wait for any run status, so this test's own completion (with
    no blocking or polling) is itself the proof.
    """
    # Arrange
    flow = _FakeBenchmarkFlowApi(run_id=_ANOTHER_RUN_ID)
    request = _make_request()
    gateway = _make_gateway(flow=flow)

    # Act
    result = gateway.start_run(request)

    # Assert
    assert result == _ANOTHER_RUN_ID
    assert flow.start_calls == [request]


# -- STORY-106-AC-3 -----------------------------------------------------------------------


def test_notify_error_passes_the_message_through_unchanged() -> None:
    """Proves: STORY-106-AC-3

    Given a message containing a value the redaction module would otherwise treat as a
    secret (an OpenAI-shaped API key, the same secret shape used in
    ``backend/errors/tests/test_redaction.py``'s RT-01 case), when
    ``notify_error(message)`` is called, then the exact string -- including that
    secret-shaped substring -- reaches the notification service unchanged. Per
    ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §22 (backed by
    ``10_Domain_and_Data/08_REDACTION_PATTERNS.md`` §1), redaction is scoped to exactly
    two surfaces -- the ``app.*`` log pipeline and provider-SDK error-message wrapping at
    the adapter boundary -- and a user-facing toast is neither: applying ``redact()``
    here would risk silently masking legitimate diagnostic text the Run Summary dialog's
    preflight-refusal toast (``run_summary_dialog.md`` §8) needs to show verbatim.
    """
    # Arrange -- secret-shaped text is deliberately present to prove no redaction runs.
    secret = "sk-proj-AB12cd34EF56gh78IJ90kl12MN"  # noqa: S105  # redaction fixture, not a real credential
    message = f"the provider call failed: key is {secret}"
    notification = FakeNotificationService()
    gateway = _make_gateway(notification=notification)

    # Act
    gateway.notify_error(message)

    # Assert
    assert notification.error_calls == [(message, False)]


# -- STORY-106-AC-4 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Proves: STORY-106-AC-4

    Given fake settings, provider-registry, readiness, flow, and notification
    collaborators that record every call, when ``make_new_benchmark_gateway(...)`` is
    called, then the factory returns a gateway and no method was invoked on any
    collaborator.
    """
    # Arrange
    app_settings = _FakeAppSettingsStore()
    settings = _FakeSettingsService()
    provider_registry = _FakeProviderRegistry(providers=())
    readiness = _FakeReadinessService(snapshot=_make_snapshot())
    flow = _FakeBenchmarkFlowApi(run_id=1)
    notification = FakeNotificationService()

    # Act
    gateway = make_new_benchmark_gateway(
        app_settings=app_settings,
        settings=settings,
        provider_registry=provider_registry,
        readiness=readiness,
        flow=flow,
        notification=notification,
    )

    # Assert
    assert gateway is not None
    assert app_settings.get_setting_calls == []
    assert settings.set_calls == []
    assert provider_registry.list_enabled_calls == 0
    assert readiness.snapshot_calls == 0
    assert flow.start_calls == []
    assert notification.error_calls == []
    assert notification.info_calls == []
    assert notification.warning_calls == []
