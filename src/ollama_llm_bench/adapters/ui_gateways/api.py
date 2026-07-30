"""Public factories for the UI adapter gateways (``01_MODULE_INVENTORY.md`` §5, ADR-0014).

Constructs the concrete ``MainWindowGateway`` over ``AppSettingsStore``,
``SettingsService``, ``ReadinessService``, ``BenchmarkFlowApi``, and ``RunDispatcher``,
and the concrete ``NewBenchmarkGateway`` over ``AppSettingsStore``, ``SettingsService``,
``ProviderRegistry``, ``ReadinessService``, ``BenchmarkFlowApi``, and
``NotificationService`` -- the adapters that let the Main Window shell and the New
Benchmark widget reach the backend without ever holding a backend Store or Service
Protocol themselves (D-R-06).
"""

import icontract

from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.ui_gateways._internal.main_window.gateway import (
    MainWindowGatewayCollaborators,
    _MainWindowGateway,
)
from ollama_llm_bench.adapters.ui_gateways._internal.new_benchmark.gateway import (
    NewBenchmarkGatewayCollaborators,
    _NewBenchmarkGateway,
)
from ollama_llm_bench.adapters.ui_gateways.protocols import (
    MainWindowGateway,
    NewBenchmarkGateway,
)
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import RunDispatcher
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

__all__: list[str] = [
    "MainWindowGateway",
    "NewBenchmarkGateway",
    "make_main_window_gateway",
    "make_new_benchmark_gateway",
]


@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda readiness: readiness is not None,
    "readiness is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda flow: flow is not None,
    "flow is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda dispatcher: dispatcher is not None,
    "dispatcher is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_main_window_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_main_window_gateway(
    *,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    readiness: ReadinessService,
    flow: BenchmarkFlowApi,
    dispatcher: RunDispatcher,
) -> MainWindowGateway:
    """Construct the Main Window's adapter gateway.

    Construction is side-effect free: it performs no backend read, no readiness
    probe, and no network call (STORY-105-AC-3).

    Args:
        app_settings: The user-saved settings store the nullable window-shell
            reads (geometry, splitter sizes, active workspace) go through.
        settings: The settings service the window-shell writes and the
            resolved theme read go through, so the settings-changed event
            fires on every write.
        readiness: The readiness service backing the status-bar health dot's
            snapshot read and re-probe trigger.
        flow: The benchmark flow API backing the quit decision and the
            graceful shutdown on application quit.
        dispatcher: The single, persistent pipeline-dispatcher thread that a
            re-probe is submitted to -- never the ``TaskRunner`` pool.

    Returns:
        A ``MainWindowGateway`` ready to be handed to ``make_main_window``.
    """
    return _MainWindowGateway(
        collaborators=MainWindowGatewayCollaborators(
            app_settings=app_settings,
            settings=settings,
            readiness=readiness,
            flow=flow,
            dispatcher=dispatcher,
        )
    )


@icontract.require(
    lambda app_settings: app_settings is not None,
    "app_settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda provider_registry: provider_registry is not None,
    "provider_registry is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda readiness: readiness is not None,
    "readiness is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda flow: flow is not None,
    "flow is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda notification: notification is not None,
    "notification is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_new_benchmark_gateway must always return a usable gateway — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_new_benchmark_gateway(  # noqa: PLR0913  # six distinct required collaborators
    # per the approved D-R-06 gateway shape (STORY-106)
    *,
    app_settings: AppSettingsStore,
    settings: SettingsService,
    provider_registry: ProviderRegistry,
    readiness: ReadinessService,
    flow: BenchmarkFlowApi,
    notification: NotificationService,
) -> NewBenchmarkGateway:
    """Construct the New Benchmark widget's adapter gateway.

    Construction is side-effect free: it performs no backend read, no readiness
    probe, and no network call (STORY-106-AC-4).

    Args:
        app_settings: The user-saved settings store the nullable
            advanced-option-default/``benchmark.last_mode``/
            ``embedding.hide_from_test_models`` reads go through.
        settings: The settings service writes go through, so the
            settings-changed event fires on every write.
        provider_registry: The provider registry backing the model picker's
            enabled-provider list.
        readiness: The readiness service backing the pre-run readiness gate's
            snapshot read.
        flow: The benchmark flow API backing the run-start command.
        notification: The notification service backing the preflight-refusal
            toast.

    Returns:
        A ``NewBenchmarkGateway`` ready to be handed to
        ``make_new_benchmark_widget``.
    """
    return _NewBenchmarkGateway(
        collaborators=NewBenchmarkGatewayCollaborators(
            app_settings=app_settings,
            settings=settings,
            provider_registry=provider_registry,
            readiness=readiness,
            flow=flow,
            notification=notification,
        )
    )
