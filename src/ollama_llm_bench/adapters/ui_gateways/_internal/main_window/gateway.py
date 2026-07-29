"""The concrete ``MainWindowGateway`` implementation (STORY-105).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.1, §12, §4 (the threading contract);
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a.
"""

from typing import Final

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import RunDispatcher
from ollama_llm_bench.backend.domain import AppReadinessSnapshot, SettingKey
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.settings import SettingsService

__all__: list[str] = [
    "MainWindowGatewayCollaborators",
    "_MainWindowGateway",
]

# The window-shell persistence keys (`08_Cross_Cutting/08-G_feature_flags.md` §7). The
# canonical registry (`backend/settings/_internal/registry.py`) is a private module this
# adapter may not import, so these are string literals mirroring its `ui.*` entries.
_KEY_WINDOW_GEOMETRY: Final[SettingKey] = "ui.window_geometry"
_KEY_SPLITTER_SIZES: Final[SettingKey] = "ui.splitter_sizes"
_KEY_ACTIVE_WORKSPACE: Final[SettingKey] = "ui.active_workspace"
_KEY_THEME: Final[SettingKey] = "ui.theme"


class MainWindowGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so it
    is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(
        self,
        *,
        app_settings: AppSettingsStore,
        settings: SettingsService,
        readiness: ReadinessService,
        flow: BenchmarkFlowApi,
        dispatcher: RunDispatcher,
    ) -> None:
        self.app_settings = app_settings
        self.settings = settings
        self.readiness = readiness
        self.flow = flow
        self.dispatcher = dispatcher


class _MainWindowGateway:
    """Adapter gateway for the Main Window shell, satisfying
    ``ui.main_window.protocols.MainWindowGateway`` structurally (D-R-06).

    Wraps ``AppSettingsStore``/``SettingsService`` (window-shell persistence),
    ``ReadinessService`` (status-bar health dot), and ``BenchmarkFlowApi`` (the quit
    decision and graceful shutdown). Construction is side-effect free -- it performs
    no read, no probe, and no network call (STORY-105-AC-3).
    """

    def __init__(self, *, collaborators: MainWindowGatewayCollaborators) -> None:
        self._c = collaborators

    # -- window-shell persistence ---------------------------------------------------
    #
    # The read/write split is deliberate. `SettingsService.get_str` guarantees a
    # default floor and can never return `None` (`backend/settings/protocols.py`), but
    # these three reads must return `None` when unset. So they go through
    # `AppSettingsStore.get_setting`, which does return `str | None`. Writes still go
    # through `SettingsService.set` so the settings-changed event fires.

    def get_window_geometry(self) -> str | None:
        """Read the persisted ``ui.window_geometry`` blob, or ``None`` if unset."""
        return self._c.app_settings.get_setting(_KEY_WINDOW_GEOMETRY)

    def set_window_geometry(self, value: str) -> None:
        """Persist the ``ui.window_geometry`` blob (debounced by the caller)."""
        self._c.settings.set(_KEY_WINDOW_GEOMETRY, value)

    def get_splitter_sizes(self) -> str | None:
        """Read the persisted ``ui.splitter_sizes``, or ``None`` if unset."""
        return self._c.app_settings.get_setting(_KEY_SPLITTER_SIZES)

    def set_splitter_sizes(self, value: str) -> None:
        """Persist ``ui.splitter_sizes``."""
        self._c.settings.set(_KEY_SPLITTER_SIZES, value)

    def get_active_workspace(self) -> str | None:
        """Read the persisted ``ui.active_workspace`` (``"benchmark"``/``"task_editor"``)."""
        return self._c.app_settings.get_setting(_KEY_ACTIVE_WORKSPACE)

    def set_active_workspace(self, value: str) -> None:
        """Persist ``ui.active_workspace``."""
        self._c.settings.set(_KEY_ACTIVE_WORKSPACE, value)

    def get_theme(self) -> str:
        """Read the resolved ``ui.theme`` setting (never absent -- ``get_str`` floors it)."""
        return self._c.settings.get_str(_KEY_THEME)

    def set_theme(self, value: str) -> None:
        """Persist ``ui.theme``."""
        self._c.settings.set(_KEY_THEME, value)

    # -- readiness --------------------------------------------------------------------

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the status-bar dot; never probes."""
        return self._c.readiness.snapshot()

    def reprobe(self) -> None:
        """Trigger a readiness re-probe and return without waiting for it.

        Submits to the ``RunDispatcher`` (DD-38), never to the ``TaskRunner`` pool.
        ``ReadinessService.probe_all()`` itself fans one probe per provider out to the
        pool and blocks waiting for all of them; running it *on* a pool thread would be
        a pool thread waiting on pool threads, which
        `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a forbids. With the
        pool fixed at four threads and each provider's timeout clock starting at
        *queue* time (not start time), doing so would silently misreport healthy
        providers as unreachable once there are four or more providers. The new
        snapshot reaches the UI via the readiness-changed bus event, never through this
        method's return value.
        """
        self._c.dispatcher.submit(self._run_probe)

    def _run_probe(self) -> None:
        """Run one probe batch on the dispatcher thread, discarding its return value.

        ``RunDispatcher.submit`` takes a ``Callable[[], None]``, but
        ``ReadinessService.probe_all()`` returns a snapshot -- this wrapper bridges the
        two so a direct method reference does not fail ``mypy --strict``.
        """
        self._c.readiness.probe_all()

    # -- the quit decision --------------------------------------------------------------

    def is_run_active(self) -> bool:
        """Whether a run is currently active (non-terminal) -- the quit decision."""
        return self._c.flow.is_running()

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit (bounded wait)."""
        self._c.flow.shutdown(timeout_ms)
