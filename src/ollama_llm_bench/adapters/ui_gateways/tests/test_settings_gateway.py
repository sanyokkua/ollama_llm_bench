"""Unit tests for the concrete ``SettingsGateway`` (STORY-110).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.6, §7, §10, §12, §4 (the threading contract);
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a; ADR-0015.

Collaborators are ``mocker.Mock(spec=Protocol)`` throughout, rather than the hand-written
call-recording fakes some sibling gateway test files use -- with thirteen distinct
collaborators here (versus five-twelve on the other gateways), a purpose-built fake class
per collaborator would multiply this file's size for no extra precision:
``mocker.Mock(spec=Protocol)`` already rejects any attribute outside the real Protocol
(catching a typo'd method name) and every assertion below pins down both "the right
collaborator's right method was called with the right arguments" (``assert_called_once_with``)
and "no other collaborator/method fired" (``assert_not_called()`` / ``method_calls == []``),
which is the same guarantee the hand-written fakes exist to provide. This is a deliberate,
per-file pattern choice sanctioned by ``16_Engineering_Standards/07_TESTING_STANDARD.md``'s
mocking-discipline table.
"""

from collections.abc import Callable
from concurrent.futures import Future
import threading
from typing import Final

import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_benchmark_flow import make_run_dispatcher
from ollama_llm_bench.adapters.ui_gateways import SettingsGateway, make_settings_gateway
from ollama_llm_bench.adapters.ui_gateways.protocols import (
    PreviewGroup,
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportResult,
    Severity,
    ValidationFinding,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    CapabilitySource,
    GateLease,
    InferenceActivity,
    InferenceTestOutcome,
    InferenceTestResult,
    ModelCapability,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    SettingKey,
)
from ollama_llm_bench.backend.errors import ConfigurationError, HttpConnectionError
from ollama_llm_bench.backend.import_export import (
    ImportExportService,
    ImportFinding,
    ImportFindingSeverity,
    ImportPreviewGroup,
    ProviderImportItem,
    ProviderImportPreview as BackendProviderPreview,
    ProviderImportResult as BackendProviderResult,
    SettingsImportItem,
    SettingsImportPreview as BackendSettingsPreview,
    SettingsImportResult as BackendSettingsResult,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.model_capabilities import ModelCapabilitiesStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsAtomicWriter, SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

_KNOWN_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_KNOWN_MODEL: Final[ModelName] = "llama3"

_KEY_SELECTED_PROVIDER: Final[SettingKey] = "embedding.selected_provider_name"
_KEY_SELECTED_MODEL: Final[SettingKey] = "embedding.selected_model_name"
_KEY_COSINE_THRESHOLD: Final[SettingKey] = "eval.cosine_threshold"
_KEY_CACHE_MAX_ENTRIES: Final[SettingKey] = "eval.embedding_cache_max_entries"
_KEY_CONSECUTIVE_FAILURES: Final[SettingKey] = "eval.embedding_consecutive_failures_to_skip"


# -- shared construction helpers ---------------------------------------------------------


def _make_snapshot() -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
    )


def _make_provider_config(
    *, provider_id: ProviderId = _KNOWN_PROVIDER_ID, name: str = "Ollama (local)"
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url="http://localhost:11434/v1",
    )


def _make_gateway(  # noqa: PLR0913  # test factory forwards every constructor dependency
    mocker: MockerFixture,
    *,
    providers_store: ProvidersStore | None = None,
    app_settings_store: AppSettingsStore | None = None,
    model_capabilities_store: ModelCapabilitiesStore | None = None,
    settings: SettingsService | None = None,
    atomic_writer: SettingsAtomicWriter | None = None,
    provider_registry: ProviderRegistry | None = None,
    readiness: ReadinessService | None = None,
    import_export: ImportExportService | None = None,
    gate: InferenceActivityStore | None = None,
    task_runner: object = None,
    dispatcher: object = None,
    clock: Clock | None = None,
) -> SettingsGateway:
    return make_settings_gateway(
        providers_store=providers_store
        if providers_store is not None
        else mocker.Mock(spec=ProvidersStore),
        app_settings_store=app_settings_store
        if app_settings_store is not None
        else mocker.Mock(spec=AppSettingsStore),
        model_capabilities_store=model_capabilities_store
        if model_capabilities_store is not None
        else mocker.Mock(spec=ModelCapabilitiesStore),
        settings=settings if settings is not None else mocker.Mock(spec=SettingsService),
        atomic_writer=atomic_writer
        if atomic_writer is not None
        else mocker.Mock(spec=SettingsAtomicWriter),
        provider_registry=provider_registry
        if provider_registry is not None
        else mocker.Mock(spec=ProviderRegistry),
        readiness=readiness if readiness is not None else mocker.Mock(spec=ReadinessService),
        import_export=import_export
        if import_export is not None
        else mocker.Mock(spec=ImportExportService),
        gate=gate if gate is not None else mocker.Mock(spec=InferenceActivityStore),
        task_runner=task_runner  # type: ignore[arg-type]
        if task_runner is not None
        else _ThreadTaskRunner(),
        dispatcher=dispatcher  # type: ignore[arg-type]
        if dispatcher is not None
        else mocker.Mock(),
        clock=clock if clock is not None else _FakeClock(),
    )


