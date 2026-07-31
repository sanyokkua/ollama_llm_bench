"""The concrete ``SettingsGateway`` (D-R-06) -- see ``adapters/ui_gateways/protocols.py``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.6, §4 (the threading contract), §12 (Readiness Service);
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a;
ADR-0015.
"""

from collections.abc import Callable
import functools
from typing import TYPE_CHECKING, Final, cast

import msgspec
from PySide6.QtCore import QObject, Qt, Signal, Slot

if TYPE_CHECKING:
    from concurrent.futures import Future

from ollama_llm_bench.adapters.ui_gateways.protocols import (
    PreviewGroup,
    ProviderImportPreview,
    ProviderImportPreviewRow,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportPreviewRow,
    SettingsImportResult,
    Severity,
    ValidationFinding,
)
from ollama_llm_bench.backend.concurrency import RunDispatcher, TaskRunner, make_cancellation_token
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkRunSettingEntry,
    InferenceActivity,
    InferenceActivityContext,
    InferenceTestOutcome,
    InferenceTestResult,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderId,
    SettingKey,
)
from ollama_llm_bench.backend.embedding import make_embedding_service
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    AppReadinessChangedEvent,
    EventBus,
    ProviderHealthSummary,
)
from ollama_llm_bench.backend.import_export import (
    ImportExportService,
    ImportFinding,
    ProviderImportPreview as BackendProviderImportPreview,
    SettingsImportPreview as BackendSettingsImportPreview,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.model_capabilities import ModelCapabilitiesStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.provider_registry import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsAtomicWriter, SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = ["SettingsGatewayCollaborators", "_SettingsGateway"]

# `backend.embedding`'s three required per-run-overridable settings keys
# (`backend/embedding/_internal/parameters.py::REQUIRED_SETTING_KEYS`) --
# hand-mirrored here rather than imported, since that name is not re-exported
# from `backend.embedding`'s public surface and `backend/embedding/` is not a
# module this story's `modules:` front-matter names (reaching into its
# `_internal` package is forbidden by import-linter regardless). Must stay in
# sync with that private constant by hand.
_EMBEDDING_REQUIRED_SETTING_KEYS: Final[tuple[SettingKey, ...]] = (
    "eval.cosine_threshold",
    "eval.embedding_cache_max_entries",
    "eval.embedding_consecutive_failures_to_skip",
)

_SELECTED_PROVIDER_NAME_KEY: Final[SettingKey] = "embedding.selected_provider_name"
_SELECTED_MODEL_NAME_KEY: Final[SettingKey] = "embedding.selected_model_name"


class _CompletionRelay[T](QObject):
    """Marshals one worker-thread completion onto the GUI thread.

    Modelled on ``adapters/ui_gateways/_internal/result/gateway.py``'s
    ``_AnalysisCompletionRelay`` -- see that class's docstring for why a
    relay lives on its own tiny ``QObject`` and why the gateway (not the
    caller) must hold a strong reference to it until delivery.
    """

    _completed = Signal(object)

    def __init__(
        self,
        on_complete: Callable[[T], None],
        *,
        on_delivered: Callable[["_CompletionRelay[T]"], None],
    ) -> None:
        super().__init__()
        self._on_complete = on_complete
        self._on_delivered = on_delivered
        self._completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def deliver(self, result: T) -> None:
        """Emit the relay signal; safe to call from any thread (typically a worker)."""
        self._completed.emit(result)

    @Slot(object)
    def _deliver(self, result: object) -> None:
        try:
            self._on_complete(cast("T", result))
        finally:
            self._on_delivered(self)


def _to_gateway_finding(finding: ImportFinding) -> ValidationFinding:
    """Translate one ``backend.import_export.models.ImportFinding`` into the
    adapter-local ``ValidationFinding`` mirror."""
    return ValidationFinding(
        severity=Severity(finding.severity.value),
        target=finding.item_key or "",
        message=finding.reason,
    )


def _to_gateway_settings_preview(
    backend_preview: BackendSettingsImportPreview,
) -> SettingsImportPreview:
    return SettingsImportPreview(
        rows=tuple(
            SettingsImportPreviewRow(
                setting_key=item.setting_key,
                current_value=item.current_value,
                imported_value=item.imported_value,
                group=PreviewGroup(item.group.value),
            )
            for item in backend_preview.items
        ),
        findings=tuple(_to_gateway_finding(finding) for finding in backend_preview.findings),
        resolved_values=dict(backend_preview.resolved_values),
        backend_preview=backend_preview,
    )


def _to_gateway_provider_preview(
    backend_preview: BackendProviderImportPreview,
) -> ProviderImportPreview:
    return ProviderImportPreview(
        rows=tuple(
            ProviderImportPreviewRow(name=item.name, group=PreviewGroup(item.group.value))
            for item in backend_preview.items
        ),
        embedding_provider_name=backend_preview.embedding_provider_name or None,
        embedding_model_name=backend_preview.embedding_model_name or None,
        findings=tuple(_to_gateway_finding(finding) for finding in backend_preview.findings),
        backend_preview=backend_preview,
    )


class SettingsGatewayCollaborators:
    """Dependency bundle for ``_SettingsGateway`` (>4-parameter rule)."""

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these thirteen
        # distinct required collaborators (<=4-parameter rule via a dependency bundle)
        self,
        *,
        providers_store: ProvidersStore,
        app_settings_store: AppSettingsStore,
        model_capabilities_store: ModelCapabilitiesStore,
        settings: SettingsService,
        atomic_writer: SettingsAtomicWriter,
        provider_registry: ProviderRegistry,
        readiness: ReadinessService,
        import_export: ImportExportService,
        gate: InferenceActivityStore,
        event_bus: EventBus,
        task_runner: TaskRunner[object],
        dispatcher: RunDispatcher,
        clock: Clock,
    ) -> None:
        self.providers_store = providers_store
        self.app_settings_store = app_settings_store
        self.model_capabilities_store = model_capabilities_store
        self.settings = settings
        self.atomic_writer = atomic_writer
        self.provider_registry = provider_registry
        self.readiness = readiness
        self.import_export = import_export
        self.gate = gate
        self.event_bus = event_bus
        self.task_runner = task_runner
        self.dispatcher = dispatcher
        self.clock = clock


