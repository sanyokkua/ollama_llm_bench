"""Public factory for the Main Window gateway (``01_MODULE_INVENTORY.md`` §5, ADR-0014).

Constructs the concrete ``MainWindowGateway`` over ``AppSettingsStore``,
``SettingsService``, ``ReadinessService``, ``BenchmarkFlowApi``, and ``RunDispatcher`` --
the adapter that lets the Main Window shell reach the backend without ever holding a
backend Store or Service Protocol itself (D-R-06).
"""

import icontract

from ollama_llm_bench.adapters.ui_gateways._internal.main_window.gateway import (
    MainWindowGatewayCollaborators,
    _MainWindowGateway,
)
from ollama_llm_bench.adapters.ui_gateways.protocols import MainWindowGateway
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import RunDispatcher
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

__all__: list[str] = ["MainWindowGateway", "make_main_window_gateway"]


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