class _FakeClock:
    """A deterministic, injectable ``Clock``."""

    def __init__(self) -> None:
        self._monotonic_ms = 0

    def now_utc(self) -> str:
        return "2026-07-31T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        self._monotonic_ms += 1
        return self._monotonic_ms


class _ThreadTaskRunner:
    """Runs each submitted unit on a brand-new ``threading.Thread`` and returns an
    unresolved ``Future`` immediately -- a minimal stand-in for the real
    ``QThreadPool``-backed ``TaskRunner``. Copied from ``test_result_gateway.py``'s
    fake of the same name and shape."""

    def __init__(self) -> None:
        self.submit_calls: list[Callable[[], object]] = []

    def submit(self, fn: Callable[[], object], *, token: object) -> "Future[object]":
        del token
        self.submit_calls.append(fn)
        future: Future[object] = Future()

        def _run() -> None:
            try:
                future.set_result(fn())
            except BaseException as exc:  # noqa: BLE001  # relayed via the future, not swallowed
                future.set_exception(exc)

        threading.Thread(target=_run, daemon=True).start()
        return future


# -- STORY-110-AC-1 -----------------------------------------------------------------------


def _case_list_providers(mocker: MockerFixture) -> None:
    configs = (_make_provider_config(),)
    providers_store = mocker.Mock(spec=ProvidersStore)
    providers_store.list_providers.return_value = configs
    gateway = _make_gateway(mocker, providers_store=providers_store)

    result = gateway.list_providers()

    providers_store.list_providers.assert_called_once_with()
    assert result == configs


def _case_get_provider_by_name(mocker: MockerFixture) -> None:
    config = _make_provider_config()
    providers_store = mocker.Mock(spec=ProvidersStore)
    providers_store.get_by_name.return_value = config
    gateway = _make_gateway(mocker, providers_store=providers_store)

    result = gateway.get_provider_by_name("Ollama (local)")

    providers_store.get_by_name.assert_called_once_with("Ollama (local)")
    assert result is config


def _case_replace_providers(mocker: MockerFixture) -> None:
    configs = (_make_provider_config(),)
    providers_store = mocker.Mock(spec=ProvidersStore)
    gateway = _make_gateway(mocker, providers_store=providers_store)

    gateway.replace_providers(configs)

    providers_store.replace_providers.assert_called_once_with(configs)


def _case_get_setting(mocker: MockerFixture) -> None:
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.get_setting.return_value = "dark"
    gateway = _make_gateway(mocker, app_settings_store=app_settings_store)

    result = gateway.get_setting("ui.theme")

    app_settings_store.get_setting.assert_called_once_with("ui.theme")
    assert result == "dark"


def _case_get_setting_returns_none_when_unset(mocker: MockerFixture) -> None:
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.get_setting.return_value = None
    gateway = _make_gateway(mocker, app_settings_store=app_settings_store)

    result = gateway.get_setting("ui.theme")

    assert result is None


def _case_list_settings(mocker: MockerFixture) -> None:
    values = {"ui.theme": "dark"}
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.list_settings.return_value = values
    gateway = _make_gateway(mocker, app_settings_store=app_settings_store)

    result = gateway.list_settings()

    app_settings_store.list_settings.assert_called_once_with()
    assert result == values


def _case_upsert_settings(mocker: MockerFixture) -> None:
    values = {"ui.theme": "light"}
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    gateway = _make_gateway(mocker, app_settings_store=app_settings_store)

    gateway.upsert_settings(values)

    app_settings_store.upsert_settings.assert_called_once_with(values)


def _case_get_resolved_str(mocker: MockerFixture) -> None:
    settings = mocker.Mock(spec=SettingsService)
    settings.get_str.return_value = "dark"
    gateway = _make_gateway(mocker, settings=settings)

    result = gateway.get_resolved_str("ui.theme")

    settings.get_str.assert_called_once_with("ui.theme")
    assert result == "dark"


def _case_list_model_capabilities(mocker: MockerFixture) -> None:
    records = (
        ModelCapabilityRecord(
            provider_id=_KNOWN_PROVIDER_ID,
            model_name=_KNOWN_MODEL,
            capability=ModelCapability.STREAMING,
            supported=1,
            last_observed_at="2026-07-31T00:00:00+00:00",
            observed_via=CapabilitySource.PROBE,
        ),
    )
    model_capabilities_store = mocker.Mock(spec=ModelCapabilitiesStore)
    model_capabilities_store.list_model_capabilities.return_value = records
    gateway = _make_gateway(mocker, model_capabilities_store=model_capabilities_store)

    result = gateway.list_model_capabilities(_KNOWN_PROVIDER_ID, _KNOWN_MODEL)

    model_capabilities_store.list_model_capabilities.assert_called_once_with(
        _KNOWN_PROVIDER_ID, _KNOWN_MODEL
    )
    assert result == records


def _case_upsert_model_capability(mocker: MockerFixture) -> None:
    record = ModelCapabilityRecord(
        provider_id=_KNOWN_PROVIDER_ID,
        model_name=_KNOWN_MODEL,
        capability=ModelCapability.STREAMING,
        supported=1,
        last_observed_at="2026-07-31T00:00:00+00:00",
        observed_via=CapabilitySource.MANUAL,
    )
    model_capabilities_store = mocker.Mock(spec=ModelCapabilitiesStore)
    gateway = _make_gateway(mocker, model_capabilities_store=model_capabilities_store)

    gateway.upsert_model_capability(record)

    model_capabilities_store.upsert_model_capability.assert_called_once_with(record)