class _SettingsGateway:
    """Adapter gateway for the Settings Dialog, satisfying
    ``ui.settings_dialog.protocols.SettingsGateway`` structurally (D-R-06).

    Construction is side-effect free: it performs no backend read, no probe,
    and no network call (STORY-110-AC-6).
    """

    def __init__(self, *, collaborators: SettingsGatewayCollaborators) -> None:
        self._c = collaborators
        # Untyped as `object`, not `_CompletionRelay[object]`: this set exists only to
        # hold a strong reference until delivery (add/discard by identity), never to
        # be read from, so the generic payload type each relay actually carries is
        # irrelevant here -- see `_CompletionRelay`'s own docstring.
        self._pending_relays: set[object] = set()

    # -- AC-1: ten fast-synchronous pass-throughs -------------------------------------

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return self._c.providers_store.list_providers()

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        return self._c.providers_store.get_by_name(name)

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        self._c.providers_store.replace_providers(configs)

    def get_setting(self, key: SettingKey) -> str | None:
        return self._c.app_settings_store.get_setting(key)

    def list_settings(self) -> dict[SettingKey, str]:
        return self._c.app_settings_store.list_settings()

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        self._c.app_settings_store.upsert_settings(values)

    def get_resolved_str(self, key: SettingKey) -> str:
        return self._c.settings.get_str(key)

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        return self._c.model_capabilities_store.list_model_capabilities(provider_id, model_name)

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        self._c.model_capabilities_store.upsert_model_capability(record)

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._c.readiness.snapshot()

    # -- AC-2: six import/export pass-throughs -----------------------------------------

    def build_settings_import_preview(self, file_path: str) -> SettingsImportPreview:
        return _to_gateway_settings_preview(
            self._c.import_export.build_settings_import_preview(file_path)
        )

    def apply_settings_import(self, preview: SettingsImportPreview) -> SettingsImportResult:
        backend_preview = cast("BackendSettingsImportPreview", preview.backend_preview)
        result = self._c.import_export.apply_settings_import(backend_preview)
        return SettingsImportResult(
            applied_count=result.applied_count, skipped_count=result.skipped_count
        )

    def build_provider_import_preview(self, file_path: str) -> ProviderImportPreview:
        return _to_gateway_provider_preview(
            self._c.import_export.build_provider_import_preview(file_path)
        )

    def apply_provider_import(self, preview: ProviderImportPreview) -> ProviderImportResult:
        backend_preview = cast("BackendProviderImportPreview", preview.backend_preview)
        result = self._c.import_export.apply_provider_import(backend_preview)
        return ProviderImportResult(
            applied_count=result.applied_count, skipped_count=result.skipped_count
        )

    def export_settings(self) -> bytes:
        return self._c.import_export.export_settings()

    def export_providers(self) -> bytes:
        return self._c.import_export.export_providers()

    # -- AC-3, AC-4: atomic save / reset -------------------------------------------------

    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None:
        self._c.atomic_writer.save_all(providers=providers, settings_values=settings_values)

    def reset_to_defaults(self, *, bundled_providers: tuple[ProviderConfig, ...]) -> None:
        # Local import: backend.settings.DEFAULTS is this story's own Task-1 addition
        # to that module's public surface (avoids a module-level import cycle risk
        # with the settings package still being finalized at import time -- matches
        # this file's other backend.settings import already at module scope; kept
        # inline only for readability next to its one call site).
        from ollama_llm_bench.backend.settings import DEFAULTS  # noqa: PLC0415

        self._c.atomic_writer.reset_to_defaults(
            bundled_providers=bundled_providers, all_default_settings=DEFAULTS
        )

    # -- AC-7, AC-8: test_provider / discover_models -------------------------------------

    def test_provider(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        on_complete: Callable[[InferenceTestResult], None],
    ) -> None:
        relay: _CompletionRelay[InferenceTestResult] = _CompletionRelay(
            on_complete, on_delivered=self._pending_relays.discard
        )
        self._pending_relays.add(relay)
        token = make_cancellation_token(clock=self._c.clock)
        future = self._c.task_runner.submit(
            functools.partial(self._run_test_provider, provider_id, model_name), token=token
        )
        future.add_done_callback(functools.partial(self._on_test_provider_done, relay=relay))

    def _run_test_provider(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> InferenceTestResult:
        lease = self._c.gate.try_acquire(
            InferenceActivity.PROVIDER_TEST,
            InferenceActivityContext(
                activity=InferenceActivity.PROVIDER_TEST,
                started_at=self._c.clock.monotonic_ms(),
                provider_id=provider_id,
                model_name=model_name or None,
            ),
        )
        if lease is None:
            return InferenceTestResult(
                outcome=InferenceTestOutcome.GATE_BUSY,
                provider_id=provider_id,
                model_name=model_name or "unknown",
                tested_at=self._c.clock.monotonic_ms(),
            )
        try:
            client = self._c.provider_registry.get_client(provider_id)
            if not model_name:
                return self._probe_health_as_inference_result(client, provider_id)
            return client.test_inference(model_name)
        finally:
            self._c.gate.release(lease)

    def _probe_health_as_inference_result(
        self, client: LLMClient, provider_id: ProviderId
    ) -> InferenceTestResult:
        health = client.probe_health()
        outcome = (
            InferenceTestOutcome.SUCCESS
            if health.reachable
            else InferenceTestOutcome.REACHABILITY_FAILED
        )
        return InferenceTestResult(
            outcome=outcome,
            provider_id=provider_id,
            model_name="",
            latency_ms=health.last_probe_ms,
            last_error=health.last_error,
            tested_at=health.probed_at,
        )

    def _on_test_provider_done(
        self, future: "Future[object]", *, relay: "_CompletionRelay[InferenceTestResult]"
    ) -> None:
        relay.deliver(cast("InferenceTestResult", future.result()))

    def discover_models(
        self, provider_id: ProviderId, *, on_complete: Callable[[tuple[ModelName, ...]], None]
    ) -> None:
        relay: _CompletionRelay[tuple[ModelName, ...]] = _CompletionRelay(
            on_complete, on_delivered=self._pending_relays.discard
        )
        self._pending_relays.add(relay)
        token = make_cancellation_token(clock=self._c.clock)
        future = self._c.task_runner.submit(
            functools.partial(self._run_discover_models, provider_id), token=token
        )
        future.add_done_callback(functools.partial(self._on_discover_models_done, relay=relay))

    def _run_discover_models(self, provider_id: ProviderId) -> tuple[ModelName, ...]:
        client = self._c.provider_registry.get_client(provider_id)
        return client.list_models()

    def _on_discover_models_done(
        self,
        future: "Future[object]",
        *,
        relay: "_CompletionRelay[tuple[ModelName, ...]]",
    ) -> None:
        relay.deliver(cast("tuple[ModelName, ...]", future.result()))

    # -- AC-7: probe_all / probe_embedding ------------------------------------------------

    def probe_all(self) -> None:
        self._c.dispatcher.submit(self._run_probe_all)

    def _run_probe_all(self) -> None:
        self._c.readiness.probe_all()

    def probe_embedding(self) -> None:
        token = make_cancellation_token(clock=self._c.clock)
        self._c.task_runner.submit(self._run_probe_embedding, token=token)

    def _run_probe_embedding(self) -> None:
        lease = self._c.gate.try_acquire(
            InferenceActivity.PROVIDER_TEST,
            InferenceActivityContext(
                activity=InferenceActivity.PROVIDER_TEST,
                started_at=self._c.clock.monotonic_ms(),
            ),
        )
        if lease is None:
            # The gate is held elsewhere; the button's own gate-binding already
            # prevents this click in the ordinary case, so a lost race here is
            # silently dropped rather than surfaced -- probe_embedding carries no
            # on_complete/GATE_BUSY channel for this method (ADR-0015).
            return
        try:
            reachable = self._run_embedding_capability_check()
        finally:
            self._c.gate.release(lease)
        self._publish_updated_embedding_readiness(reachable=reachable)
        return

    def _run_embedding_capability_check(self) -> bool:
        provider_name = self._c.app_settings_store.get_setting(_SELECTED_PROVIDER_NAME_KEY)
        model_name = self._c.app_settings_store.get_setting(_SELECTED_MODEL_NAME_KEY)
        if not provider_name or not model_name:
            return False
        provider = self._c.providers_store.get_by_name(provider_name)
        if provider is None:
            return False
        client = self._c.provider_registry.get_client(provider.provider_id)
        embedding_service = make_embedding_service(
            client=client,
            provider_id=provider.provider_id,
            model_name=model_name,
            snapshot=self._synthesize_embedding_settings_snapshot(),
        )
        vector = embedding_service.embed("probe")
        return len(vector) > 0

    def _synthesize_embedding_settings_snapshot(self) -> tuple[BenchmarkRunSettingEntry, ...]:
        return tuple(
            BenchmarkRunSettingEntry(setting_key=key, setting_value=self._c.settings.get_str(key))
            for key in _EMBEDDING_REQUIRED_SETTING_KEYS
        )

    def _publish_updated_embedding_readiness(self, *, reachable: bool) -> None:
        current = self._c.readiness.snapshot()
        updated = msgspec.structs.replace(current, embedding_reachable=reachable)
        summaries = tuple(
            ProviderHealthSummary(
                provider_id=health.provider_id,
                reachable=health.reachable,
                discovery_supported=health.discovery_supported,
                model_count=health.model_count,
                last_error=health.last_error,
            )
            for health in updated.per_provider
        )
        self._c.event_bus.emit(
            SIGNAL_APP_READINESS_CHANGED,
            AppReadinessChangedEvent(
                overall=updated.overall,
                per_provider=summaries,
                embedding_reachable=updated.embedding_reachable,
                checked_at=self._c.clock.now_utc(),
            ),
        )
