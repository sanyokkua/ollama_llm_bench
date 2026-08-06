"""Shared rig for `tests/integration/` tests that build the real composed application.

Moved here from `test_compose_build_app.py` so the theme-reapply and menu-dialog suites
(STORY-083) share one copy instead of triplicating it. The autouse
`_disconnect_os_color_scheme_signal` fixture is load-bearing: every `build_app` constructs a
`ThemeManager` that connects to the session-scoped `qapp.styleHints().colorSchemeChanged`,
and `pytest-randomly` reorders tests, so a leaked connection corrupts a later test. Because
this fixture is autouse, it now runs for *every* test under `tests/integration/`, including
the `persistence/` and `provider_stub/` suites that never construct a `ThemeManager` and so
have nothing connected -- `_disconnect_and_discard_warning` below exists to make that the
common case a silent no-op rather than a `RuntimeWarning`.

**Cross-platform filesystem isolation.** The real, non-injected `PlatformDetector` `build_app`
constructs (`make_platform_detector()`) resolves `<app-data>` from `Path.home()` on macOS and
Windows, and only falls back to `XDG_DATA_HOME` on Linux
(`backend/platform/_internal/detector.py`). The root `conftest.py`'s `_isolate_filesystem`
fixture only redirects `XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`LOCALAPPDATA` into `tmp_path` -- so
on a macOS/Windows host it does *not* stop a real `build_app()` call from resolving into this
machine's actual user profile directory. `compose.py` is the only call site in the whole
codebase that constructs the real, non-injected `InjectablePlatformDetector` this way. The
`isolated_home` fixture below additionally redirects `HOME`/`USERPROFILE` into `tmp_path` so
every test that depends on it (directly, or transitively through `seeded_app_data_root`/
`build_real_app`) is safe on every host platform, regardless of which OS branch
`Path.home()` resolves through.

**No cross-module import.** `_seed_setting`, `_shutdown`, `_build_common_dialogs`, and
`_DISPATCHER_SHUTDOWN_TIMEOUT_MS` stay module-private here and are handed to test modules only
through the `seed_setting`, `shutdown_handle`, `common_dialogs`, and
`dispatcher_shutdown_timeout_ms` fixtures below -- pytest auto-injects fixtures by name, so no
test module needs `from tests.integration.conftest import ...`. There are zero `__init__.py`
files anywhere under `tests/`; adding one just to support that kind of import would be a wider,
unrelated change to how this repository's test tree is packaged.
"""

from collections.abc import Callable, Generator
import functools
from pathlib import Path
from typing import Final
import warnings

import msgspec
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.clipboard import make_clipboard
from ollama_llm_bench.adapters.file_system_actions import make_file_system_actions
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ModelDescriptor,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
)
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import (
    create_providers_store,
    seed_builtin_providers,
)
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.compose import AppHandle, build_app
from ollama_llm_bench.ui.common_dialogs import (
    AboutDialogCollaborators,
    ErrorDialogPattern,
    ErrorDialogPayload,
    GenerateAnalysisCollaborators,
    make_about_dialog,
    make_error_dialog,
    make_generate_analysis_dialog,
    make_rename_run_dialog,
    make_resume_summary_dialog,
    make_retry_selection_dialog,
    make_run_summary_dialog,
)
from ollama_llm_bench.ui.new_benchmark.testing import FakeRunValidator

_PROVIDER_ID: Final[str] = "550e8400-e29b-41d4-a716-446655440000"
_MODEL_NAME: Final[str] = "llama3.1:8b"
_RUN_ID: Final[int] = 1
_TIMESTAMP: Final[str] = "2026-08-05T12:00:00Z"

_DIALOG_SIZE: Final[tuple[int, int]] = (900, 700)


class _StubRenameRunGateway:
    """Structural ``RenameRunGateway`` returning one canned run header."""

    def __init__(self, *, runs: tuple[BenchmarkRun, ...]) -> None:
        self._runs = runs

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        return None


class _StubRunSummaryGateway:
    """Structural ``RunSummaryGateway`` whose readiness passes preflight."""

    def __init__(self, *, readiness: AppReadinessSnapshot) -> None:
        self._readiness = readiness

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def start_run(self, request: RunStartRequest) -> RunId:
        return _RUN_ID