def _case_readiness_snapshot(mocker: MockerFixture) -> None:
    snapshot = _make_snapshot()
    readiness = mocker.Mock(spec=ReadinessService)
    readiness.snapshot.return_value = snapshot
    gateway = _make_gateway(mocker, readiness=readiness)

    result = gateway.readiness_snapshot()

    readiness.snapshot.assert_called_once_with()
    readiness.probe_all.assert_not_called()
    assert result is snapshot


_AC1_CASES: tuple[tuple[str, Callable[[MockerFixture], None]], ...] = (
    ("list_providers", _case_list_providers),
    ("get_provider_by_name", _case_get_provider_by_name),
    ("replace_providers", _case_replace_providers),
    ("get_setting", _case_get_setting),
    ("get_setting_unset", _case_get_setting_returns_none_when_unset),
    ("list_settings", _case_list_settings),
    ("upsert_settings", _case_upsert_settings),
    ("get_resolved_str", _case_get_resolved_str),
    ("list_model_capabilities", _case_list_model_capabilities),
    ("upsert_model_capability", _case_upsert_model_capability),
    ("readiness_snapshot", _case_readiness_snapshot),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_fast_synchronous_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[MockerFixture], None]], mocker: MockerFixture
) -> None:
    """Proves: STORY-110-AC-1

    For each of the ten fast-synchronous ``SettingsGateway`` methods, calling it
    performs exactly the stated interaction against its injected collaborator (the
    right collaborator, the right method, the right arguments) and returns that
    collaborator's value unchanged. Table-driven -- one row per method -- because
    the variation across all ten rows is a finite enumerable set and is the point
    of the criterion (Pattern B, ``acceptance-criteria-authoring`` skill).
    """
    _name, run_case = case
    run_case(mocker)


# -- STORY-110-AC-2 -----------------------------------------------------------------------


def _make_backend_settings_preview() -> BackendSettingsPreview:
    return BackendSettingsPreview(
        items=(
            SettingsImportItem(
                setting_key="ui.theme",
                current_value="dark",
                imported_value="light",
                group=ImportPreviewGroup.CHANGED,
            ),
        ),
        findings=(
            ImportFinding(
                severity=ImportFindingSeverity.SOFT_WARNING,
                item_key="ui.theme",
                reason="value changed",
            ),
        ),
        resolved_values={"ui.theme": "light"},
    )


def _make_backend_provider_preview() -> BackendProviderPreview:
    return BackendProviderPreview(
        items=(
            ProviderImportItem(
                name="Ollama (local)", group=ImportPreviewGroup.UNCHANGED, draft=None
            ),
        ),
        embedding_provider_name="Ollama (local)",
        embedding_model_name="nomic-embed-text",
        findings=(),
    )


def _case_build_settings_import_preview(mocker: MockerFixture) -> None:
    backend_preview = _make_backend_settings_preview()
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.build_settings_import_preview.return_value = backend_preview
    gateway = _make_gateway(mocker, import_export=import_export)
    file_path = "/settings-import/settings.yaml"

    result = gateway.build_settings_import_preview(file_path)

    import_export.build_settings_import_preview.assert_called_once_with(file_path)
    assert result.rows[0].setting_key == "ui.theme"
    assert result.rows[0].group == PreviewGroup.CHANGED
    assert result.findings == (
        ValidationFinding(
            severity=Severity.SOFT_WARNING, target="ui.theme", message="value changed"
        ),
    )
    assert result.resolved_values == {"ui.theme": "light"}
    assert result.backend_preview is backend_preview


def _case_apply_settings_import(mocker: MockerFixture) -> None:
    backend_preview = _make_backend_settings_preview()
    backend_result = BackendSettingsResult(applied_count=1, skipped_count=0)
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.apply_settings_import.return_value = backend_result
    gateway = _make_gateway(mocker, import_export=import_export)
    preview = SettingsImportPreview(
        rows=(), findings=(), resolved_values={}, backend_preview=backend_preview
    )

    result = gateway.apply_settings_import(preview)

    import_export.apply_settings_import.assert_called_once_with(backend_preview)
    assert result == SettingsImportResult(applied_count=1, skipped_count=0)


def _case_build_provider_import_preview(mocker: MockerFixture) -> None:
    backend_preview = _make_backend_provider_preview()
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.build_provider_import_preview.return_value = backend_preview
    gateway = _make_gateway(mocker, import_export=import_export)
    file_path = "/providers-import/providers.yaml"

    result = gateway.build_provider_import_preview(file_path)

    import_export.build_provider_import_preview.assert_called_once_with(file_path)
    assert result.rows[0].name == "Ollama (local)"
    assert result.rows[0].group == PreviewGroup.UNCHANGED
    assert result.embedding_provider_name == "Ollama (local)"
    assert result.embedding_model_name == "nomic-embed-text"
    assert result.backend_preview is backend_preview


