"""The concrete ``NewBenchmarkGateway`` implementation (STORY-106).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.2 (``NewBenchmarkGateway``), §7b (UI adapter gateways, D-R-06), §4 (the threading
contract).
"""

from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderConfig,
    RunId,
    RunStartRequest,
    SettingKey,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

__all__: list[str] = ["NewBenchmarkGatewayCollaborators", "_NewBenchmarkGateway"]


class NewBenchmarkGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so it
    is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these six
        # distinct required collaborators (<=4-parameter rule via a dependency bundle)
        self,
        *,
        app_settings: AppSettingsStore,
        settings: SettingsService,
        provider_registry: ProviderRegistry,
        readiness: ReadinessService,
        flow: BenchmarkFlowApi,
        notification: NotificationService,
    ) -> None:
        self.app_settings = app_settings
        self.settings = settings
        self.provider_registry = provider_registry
        self.readiness = readiness
        self.flow = flow
        self.notification = notification


class _NewBenchmarkGateway:
    """Adapter gateway for the New Benchmark widget, satisfying
    ``ui.new_benchmark.protocols.NewBenchmarkGateway`` structurally (D-R-06).

    Wraps ``AppSettingsStore``/``SettingsService`` (advanced-option defaults,
    ``benchmark.last_mode``, ``embedding.hide_from_test_models``), ``ProviderRegistry``
    (the model picker's provider list), ``ReadinessService`` (the pre-run readiness
    gate), ``BenchmarkFlowApi`` (the run-start command), and ``NotificationService``
    (the preflight-refusal toast). Construction is side-effect free -- it performs no
    read, no probe, and no network call (STORY-106-AC-4).

    This same concrete class also structurally satisfies
    ``ui.common_dialogs.protocols.RunSummaryGateway`` with no extra adapter class, as
    proven by STORY-104-AC-2 -- not retested here.
    """

    def __init__(self, *, collaborators: NewBenchmarkGatewayCollaborators) -> None:
        self._c = collaborators

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a user-saved setting, or ``None`` if unset."""
        return self._c.app_settings.get_setting(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a user-saved setting through the settings service."""
        self._c.settings.set(key, value)

    def provider_list(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers, in display order, for the model picker."""
        return self._c.provider_registry.list_enabled()

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the pre-run readiness gate."""
        return self._c.readiness.snapshot()

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id."""
        return self._c.flow.start(request)

    def notify_error(self, message: str) -> None:
        """Surface a non-blocking, user-facing error toast, unredacted.

        Per ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §22 (backed by
        ``10_Domain_and_Data/08_REDACTION_PATTERNS.md`` §1), redaction is scoped to
        exactly two surfaces -- the ``app.*`` log pipeline and provider-SDK
        error-message wrapping at the adapter boundary -- and UI/display surfaces do
        not apply it. ``message`` is passed through unchanged (STORY-106-AC-3).
        """
        self._c.notification.show_error(message, blocking=False)