class _StubResumeSummaryGateway:
    """Structural ``ResumeSummaryGateway`` with non-empty resumable results."""

    def __init__(self, *, run: BenchmarkRun, results: tuple[BenchmarkResult, ...]) -> None:
        self._run = run
        self._results = results

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._run

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return ()

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRetrySelectionGateway:
    """Structural ``RetrySelectionGateway`` with a non-empty result table."""

    def __init__(self, *, results: tuple[BenchmarkResult, ...]) -> None:
        self._results = results

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRunAnalysisDispatcher:
    """Structural ``RunAnalysisDispatcher`` that always accepts a dispatch."""

    def regenerate_analysis(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> bool:
        return True


class _StubProviderListSource:
    """Structural ``ProviderListSource`` offering one enabled provider."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...]) -> None:
        self._providers = providers

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return self._providers


class _StubModelFetcher:
    """Structural ``ModelFetcher`` delivering a canned catalogue synchronously."""

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        on_success(provider_id, (_MODEL_NAME,))


class _StubSubscription:
    """Structural ``Subscription`` handle; cancellation is a no-op for a capture."""

    def cancel(self) -> None:
        return None


class _StubGenerateAnalysisEventBus:
    """Structural ``EventBus`` fake routing around a real production defect.

    ``ui/common_dialogs/_internal/generate_analysis_view.py`` calls
    ``event_bus.subscribe(signal, handler)`` three times with no ``owner=``
    keyword. The real ``QtEventBusDeliverer.subscribe`` (used everywhere else
    in this harness) carries an ``icontract`` precondition requiring a non-
    ``None`` owner (08-J §2), so building this one dialog against the real
    bus raises ``icontract.errors.ViolationError`` -- a genuine bug that would
    crash any real user opening this dialog, masked in
    ``ui/common_dialogs/tests/test_generate_analysis_dialog.py`` by that
    module's own ``_FakeEventBus``, which accepts a missing owner silently.
    This mirrors that same fake, scoped to this one dialog only, so both the
    mockup-conformance screenshot harness (``test_screenshot_harness.py``) and
    the accessibility-name walker (``test_a11y_names_shell.py``) can build
    this dialog without hitting that defect. It changes no behaviour of its
    own -- it only accepts the missing-owner calls the real bus would reject.
    """

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> _StubSubscription:
        return _StubSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


def _canned_provider() -> ProviderConfig:
    """Return one enabled provider entry for the Generate Analysis dropdown."""
    return ProviderConfig(
        provider_id=_PROVIDER_ID,
        name="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _canned_readiness() -> AppReadinessSnapshot:
    """Return a snapshot with one reachable provider and a reachable embedding."""
    return AppReadinessSnapshot(
        overall=ReadinessState.READY,
        per_provider=(
            ProviderHealth(
                provider_id=_PROVIDER_ID,
                reachable=True,
                discovery_supported=True,
                model_count=3,
                last_probe_ms=12,
                probed_at=0,
            ),
        ),
        embedding_reachable=True,
    )


def _canned_request() -> RunStartRequest:
    """Return a start request that passes the Run Summary preflight."""
    return RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _canned_run() -> BenchmarkRun:
    """Return one completed run header."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp=_TIMESTAMP,
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=4,
        completed_tasks=2,
        total_elapsed_ms=42_000,
        schema_version=1,
        created_at=_TIMESTAMP,
    )


def _canned_results() -> tuple[BenchmarkResult, ...]:
    """Return two result rows: one completed, one failed and retryable."""
    return (
        BenchmarkResult(
            result_id=1,
            run_id=_RUN_ID,
            task_id="synthetic_small_1",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.COMPLETED,
            created_at=_TIMESTAMP,
        ),
        BenchmarkResult(
            result_id=2,
            run_id=_RUN_ID,
            task_id="synthetic_small_2",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.FAILED_TIMEOUT,
            created_at=_TIMESTAMP,
        ),
    )