def _case_apply_provider_import(mocker: MockerFixture) -> None:
    backend_preview = _make_backend_provider_preview()
    backend_result = BackendProviderResult(applied_count=1, skipped_count=0)
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.apply_provider_import.return_value = backend_result
    gateway = _make_gateway(mocker, import_export=import_export)
    preview = ProviderImportPreview(
        rows=(),
        embedding_provider_name=None,
        embedding_model_name=None,
        findings=(),
        backend_preview=backend_preview,
    )

    result = gateway.apply_provider_import(preview)

    import_export.apply_provider_import.assert_called_once_with(backend_preview)
    assert result == ProviderImportResult(applied_count=1, skipped_count=0)


def _case_export_settings(mocker: MockerFixture) -> None:
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.export_settings.return_value = b"settings-payload"
    gateway = _make_gateway(mocker, import_export=import_export)

    result = gateway.export_settings()

    import_export.export_settings.assert_called_once_with()
    assert result == b"settings-payload"


def _case_export_providers(mocker: MockerFixture) -> None:
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.export_providers.return_value = b"providers-payload"
    gateway = _make_gateway(mocker, import_export=import_export)

    result = gateway.export_providers()

    import_export.export_providers.assert_called_once_with()
    assert result == b"providers-payload"


_AC2_CASES: tuple[tuple[str, Callable[[MockerFixture], None]], ...] = (
    ("build_settings_import_preview", _case_build_settings_import_preview),
    ("apply_settings_import", _case_apply_settings_import),
    ("build_provider_import_preview", _case_build_provider_import_preview),
    ("apply_provider_import", _case_apply_provider_import),
    ("export_settings", _case_export_settings),
    ("export_providers", _case_export_providers),
)
_AC2_CASE_IDS = [case[0] for case in _AC2_CASES]


@pytest.mark.parametrize("case", _AC2_CASES, ids=_AC2_CASE_IDS)
def test_each_import_export_method_delegates_to_the_service(
    case: tuple[str, Callable[[MockerFixture], None]], mocker: MockerFixture
) -> None:
    """Proves: STORY-110-AC-2

    For each of the six import/export ``SettingsGateway`` methods, calling it
    delegates to ``ImportExportService``'s matching method (translating the
    backend DTO to/from this module's adapter-local mirror) and returns its
    value unchanged. Table-driven -- one row per method.
    """
    _name, run_case = case
    run_case(mocker)


# -- STORY-113-AC-3 / STORY-113-AC-4 ------------------------------------------------------


def test_apply_settings_import_round_trips_the_original_backend_preview(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-113-AC-3

    Given a settings-import preview obtained from the concrete Settings gateway's
    ``build_settings_import_preview``, when that preview object is passed back
    unchanged to ``apply_settings_import``, then the underlying import/export service
    receives the identical backend preview object that produced it -- checked with
    ``is``, not ``==``, because the point of the criterion is that no intermediate
    reconstruction happens, and a freshly-built-but-equal backend preview would pass an
    equality check while still failing this one.
    """
    backend_preview = _make_backend_settings_preview()
    backend_result = BackendSettingsResult(applied_count=1, skipped_count=0)
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.build_settings_import_preview.return_value = backend_preview
    import_export.apply_settings_import.return_value = backend_result
    gateway = _make_gateway(mocker, import_export=import_export)

    preview = gateway.build_settings_import_preview("/settings-import/settings.yaml")
    gateway.apply_settings_import(preview)

    call_args = import_export.apply_settings_import.call_args
    assert call_args is not None
    assert call_args.args[0] is backend_preview


def test_apply_provider_import_round_trips_the_original_backend_preview(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-113-AC-4

    Given a provider-import preview obtained from the concrete Settings gateway's
    ``build_provider_import_preview``, when that preview object is passed back
    unchanged to ``apply_provider_import``, then the underlying import/export service
    receives the identical backend preview object that produced it -- checked with
    ``is``, not ``==``, for the same reason as STORY-113-AC-3.
    """
    backend_preview = _make_backend_provider_preview()
    backend_result = BackendProviderResult(applied_count=1, skipped_count=0)
    import_export = mocker.Mock(spec=ImportExportService)
    import_export.build_provider_import_preview.return_value = backend_preview
    import_export.apply_provider_import.return_value = backend_result
    gateway = _make_gateway(mocker, import_export=import_export)

    preview = gateway.build_provider_import_preview("/providers-import/providers.yaml")
    gateway.apply_provider_import(preview)

    call_args = import_export.apply_provider_import.call_args
    assert call_args is not None
    assert call_args.args[0] is backend_preview


# -- STORY-110-AC-6 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator(mocker: MockerFixture) -> None:
    """Proves: STORY-110-AC-6

    Given fake providers-store, app-settings-store, capabilities-store, settings,
    provider-registry, readiness, and import/export collaborators that record every
    call, when ``make_settings_gateway(...)`` is called, then the factory returns a
    gateway and no method was invoked on any collaborator -- in particular, no probe
    ran.
    """
    providers_store = mocker.Mock(spec=ProvidersStore)
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    model_capabilities_store = mocker.Mock(spec=ModelCapabilitiesStore)
    settings = mocker.Mock(spec=SettingsService)
    atomic_writer = mocker.Mock(spec=SettingsAtomicWriter)
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    readiness = mocker.Mock(spec=ReadinessService)
    import_export = mocker.Mock(spec=ImportExportService)
    gate = mocker.Mock(spec=InferenceActivityStore)
    task_runner = _ThreadTaskRunner()
    dispatcher = mocker.Mock()
    clock = _FakeClock()

    gateway = make_settings_gateway(
        providers_store=providers_store,
        app_settings_store=app_settings_store,
        model_capabilities_store=model_capabilities_store,
        settings=settings,
        atomic_writer=atomic_writer,
        provider_registry=provider_registry,
        readiness=readiness,
        import_export=import_export,
        gate=gate,
        task_runner=task_runner,
        dispatcher=dispatcher,
        clock=clock,
    )

    assert gateway is not None
    assert providers_store.method_calls == []
    assert app_settings_store.method_calls == []
    assert model_capabilities_store.method_calls == []
    assert settings.method_calls == []
    assert atomic_writer.method_calls == []
    assert provider_registry.method_calls == []
    assert readiness.method_calls == []
    assert import_export.method_calls == []
    assert gate.method_calls == []
    assert task_runner.submit_calls == []
    assert dispatcher.method_calls == []


# -- STORY-110-AC-7 -----------------------------------------------------------------------

_PROBE_RELEASE_TIMEOUT_S: Final[float] = 3.0
_WAIT_TIMEOUT_S: Final[float] = 5.0

# The name a real `RunDispatcher` gives its thread (DD-38,
# `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a). Asserting on it is what
# distinguishes "ran on the dispatcher" from "ran on any background thread".
_DISPATCHER_THREAD_NAME: Final[str] = "pipeline-dispatcher"


def _make_gate_lease() -> GateLease:
    return GateLease(activity=InferenceActivity.PROVIDER_TEST, lease_id=1, acquired_at=0)


class _BlockingLLMClient:
    """Records the calling thread's identity, then blocks until released.

    ``started`` fires the moment the blocking method begins running (on whatever
    thread that turns out to be); ``finished`` fires only after the internal wait
    returns -- either because the test released it, or (in a buggy inline
    implementation) because the bounded wait's own timeout elapsed. Mirrors
    ``test_main_window_gateway.py``'s ``_BlockingReadinessService``.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release_event = threading.Event()
        self.recorded_thread_ids: list[int] = []

    def _block(self) -> None:
        self.recorded_thread_ids.append(threading.get_ident())
        self.started.set()
        self.release_event.wait(timeout=_PROBE_RELEASE_TIMEOUT_S)
        self.finished.set()

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        self._block()
        return InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=_KNOWN_PROVIDER_ID,
            model_name=model_name,
            tested_at=0,
        )

    def list_models(self) -> tuple[ModelName, ...]:
        self._block()
        return (_KNOWN_MODEL,)

    def embed(self, text: str) -> tuple[float, ...]:
        del text
        self._block()
        return (0.1, 0.2)

    def probe_health(self) -> ProviderHealth:
        raise AssertionError("this fake only exercises the method under test")


class _BlockingReadinessService:
    """Records the probing thread's name, then blocks until released -- the
    ``probe_all`` counterpart to ``_BlockingLLMClient``, copied from
    ``test_main_window_gateway.py``'s fake of the same name."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release_event = threading.Event()
        self.recorded_thread_names: list[str] = []

    def snapshot(self) -> AppReadinessSnapshot:
        raise AssertionError("this test only exercises probe_all")

    def probe_all(self) -> AppReadinessSnapshot:
        self.recorded_thread_names.append(threading.current_thread().name)
        self.started.set()
        self.release_event.wait(timeout=_PROBE_RELEASE_TIMEOUT_S)
        self.finished.set()
        return _make_snapshot()

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise AssertionError("this test only exercises probe_all")

    def record_embedding_capability_result(self, *, reachable: bool) -> None:
        raise AssertionError("this test only exercises probe_all")


def _case_test_provider_runs_on_a_task_runner_worker_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    del qtbot  # only requested so a live QApplication exists for the relay's QObject
    client = _BlockingLLMClient()
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    task_runner = _ThreadTaskRunner()
    calling_thread_id = threading.get_ident()
    gateway = _make_gateway(
        mocker, provider_registry=provider_registry, gate=gate, task_runner=task_runner
    )

    try:
        gateway.test_provider(_KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=lambda _r: None)

        assert not client.finished.is_set()
        assert client.started.wait(timeout=_WAIT_TIMEOUT_S), (
            "test_inference never started on a worker thread"
        )
        assert client.recorded_thread_ids[0] != calling_thread_id
    finally:
        client.release_event.set()


def _case_discover_models_runs_on_a_task_runner_worker_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    del qtbot
    client = _BlockingLLMClient()
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    task_runner = _ThreadTaskRunner()
    calling_thread_id = threading.get_ident()
    gateway = _make_gateway(mocker, provider_registry=provider_registry, task_runner=task_runner)

    try:
        gateway.discover_models(_KNOWN_PROVIDER_ID, on_complete=lambda _r: None)

        assert not client.finished.is_set()
        assert client.started.wait(timeout=_WAIT_TIMEOUT_S), (
            "list_models never started on a worker thread"
        )
        assert client.recorded_thread_ids[0] != calling_thread_id
    finally:
        client.release_event.set()


def _case_probe_all_runs_on_the_dispatcher_thread(mocker: MockerFixture, qtbot: QtBot) -> None:
    del qtbot
    dispatcher = make_run_dispatcher()
    readiness = _BlockingReadinessService()
    gateway = _make_gateway(mocker, readiness=readiness, dispatcher=dispatcher)

    try:
        gateway.probe_all()

        assert not readiness.finished.is_set()
        assert readiness.started.wait(timeout=_WAIT_TIMEOUT_S), (
            "the readiness probe never started on the dispatcher thread"
        )
        readiness.release_event.set()
        assert readiness.finished.wait(timeout=_WAIT_TIMEOUT_S), (
            "the readiness probe never finished after being released"
        )
        assert readiness.recorded_thread_names == [_DISPATCHER_THREAD_NAME]
    finally:
        readiness.release_event.set()
        dispatcher.shutdown(timeout_ms=5000)


def _case_probe_embedding_runs_on_a_task_runner_worker_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    del qtbot
    client = _BlockingLLMClient()
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    providers_store = mocker.Mock(spec=ProvidersStore)
    providers_store.get_by_name.return_value = _make_provider_config()
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.get_setting.side_effect = {
        _KEY_SELECTED_PROVIDER: "Ollama (local)",
        _KEY_SELECTED_MODEL: "nomic-embed-text",
    }.__getitem__
    settings = mocker.Mock(spec=SettingsService)
    settings.get_str.side_effect = {
        _KEY_COSINE_THRESHOLD: "0.75",
        _KEY_CACHE_MAX_ENTRIES: "1000",
        _KEY_CONSECUTIVE_FAILURES: "3",
    }.__getitem__
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    readiness = mocker.Mock(spec=ReadinessService)
    readiness.snapshot.return_value = _make_snapshot()
    task_runner = _ThreadTaskRunner()
    calling_thread_id = threading.get_ident()
    gateway = _make_gateway(
        mocker,
        provider_registry=provider_registry,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
        settings=settings,
        gate=gate,
        readiness=readiness,
        task_runner=task_runner,
    )

    try:
        gateway.probe_embedding(on_complete=lambda _r: None)

        assert not client.finished.is_set()
        assert client.started.wait(timeout=_WAIT_TIMEOUT_S), (
            "the embedding probe call never started on a worker thread"
        )
        assert client.recorded_thread_ids[0] != calling_thread_id
    finally:
        client.release_event.set()


_AC7_CASES: tuple[tuple[str, Callable[[MockerFixture, QtBot], None]], ...] = (
    ("test_provider", _case_test_provider_runs_on_a_task_runner_worker_thread),
    ("discover_models", _case_discover_models_runs_on_a_task_runner_worker_thread),
    ("probe_all", _case_probe_all_runs_on_the_dispatcher_thread),
    ("probe_embedding", _case_probe_embedding_runs_on_a_task_runner_worker_thread),
)
_AC7_CASE_IDS = [case[0] for case in _AC7_CASES]


@pytest.mark.parametrize("case", _AC7_CASES, ids=_AC7_CASE_IDS)
def test_each_network_bound_method_returns_before_its_call_runs_off_thread(
    case: tuple[str, Callable[[MockerFixture, QtBot], None]],
    mocker: MockerFixture,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-110-AC-7

    Each of the four network-bound ``SettingsGateway`` methods
    (``test_provider``, ``discover_models``, ``probe_all``, ``probe_embedding``)
    returns ``None`` to its caller before its backend call has completed, and runs
    that call off the calling thread -- ``probe_all`` specifically on the
    pipeline-dispatcher thread (never a ``TaskRunner`` worker, per
    ``04_CONCURRENCY_STANDARD.md`` §4a), the other three on a ``TaskRunner``
    worker. Table-driven -- one row per method -- following STORY-105-AC-2's
    ``test_reprobe_runs_the_probe_on_the_dispatcher_thread`` idiom (a fake
    collaborator recording ``threading.get_ident()``/thread name, blocking on a
    ``threading.Event`` the test releases after asserting the gateway call
    already returned).
    """
    _name, run_case = case
    run_case(mocker, qtbot)


# -- STORY-110-AC-8 -----------------------------------------------------------------------


def _case_test_provider_delivers_once_on_the_gui_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    expected = InferenceTestResult(
        outcome=InferenceTestOutcome.SUCCESS,
        provider_id=_KNOWN_PROVIDER_ID,
        model_name=_KNOWN_MODEL,
        tested_at=0,
    )

    class _Client:
        def test_inference(self, model_name: ModelName) -> InferenceTestResult:
            del model_name
            return expected

        def probe_health(self) -> ProviderHealth:
            raise AssertionError("this test only exercises test_inference")

    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = _Client()
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(
        mocker, provider_registry=provider_registry, gate=gate, task_runner=task_runner
    )
    gui_thread_id = threading.get_ident()
    received: list[InferenceTestResult] = []
    callback_thread_ids: list[int] = []

    def _on_complete(result: InferenceTestResult) -> None:
        callback_thread_ids.append(threading.get_ident())
        received.append(result)

    gateway.test_provider(_KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=_on_complete)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [expected]
    assert callback_thread_ids == [gui_thread_id]
    gate.release.assert_called_once()


def _case_discover_models_delivers_once_on_the_gui_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    expected = (_KNOWN_MODEL, "llama3.1")

    class _Client:
        def list_models(self) -> tuple[ModelName, ...]:
            return expected

    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = _Client()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(mocker, provider_registry=provider_registry, task_runner=task_runner)
    gui_thread_id = threading.get_ident()
    received: list[tuple[ModelName, ...]] = []
    callback_thread_ids: list[int] = []

    def _on_complete(result: tuple[ModelName, ...]) -> None:
        callback_thread_ids.append(threading.get_ident())
        received.append(result)

    gateway.discover_models(_KNOWN_PROVIDER_ID, on_complete=_on_complete)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [expected]
    assert callback_thread_ids == [gui_thread_id]


_AC8_CASES: tuple[tuple[str, Callable[[MockerFixture, QtBot], None]], ...] = (
    ("test_provider", _case_test_provider_delivers_once_on_the_gui_thread),
    ("discover_models", _case_discover_models_delivers_once_on_the_gui_thread),
)
_AC8_CASE_IDS = [case[0] for case in _AC8_CASES]


@pytest.mark.parametrize("case", _AC8_CASES, ids=_AC8_CASE_IDS)
def test_each_callback_bearing_method_delivers_its_result_once_on_the_calling_thread(
    case: tuple[str, Callable[[MockerFixture, QtBot], None]],
    mocker: MockerFixture,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-110-AC-8

    Each of ``test_provider`` and ``discover_models`` invokes its ``on_complete``
    callback exactly once, on the calling (graphical) thread, with the value its
    backend call produced. Table-driven -- one row per method -- following
    STORY-108-AC-2's ``test_regenerate_dispatches_to_a_worker_and_calls_back_on_
    the_gui_thread`` idiom: a real ``threading.Thread``-backed ``TaskRunner`` fake
    so the real ``_CompletionRelay``/queued-signal marshalling path is exercised,
    with ``qtbot`` driving a real Qt event loop so the queued connection actually
    delivers.
    """
    _name, run_case = case
    run_case(mocker, qtbot)


# -- STORY-110-AC-10 ----------------------------------------------------------------------


def _case_test_provider_translates_configuration_error(mocker: MockerFixture, qtbot: QtBot) -> None:
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.side_effect = ConfigurationError(message="provider unusable")
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(
        mocker, provider_registry=provider_registry, gate=gate, task_runner=task_runner
    )
    received: list[InferenceTestResult] = []

    gateway.test_provider(_KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=received.append)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received[0].outcome == InferenceTestOutcome.PROVIDER_ERROR
    assert received[0].provider_id == _KNOWN_PROVIDER_ID
    gate.release.assert_called_once()


def _case_discover_models_translates_provider_error_to_empty_tuple(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    client = mocker.Mock(spec=["list_models"])
    client.list_models.side_effect = HttpConnectionError(message="connection refused")
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(mocker, provider_registry=provider_registry, task_runner=task_runner)
    received: list[tuple[ModelName, ...]] = []

    gateway.discover_models(_KNOWN_PROVIDER_ID, on_complete=received.append)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [()]


def _case_probe_embedding_translates_worker_exception_to_unreachable(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.side_effect = ConfigurationError(message="provider unusable")
    providers_store = mocker.Mock(spec=ProvidersStore)
    providers_store.get_by_name.return_value = _make_provider_config()
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.get_setting.side_effect = {
        _KEY_SELECTED_PROVIDER: "Ollama (local)",
        _KEY_SELECTED_MODEL: "nomic-embed-text",
    }.__getitem__
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    readiness = mocker.Mock(spec=ReadinessService)
    recorded = threading.Event()
    readiness.record_embedding_capability_result.side_effect = lambda **_kwargs: recorded.set()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(
        mocker,
        provider_registry=provider_registry,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
        gate=gate,
        readiness=readiness,
        task_runner=task_runner,
    )
    received: list[bool] = []

    gateway.probe_embedding(on_complete=received.append)

    assert recorded.wait(timeout=_WAIT_TIMEOUT_S), (
        "record_embedding_capability_result was never called"
    )
    readiness.record_embedding_capability_result.assert_called_once_with(reachable=False)
    gate.release.assert_called_once()
    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [False]


def _case_probe_embedding_records_unreachable_when_gate_busy(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = None
    readiness = mocker.Mock(spec=ReadinessService)
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(mocker, gate=gate, readiness=readiness, task_runner=task_runner)
    received: list[bool] = []

    gateway.probe_embedding(on_complete=received.append)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [False]
    # Gate contention is not a capability fact (STORY-110 spec-conformance fix,
    # ADR-0016): it must never be reported to ReadinessService, so the cached
    # embedding_reachable/overall readiness state -- and the app-wide GRADED
    # run-start gate that reads it -- is left exactly as it was.
    readiness.record_embedding_capability_result.assert_not_called()
    gate.release.assert_not_called()


_AC10_CASES: tuple[tuple[str, Callable[[MockerFixture, QtBot], None]], ...] = (
    ("test_provider", _case_test_provider_translates_configuration_error),
    ("discover_models", _case_discover_models_translates_provider_error_to_empty_tuple),
    (
        "probe_embedding_worker_exception",
        _case_probe_embedding_translates_worker_exception_to_unreachable,
    ),
    ("probe_embedding_gate_busy", _case_probe_embedding_records_unreachable_when_gate_busy),
)
_AC10_CASE_IDS = [case[0] for case in _AC10_CASES]


@pytest.mark.parametrize("case", _AC10_CASES, ids=_AC10_CASE_IDS)
def test_each_network_bound_method_translates_a_worker_failure_into_a_delivered_result(
    case: tuple[str, Callable[[MockerFixture, QtBot], None]],
    mocker: MockerFixture,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-110-AC-10

    A collaborator exception raised inside ``test_provider``'s/``discover_models``'s/
    ``probe_embedding``'s worker body is caught and translated into a failure-shaped
    result delivered exactly once, instead of propagating to the submitting
    ``Future`` -- where ``concurrent.futures`` logs-and-swallows a done-callback's
    own ``future.result()`` re-raise, so ``on_complete`` would otherwise never fire
    at all. ``test_provider`` yields ``InferenceTestResult(outcome=PROVIDER_ERROR,
    ...)``; ``discover_models`` yields an empty model-name tuple; ``probe_embedding``
    reports ``reachable=False`` through
    ``ReadinessService.record_embedding_capability_result`` on a genuine collaborator
    failure -- but NOT when the single-inference gate itself is busy
    (spec-conformance fix, ADR-0016): gate contention is not a capability fact, so
    that branch calls ``ReadinessService`` with nothing at all, leaving the cached
    readiness state untouched, while still delivering ``False`` through its own
    ``on_complete`` callback so the embedding diagnostic never sticks on
    "Testing...".
    """
    _name, run_case = case
    run_case(mocker, qtbot)


# -- STORY-110-AC-11 ----------------------------------------------------------------------


def _case_probe_embedding_delivers_success_once_on_the_gui_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    client = mocker.Mock(spec=["embed"])
    client.embed.return_value = (0.1, 0.2)
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    providers_store = mocker.Mock(spec=ProvidersStore)
    providers_store.get_by_name.return_value = _make_provider_config()
    app_settings_store = mocker.Mock(spec=AppSettingsStore)
    app_settings_store.get_setting.side_effect = {
        _KEY_SELECTED_PROVIDER: "Ollama (local)",
        _KEY_SELECTED_MODEL: "nomic-embed-text",
    }.__getitem__
    settings = mocker.Mock(spec=SettingsService)
    settings.get_str.side_effect = {
        _KEY_COSINE_THRESHOLD: "0.75",
        _KEY_CACHE_MAX_ENTRIES: "1000",
        _KEY_CONSECUTIVE_FAILURES: "3",
    }.__getitem__
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = _make_gate_lease()
    readiness = mocker.Mock(spec=ReadinessService)
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(
        mocker,
        provider_registry=provider_registry,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
        settings=settings,
        gate=gate,
        readiness=readiness,
        task_runner=task_runner,
    )
    gui_thread_id = threading.get_ident()
    received: list[bool] = []
    callback_thread_ids: list[int] = []

    def _on_complete(reachable: bool) -> None:  # noqa: FBT001  # mirrors the real on_complete(bool) payload
        callback_thread_ids.append(threading.get_ident())
        received.append(reachable)

    gateway.probe_embedding(on_complete=_on_complete)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [True]
    assert callback_thread_ids == [gui_thread_id]
    readiness.record_embedding_capability_result.assert_called_once_with(reachable=True)


def _case_probe_embedding_delivers_gate_busy_once_on_the_gui_thread(
    mocker: MockerFixture, qtbot: QtBot
) -> None:
    gate = mocker.Mock(spec=InferenceActivityStore)
    gate.try_acquire.return_value = None
    readiness = mocker.Mock(spec=ReadinessService)
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(mocker, gate=gate, readiness=readiness, task_runner=task_runner)
    gui_thread_id = threading.get_ident()
    received: list[bool] = []
    callback_thread_ids: list[int] = []

    def _on_complete(reachable: bool) -> None:  # noqa: FBT001  # mirrors the real on_complete(bool) payload
        callback_thread_ids.append(threading.get_ident())
        received.append(reachable)

    gateway.probe_embedding(on_complete=_on_complete)

    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert received == [False]
    assert callback_thread_ids == [gui_thread_id]
    readiness.record_embedding_capability_result.assert_not_called()


_AC11_CASES: tuple[tuple[str, Callable[[MockerFixture, QtBot], None]], ...] = (
    ("success", _case_probe_embedding_delivers_success_once_on_the_gui_thread),
    ("gate_busy", _case_probe_embedding_delivers_gate_busy_once_on_the_gui_thread),
)
_AC11_CASE_IDS = [case[0] for case in _AC11_CASES]


@pytest.mark.parametrize("case", _AC11_CASES, ids=_AC11_CASE_IDS)
def test_probe_embedding_delivers_on_complete_exactly_once_on_the_calling_thread(
    case: tuple[str, Callable[[MockerFixture, QtBot], None]],
    mocker: MockerFixture,
    qtbot: QtBot,
) -> None:
    """Proves: STORY-110-AC-11

    ``probe_embedding``'s ``on_complete`` callback (ADR-0016) fires exactly once,
    on the calling (graphical) thread, with the check's definite boolean outcome
    -- on a successful check and on a gate-busy refusal alike -- independently of
    whether ``ReadinessService.record_embedding_capability_result`` was also
    called for the same worker run (it is, on success; it is deliberately not, on
    gate-busy -- STORY-110-AC-10).
    """
    _name, run_case = case
    run_case(mocker, qtbot)