def _build_common_dialogs(*, qtbot: QtBot) -> dict[str, QDialog]:
    """Construct all seven shared modal dialogs, shown but never exec()'d.

    Three of the seven factories (``make_run_summary_dialog``,
    ``make_resume_summary_dialog``, ``make_retry_selection_dialog``) return
    ``QDialog | None`` -- ``None`` when their gateway's canned data is too
    thin to pass the dialog's own precondition. The canned data above is
    constructed specifically to satisfy every one of those preconditions, so
    a ``None`` here means the canned data regressed, not a normal outcome to
    tolerate.
    """
    bus = make_qt_event_bus_deliverer()
    clipboard = make_clipboard()
    candidates: dict[str, QDialog | None] = {
        "07_common_dialogs__about": make_about_dialog(
            collaborators=AboutDialogCollaborators(
                clipboard=clipboard,
                file_system_actions=make_file_system_actions(),
                event_bus=bus,
            ),
            version="0.0.0",
            data_folder_path="/home/user/.local/share/OllamaLLMBench",
        ),
        "07_common_dialogs__error": make_error_dialog(
            payload=ErrorDialogPayload(
                title="Provider unreachable",
                message="The benchmark could not reach the configured provider.",
                detail="HttpConnectionError: connection refused (127.0.0.1:11434)",
                pattern=ErrorDialogPattern.RECOVERABLE,
            ),
            clipboard=clipboard,
            event_bus=bus,
        ),
        "07_common_dialogs__rename_run": make_rename_run_dialog(
            gateway=_StubRenameRunGateway(runs=(_canned_run(),)),
            run_id=_RUN_ID,
            current_custom_name=None,
            computed_default_name="Synthetic run — 2026-08-05 12:00",
        ),
        "07_common_dialogs__run_summary": make_run_summary_dialog(
            gateway=_StubRunSummaryGateway(readiness=_canned_readiness()),
            run_validator=FakeRunValidator(),
            request=_canned_request(),
        ),
        "07_common_dialogs__resume_summary": make_resume_summary_dialog(
            gateway=_StubResumeSummaryGateway(run=_canned_run(), results=_canned_results()),
            event_bus=bus,
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__retry_selection": make_retry_selection_dialog(
            gateway=_StubRetrySelectionGateway(results=_canned_results()),
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__generate_analysis": make_generate_analysis_dialog(
            run=_canned_run(),
            collaborators=GenerateAnalysisCollaborators(
                dispatcher=_StubRunAnalysisDispatcher(),
                provider_source=_StubProviderListSource(providers=(_canned_provider(),)),
                model_fetcher=_StubModelFetcher(),
                # Not the shared real `bus` -- see `_StubGenerateAnalysisEventBus`'s
                # docstring for the real production defect this routes around.
                event_bus=_StubGenerateAnalysisEventBus(),
            ),
        ),
    }
    dialogs: dict[str, QDialog] = {}
    for capture_id, dialog in candidates.items():
        if dialog is None:
            message = f"{capture_id} factory returned None; its gateway data is insufficient"
            raise AssertionError(message)
        qtbot.addWidget(dialog)
        dialog.resize(*_DIALOG_SIZE)
        dialog.show()
        dialogs[capture_id] = dialog
    qtbot.wait(0)
    return dialogs


@pytest.fixture
def common_dialogs(qtbot: QtBot) -> dict[str, QDialog]:
    """All seven shared modal dialogs, built with canned data and stub gateways.

    Both the mockup-conformance screenshot harness and the accessibility-name walker
    mount the same seven dialogs from this one definition rather than two drifting
    copies. Three of the seven builders return `QDialog | None` -- `None` when their
    gateway's canned data is too thin to pass the dialog's own precondition. The
    canned data here satisfies every one of those preconditions, so a `None` means
    the canned data regressed and the narrowing below must keep failing loudly.
    """
    return _build_common_dialogs(qtbot=qtbot)


_DISPATCHER_SHUTDOWN_TIMEOUT_MS = 2000


def _disconnect_and_discard_warning(signal: SignalInstance) -> None:
    """Disconnect every slot from `signal`, discarding whatever warning PySide6 emits.

    PySide6's `SignalInstance.disconnect()` does not raise when there is nothing to
    disconnect -- it emits a Python-level `RuntimeWarning` ("Failed to disconnect (None)
    from signal ...") straight from the C++ binding and returns normally. That warning is
    invisible to `tests/conftest.py`'s `_qt_parity_rig` (which only intercepts C++-level
    `qInstallMessageHandler` traffic, not Python's `warnings` module), so it would otherwise
    print unchecked noise for every test in this directory that never connects the signal in
    the first place (confirmed empirically: `persistence/` and `provider_stub/` never
    construct a `ThemeManager`, so every one of their tests hit this).

    `warnings.catch_warnings(record=True)` combined with `simplefilter("always")` captures
    every warning `disconnect()` raises -- regardless of category or exact wording -- into a
    local list that this function never inspects and lets go out of scope, so it never
    escapes to the caller or to pytest's warning capture. Nothing is ever escalated to an
    exception, so no `SystemError` can arise from an escalated warning crossing the C++
    binding, and no exception type needs to be caught or suppressed. When something *is*
    connected, `disconnect()` performs the real disconnection and returns without warning, so
    this still performs the cleanup teardown needs either way. Verified empirically against
    the real `qapp.styleHints().colorSchemeChanged` signal: with nothing connected, no
    warning escapes and no exception is raised; with a slot connected, `signal.emit(...)`
    before this call reaches the slot and no longer does after it, proving the slot was
    genuinely disconnected rather than merely silenced -- and no warning escapes in the
    connected case either.
    """
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        signal.disconnect()


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Disconnect every `ThemeManager` this file's `build_app` calls attached to
    `qapp.styleHints().colorSchemeChanged` -- production never disconnects this
    specific signal. STORY-083's runtime theme re-application (landed in
    `compose.py`) subscribes to the settings-changed event bus instead and never
    touches this OS-colour-scheme connection, so this fixture is still needed: a
    `ThemeManager` built by one test here would otherwise stay connected and
    react to a *later, unrelated* test's own OS-colour-scheme simulation in the
    same session-scoped `qapp` (this contaminated
    `ui/theme/tests/test_theme_selection.py`'s own `test_explicit_override_ignores_
    live_os_change` before this fixture was added). Mirrors the identical cleanup
    `ui/theme/tests/test_theme_selection.py` and `tests/integration/
    test_theme_switching.py` already use for the same signal.
    """
    yield
    _disconnect_and_discard_warning(qapp.styleHints().colorSchemeChanged)
    qapp.styleHints().unsetColorScheme()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` into `tmp_path` -- see the module docstring."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _create_app_data_root_with_schema() -> Path:
    """Create, and apply the schema to, the database at the exact `<app-data>` path
    `build_app` itself will resolve and open (same detector, same environment).

    Returns the app-data root with the write connection already closed, so the caller --
    and then `build_app` -- can reopen it. Callers wanting rows in `providers` seed them
    in their own connection; see the three `*app_data_root*` fixtures below.
    """
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.close()
    return app_data_root


@pytest.fixture
def seeded_app_data_root(isolated_home: Path) -> Path:
    """Pre-create the schema and the enabled builtin providers at the exact `<app-data>`
    path `build_app` itself will resolve and open."""
    # Arrange
    app_data_root = _create_app_data_root_with_schema()
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    seed_builtin_providers(write_conn, lock)
    write_conn.close()
    return app_data_root


@pytest.fixture
def app_data_root_no_providers(isolated_home: Path) -> Path:
    """Pre-create the schema only -- zero rows in `providers`, at the exact `<app-data>`
    path `build_app` itself will resolve and open.

    Originally a `test_compose_build_app.py`-local fixture backing that file's regression
    test for the STORY-077 remediation's Fix 1 (a fresh install must not crash
    `build_app`); lifted here so the whole directory shares one copy of the rig.
    `test_compose_build_app.py` still gets it by fixture name, unchanged.

    **This does not produce a running application with no providers.** `build_app` itself
    re-seeds the builtins whenever it finds `providers` empty (`compose.py`:
    `if not provs.list_providers(): seed_builtin_providers(...)`) -- an empty table is a
    *fresh install*, and seeding it is exactly what a fresh install does. A test that needs
    the built application to have no *enabled* provider wants
    `app_data_root_all_providers_disabled` below instead.
    """
    # Arrange
    return _create_app_data_root_with_schema()


@pytest.fixture
def app_data_root_all_providers_disabled(isolated_home: Path) -> Path:
    """Pre-create the schema and the builtin providers, then disable every one of them.

    The rows are present, so `build_app`'s fresh-install re-seed does not fire and the
    application it builds genuinely has zero *enabled* providers -- the "every provider has
    been disabled" configuration `test_compose_build_app.py`'s
    `test_build_app_survives_zero_enabled_providers` describes, and a configuration a real
    user can reach from the Settings dialog by unticking all three.

    This is what makes a test that opens the real Settings dialog offline-safe; see
    `build_real_app_without_enabled_providers` below for the full reasoning.
    """
    # Arrange
    app_data_root = _create_app_data_root_with_schema()
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    seed_builtin_providers(write_conn, lock)
    store = create_providers_store(
        write_conn, lock, functools.partial(open_read_connection, db_path)
    )
    store.replace_providers(
        tuple(msgspec.structs.replace(config, enabled=False) for config in store.list_providers())
    )
    write_conn.close()
    return app_data_root


def _seed_setting(app_data_root: Path, *, key: str, value: str) -> None:
    """Persist one `AppSettingsStore` row directly, before `build_app` opens its own
    write connection to the same database file."""
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    read_conn = functools.partial(open_read_connection, db_path)
    store = create_app_settings_store(write_conn, lock, read_conn, make_system_clock())
    store.upsert_settings({key: value})
    write_conn.close()


_MAX_TASK_RUNNER_DRAIN_PASSES = 10
_TASK_RUNNER_DRAIN_TICK_MS = 10


def _drain_pending_task_runner_deliveries(handle: AppHandle, qtbot: QtBot) -> None:
    """Let every in-flight `TaskRunner` unit finish and its queued-signal completion be
    delivered, while `handle`'s widget tree is still fully alive.

    **Call this from the test body itself, before the test function returns** -- never
    from a fixture finalizer. Building the real app and opening a real dialog can leave
    asynchronous work in flight when the test body returns. The concrete case this exists
    for: opening the Settings dialog runs `ui/settings_dialog/_internal/providers_tab/
    embedding_section.py`'s first-start embedding bootstrap search, which submits a
    `discover_models` call per enabled provider to `handle.task_runner`'s real
    `QThreadPool` and delivers the result back to a dropdown widget via `adapters/
    ui_gateways/_internal/settings/gateway.py`'s `_CompletionRelay` -- a **queued**
    connection (`Qt.ConnectionType.QueuedConnection`).

    A queued signal is only *emitted* when the worker thread finishes; it is not
    *delivered* until something ticks the GUI event loop. If the test ends without ever
    ticking the loop again, the queued delivery survives -- unfired -- past this test's
    own teardown (neither dialog sets `WA_DeleteOnClose`, so `compose.py` keeps them
    alive as children of the main window in production) and only gets a chance to fire on
    whatever event-loop tick happens to run next: typically the *next* test's, once this
    test's widget tree has since been torn down. By then the widget it targets has
    already been destroyed, so it crashes with `RuntimeError: Internal C++ object (...)
    already deleted` in a test that never itself did anything wrong.

    **Why this must run from the test body, not a fixture teardown (found the hard
    way).** `qtbot.addWidget(handle.window)` registers the window with `pytest-qt`, whose
    own `pytest_runtest_teardown` hookwrapper (`pytestqt/plugin.py`) calls
    `_close_widgets(item)` -- `widget.close(); widget.deleteLater()` -- *before* running
    any test fixture's finalizer, `build_real_app`'s included. Calling this function's
    `qtbot.wait(...)` ticks from inside a fixture finalizer runs a real nested event loop
    (`QTest.qWait`), which flushes that already-scheduled `deleteLater()` too -- destroying
    `handle.window` earlier than the finalizer expects and turning `_shutdown`'s own
    `handle.window.close()` into a crash on an already-deleted object (confirmed by
    reproducing it: moving this drain into `build_real_app`'s finalizer made the *main
    window* itself come up "already deleted", strictly worse than the original bug).
    Calling it from the test body sidesteps this entirely -- `pytest-qt` does not touch
    tracked widgets until `pytest_runtest_teardown`, well after the test function returns.

    `handle.task_runner.shutdown()` blocks the calling thread until the pool is
    genuinely idle (`QThreadPool.waitForDone()`) -- a real condition, not a sleep, and
    idempotent (`_shutdown`'s own step 2b calls it again later; a no-op by then). But
    *delivering* a queued signal can submit *more* work -- the embedding bootstrap search
    chains one provider's discovery into the next's from inside the delivered callback
    (`_on_bootstrap_models_discovered` -> `_bootstrap_search_next`) -- so a single
    drain-then-tick pass is not always enough. This loops "drain the pool, then tick the
    loop" a bounded number of times: three builtin providers are seeded per test
    (`seed_builtin_providers`), so the bootstrap search chains at most three rounds;
    `_MAX_TASK_RUNNER_DRAIN_PASSES` gives more than triple that as a safety margin
    (mirroring `test_theme_reapply_on_save.py`'s `_flush_pending_widget_deletions`, which
    caps its own condition-based widget-teardown loop at the same value for the same
    reason -- a generous, explained bound instead of an unbounded wait). Each pass costs
    at most `_TASK_RUNNER_DRAIN_TICK_MS`, and every pass past the point delivery has
    genuinely stopped spawning new work costs next to nothing (`waitForDone()` returns
    immediately on an already-idle pool), so spending the full budget on a test with
    nothing pending is cheap.
    """
    for _ in range(_MAX_TASK_RUNNER_DRAIN_PASSES):
        handle.task_runner.shutdown()
        qtbot.wait(_TASK_RUNNER_DRAIN_TICK_MS)


_NOT_READY_MODAL_DISMISS_DELAY_MS = 100


def _dismiss_message_box(modal: QMessageBox) -> None:
    """Hide `modal` in a way that always removes it from Qt's modal-widget stack.

    Identical to `tests/integration/test_menu_opens_dialogs.py`'s
    `_dismiss_and_clear_modal_stack` -- see that helper's docstring for the full mechanics.
    In short: `QDialog.exec()` (which `QMessageBox.critical()` calls internally) shows the
    dialog, which is what pushes it onto `QApplication.activeModalWidget()`'s stack; a plain
    `close()`/`hide()` after the nested loop is already running does not reliably pop that
    stack back off, and a stale entry left behind aborts a later, unrelated test's own modal
    lookup with a fatal `QTEST_ASSERT` inside Qt. Restoring `WA_ShowModal` immediately before
    hiding makes Qt run `leaveModal` and clears the stack properly; this is safe to call even
    if the dialog already dismissed itself for some other reason (`hide()` on an
    already-hidden widget is a no-op inside Qt).
    """
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _DismissReadinessModalOnShow(QObject):
    """App-wide event filter that auto-dismisses the real NOT_READY `QMessageBox` the
    instant it is shown, wherever in a test's execution it happens to appear.

    **Why this can't just be a delayed one-shot timer armed after `build_app()` returns**
    (the way `tests/e2e/conftest.py`'s `_dismiss_active_modal_if_shown` does it). There, the
    modal is only ever triggered once, by the deferred `QTimer.singleShot(0, ...)` armed on
    the main window's first `showEvent`, so a single dismiss timer scheduled right after
    build time is guaranteed to run after it. Here that assumption does not hold: opening the
    real Settings dialog (`MainWindowController._on_settings_requested` ->
    `SettingsDialogController.__init__` -> a synchronous `readiness.probe_all()`) re-runs the
    readiness probe *synchronously, inside the menu-bar click itself* -- confirmed by
    tracing a hang with `faulthandler.dump_traceback_later`: the modal opens from inside
    `compose.py`'s `_open_settings()`, before `make_settings_dialog(...)` has even
    constructed the real dialog, let alone called its `.exec()`. The NOT_READY modal can
    therefore appear at build time, at the first `window.show()`, or mid-test from an
    arbitrary later user action -- an event filter watching for the moment Qt actually shows
    a `QMessageBox` is the only thing that reliably catches all three.

    **Why this is safe for the tests that assert on a real Settings/About dialog
    (`test_menu_opens_dialogs.py`) or drive a real error dialog's Quit button
    (`test_launch_abort_modal_quits.py`).** This filter only ever acts on a widget that
    `isinstance(watched, QMessageBox)` -- `QMessageBox.critical(...)` is what the production
    NOT_READY path calls (`adapters/notification_service/_internal/qt_notification_service.py`
    `_show_modal`). The Settings and About dialogs are `SettingsDialogView`/`AboutDialog`,
    both plain `QDialog` subclasses, never `QMessageBox`; the launch-abort error dialog is
    `ErrorDialog`, also a plain `QDialog`. None of them can ever satisfy this `isinstance`
    check, so this filter cannot race with or steal a dialog those tests are asserting on --
    and `test_launch_abort_modal_quits.py` does not use this fixture's build path at all (it
    calls `build_app` directly), so it is doubly unaffected.

    **Why the dismiss is scheduled on a delay rather than done synchronously inside the Show
    event.** `QDialog.exec()`'s sequence is `show()` (which is what dispatches the `Show`
    event this filter reacts to) followed by constructing and running its own nested
    `QEventLoop` -- that loop object does not exist yet while `show()` is still on the call
    stack, so hiding the widget from directly inside the event filter has nothing to make the
    nested loop return; the loop would still block forever once `exec()` reaches it. Every
    other real-dialog dismissal in this test suite (`test_menu_opens_dialogs.py`,
    `tests/e2e/conftest.py`) uses the same "come back a little later, once the nested loop is
    actually running" pattern for the same reason.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(
                _NOT_READY_MODAL_DISMISS_DELAY_MS, functools.partial(_dismiss_message_box, watched)
            )
        return False


@pytest.fixture(autouse=True)
def _dismiss_not_ready_modal(qapp: QApplication) -> Generator[None]:
    """Install `_DismissReadinessModalOnShow` on `qapp` for every test in this directory, not
    only the ones built through `build_real_app`/`build_real_app_without_enabled_providers`.

    **Why this must be directory-wide.** Eight modules build the real application by calling
    `compose.build_app` directly (`test_launch_crash_recovery.py`, `test_launch_app_data_dir.py`,
    `test_ui_thread_exception_hook.py`, `test_quit_sequence.py`, `test_launch_schema_check.py`,
    `test_launch_abort_modal_quits.py`, `test_launch_seeding.py`,
    `test_launch_instance_lock.py`), bypassing both fixtures entirely. None of them currently
    calls `handle.window.show()`, so the readiness tick `MainWindowController` arms on the main
    window's `showEvent` never fires and the real NOT_READY `QMessageBox.critical(...).exec()`
    (`08_Cross_Cutting/08-M_app_lifecycle.md` section 5) never has a chance to open -- but that is
    an accident of what those tests happen to exercise today, not a guarantee. The first test
    added to any of those modules that shows its window while running offline (no reachable
    provider, which is how every `isolated_home`-based fixture in this directory builds its
    app-data root) blocks the GUI thread inside that modal's nested event loop forever, and this
    repository has no `pytest-timeout` to rescue the run.

    Making this fixture autouse for the whole directory, rather than leaving the filter installed
    only inside `_app_handle_factory`, closes that gap once for every current and future test
    here -- including the eight `build_app`-direct modules above, which get no other chance to
    opt in since they never go through either fixture.

    **Verified safe for the tests that assert on a real, visible dialog.** The filter only acts
    on `isinstance(watched, QMessageBox)` -- see `_DismissReadinessModalOnShow`'s own docstring.
    `SettingsDialogView` and `AboutDialog` (`test_menu_opens_dialogs.py`) and `ErrorDialog` (the
    launch-abort error dialog `test_launch_abort_modal_quits.py` and the schema-mismatch/
    app-data-directory abort paths in `test_launch_schema_check.py`/`test_launch_app_data_dir.py`
    show) are all plain `QDialog` subclasses, confirmed by reading their class definitions --
    none of them can ever satisfy this `isinstance` check, so this filter cannot dismiss or race
    with a dialog those tests are asserting on.

    **Verified safe for `test_launch_abort_modal_quits.py` specifically.** That module's own
    `_clear_qt_quit_flag` autouse fixture (module-local, not this one) still runs -- autouse
    fixtures from different `conftest.py`/module scopes all apply, they do not replace each
    other. Its test never calls `handle.window.show()` (the abort happens before `build_app`
    ever returns a handle), so this filter's event loop never has a `QMessageBox` to see in that
    test; installing an inert, never-triggered filter on `qapp` for the duration of that test
    changes nothing about its behaviour.

    Installed and removed per-test (function-scoped, matching `qapp`'s own effective per-test
    widget lifetime in this suite) so no filter instance leaks into a later test.
    """
    dismiss_not_ready_modal = _DismissReadinessModalOnShow()
    qapp.installEventFilter(dismiss_not_ready_modal)
    yield
    qapp.removeEventFilter(dismiss_not_ready_modal)


def _shutdown(handle: AppHandle) -> None:
    """Release the real dispatcher thread, HTTP client, write connection, and instance
    lock a test's `build_app` call constructed, so no test leaks a live thread or a
    held lock into the next one.

    Closes the window *first* -- the shell's real close sequence (`CloseHandler` ->
    `_on_confirmed_quit` -> a pending-geometry flush) needs a live database. Closing
    it here, once, up front makes `pytestqt`'s own automatic end-of-test
    `_close_widgets()` call a harmless no-op afterwards (the shell is already
    `_quitting`, so a second `closeEvent` short-circuits before touching the database
    again). `AppHandle.shutdown()` now performs the full 5-step ordered shutdown
    (STORY-080) in one call.
    """
    handle.window.close()
    handle.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)


def _app_handle_factory(qapp: QApplication) -> Generator[Callable[[], AppHandle]]:
    """Body shared by `build_real_app` and `build_real_app_without_enabled_providers`: hand
    out a factory building real `AppHandle`s, then tear down every handle it built.

    Both fixtures differ only in *which* app-data fixture they depend on -- i.e. what is
    already in the database at the `<app-data>` path `build_app` resolves -- so the build
    and teardown logic lives here once and each fixture delegates to it with `yield from`
    (which forwards the teardown half as well, when pytest resumes the outer generator).

    Both fixtures build against an app-data root with no reachable provider (all disabled, or
    real localhost endpoints with nothing listening on an offline runner), so the real
    application genuinely computes `NOT_READY` and production genuinely opens a blocking
    `QMessageBox` (`08_Cross_Cutting/08-M_app_lifecycle.md` §5). The directory-wide autouse
    `_dismiss_not_ready_modal` fixture above installs `_DismissReadinessModalOnShow` on `qapp`
    for every test in this directory, this factory included, so this function no longer installs
    its own copy -- see that fixture's docstring for why one directory-wide filter now covers
    both this factory's tests and the modules that build `AppHandle` directly.
    """
    built: list[AppHandle] = []

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build

    for handle in built:
        _shutdown(handle)


@pytest.fixture
def build_real_app(
    qapp: QApplication, seeded_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Factory building a real `AppHandle` against the seeded, isolated app-data
    directory; every handle it built is torn down at the end of the test.

    The three seeded builtin providers are **enabled** and point at real local endpoints
    (`http://localhost:11434` for Ollama, `http://localhost:1234` for LM Studio), so a test
    that opens the real Settings dialog against *this* fixture performs real network I/O
    against whatever the developer happens to have running -- see
    `build_real_app_without_enabled_providers` below, which exists precisely to avoid that.

    A test that triggers real background work through `handle.task_runner` must drain it
    itself, via the `drain_task_runner_deliveries` fixture below, before the test function
    returns -- see `_drain_pending_task_runner_deliveries`'s docstring for why that cannot
    instead be done here, in this fixture's own teardown.
    """
    yield from _app_handle_factory(qapp)


@pytest.fixture
def build_real_app_without_enabled_providers(
    qapp: QApplication, app_data_root_all_providers_disabled: Path
) -> Generator[Callable[[], AppHandle]]:
    """Same factory as `build_real_app`, but against an app-data directory whose builtin
    providers are all **disabled** -- so nothing the built application does can reach a
    network endpoint.

    Use this for any test that opens the real Settings dialog. That dialog's embedding
    section runs a first-start bootstrap search over the *enabled* providers
    (`ui/settings_dialog/_internal/providers_tab/embedding_section.py`
    `_bootstrap_search_next`), submitting a real `discover_models` call per provider to
    `handle.task_runner`'s `QThreadPool` and delivering each result back through a queued
    connection. Against `build_real_app`'s seeded builtins those calls hit
    `localhost:11434`/`localhost:1234` for real, which makes the test's timing -- and
    therefore how much in-flight work survives into the next test -- depend on whether the
    developer running it happens to have Ollama or LM Studio up. That is how a menu-dialog
    test came to abort the whole pytest process on a machine with those servers running
    while looking clean on an offline CI runner. With every provider disabled the
    bootstrap's `enabled_providers` tuple is empty, so `_bootstrap_search_next` returns at
    its first line without submitting anything: no thread-pool work, no queued delivery, no
    socket.

    Note it must be *disabled* providers, not an *empty* `providers` table:
    `app_data_root_no_providers` does not survive contact with `build_app`, which treats an
    empty table as a fresh install and re-seeds the three enabled builtins itself
    (`compose.py`: `if not provs.list_providers(): seed_builtin_providers(...)`).
    """
    yield from _app_handle_factory(qapp)


@pytest.fixture
def drain_task_runner_deliveries(qtbot: QtBot) -> Callable[[AppHandle], None]:
    """Hand `_drain_pending_task_runner_deliveries` to test modules as a fixture
    parameter, pre-bound to this test's own `qtbot` -- see that function's docstring for
    what it drains and why a test **must** call it itself, before its test function
    returns, rather than relying on `build_real_app`'s teardown to do it."""
    return functools.partial(_drain_pending_task_runner_deliveries, qtbot=qtbot)


@pytest.fixture
def dispatcher_shutdown_timeout_ms() -> int:
    """The millisecond timeout `_shutdown` itself uses for `AppHandle.shutdown()`, exposed
    so a test module that needs the same value (e.g. to call `handle.shutdown(...)` or
    `handle.run_dispatcher.shutdown(...)` directly) never hand-copies the literal -- a second
    copy could silently drift from the one `_shutdown` uses."""
    return _DISPATCHER_SHUTDOWN_TIMEOUT_MS


@pytest.fixture
def seed_setting() -> Callable[..., None]:
    """Hand `_seed_setting` to test modules as a fixture parameter instead of a cross-module
    import -- see the module docstring."""
    return _seed_setting


@pytest.fixture
def shutdown_handle() -> Callable[[AppHandle], None]:
    """Hand `_shutdown` to test modules as a fixture parameter instead of a cross-module
    import -- see the module docstring. `build_real_app`'s own teardown above calls
    `_shutdown` directly and keeps doing so; this fixture is for tests that build an
    `AppHandle` without going through `build_real_app`."""
    return _shutdown
