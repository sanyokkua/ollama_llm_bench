"""Fixtures for the end-to-end smoke tier: an isolated, fully offline composed app.

`tests/integration/conftest.py` holds an equivalent rig, but a conftest applies only
to descendants of its own directory and there are no `__init__.py` files under
`tests/` to import a shared helper through, so the rig is restated here rather than
shared -- a deliberate duplication, not an oversight.
"""

from collections.abc import Callable, Generator, Iterable
import functools
from pathlib import Path
from typing import Final, cast
import warnings

import msgspec
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QWidget,
)
import pytest
from pytestqt.qtbot import QtBot
import shiboken6

from ollama_llm_bench.adapters.clipboard import make_clipboard
from ollama_llm_bench.adapters.file_system_actions import make_file_system_actions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
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
from ollama_llm_bench.ui.settings_dialog import SettingsDialogCollaborators, make_settings_dialog
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway

_SHUTDOWN_TIMEOUT_MS = 2000
_GEOMETRY_DEBOUNCE_DRAIN_MS = 300
_NOT_READY_MODAL_DISMISS_DELAY_MS = 100


def _disconnect_and_discard_warning(signal: SignalInstance) -> None:
    """Disconnect every slot from `signal`, discarding whatever warning PySide6 emits.

    `SignalInstance.disconnect()` does not raise when nothing is connected -- it emits a
    Python-level `RuntimeWarning` straight from the C++ binding and returns normally.
    `warnings.catch_warnings(record=True)` combined with `simplefilter("always")` captures
    that warning into a local list this function never inspects, so it never escapes to the
    caller or to pytest's warning capture.
    """
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        signal.disconnect()


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Drop the `colorSchemeChanged` connection each `build_app` leaves on the shared qapp.

    `ThemeManager` connects to the session-scoped `qapp.styleHints()` and production
    never disconnects it, so without this every built app leaks a connection into the
    next test.
    """
    yield
    _disconnect_and_discard_warning(qapp.styleHints().colorSchemeChanged)
    qapp.styleHints().unsetColorScheme()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the resolved app-data root into `tmp_path`.

    The root `_isolate_filesystem` fixture sets only the XDG/LOCALAPPDATA variables.
    On macOS the platform detector ignores those and reads `Path.home()`, so `HOME`
    and `USERPROFILE` are the only cross-platform lever.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _create_app_data_root_with_schema() -> Path:
    """Create, and apply the schema to, the database at the exact `<app-data>` path
    `build_app` itself will resolve and open (same detector, same environment).

    Returns the app-data root with the write connection already closed, so the caller
    can reopen it to seed rows before `build_app` opens its own connection.
    """
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.close()
    return app_data_root


@pytest.fixture
def offline_app_data_root(isolated_home: Path) -> Path:
    """Seed the app-data directory, then disable every provider so no probe dials out.

    Leaving the catalog empty does not work: `build_app` re-seeds the builtins whenever
    it finds `providers` empty, and those point at localhost:11434 / localhost:1234. On a
    developer machine running Ollama or LM Studio that is real network I/O from a test
    that looks clean on an offline CI runner. Seeding the rows first, then disabling every
    one, means the catalog is non-empty (so `build_app`'s fresh-install re-seed never
    fires) and nothing enabled is left for the readiness probe to dial.
    """
    app_data_root = _create_app_data_root_with_schema()
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    seed_builtin_providers(write_conn, lock)
    store = create_providers_store(write_conn, lock, functools.partial(open_read_connection, db_path))  # fmt: skip
    store.replace_providers(
        tuple(msgspec.structs.replace(config, enabled=False) for config in store.list_providers())
    )
    write_conn.close()
    return app_data_root


def _dismiss_message_box(modal: QMessageBox) -> None:
    """Hide `modal` in a way that always removes it from Qt's modal-widget stack.

    Identical mechanics to `tests/integration/conftest.py`'s `_dismiss_message_box` (restated
    here, not imported -- see this module's own docstring on why the rig is duplicated).
    `QDialog.exec()` (which `QMessageBox.critical()` calls internally) shows the dialog, which
    is what pushes it onto `QApplication.activeModalWidget()`'s stack; a plain `close()`/
    `hide()` after the nested loop is already running does not reliably pop that stack back
    off, and a stale entry left behind aborts a later, unrelated test's own modal lookup with a
    fatal `QTEST_ASSERT` inside Qt. Restoring `WA_ShowModal` immediately before hiding makes Qt
    run `leaveModal` and clears the stack properly.
    """
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _DismissReadinessModalOnShow(QObject):
    """App-wide event filter that auto-dismisses the real NOT_READY `QMessageBox` the instant
    it is shown, wherever in a test's execution it happens to appear.

    Restated from `tests/integration/conftest.py`'s identical class -- see this module's own
    docstring for why the rig is duplicated rather than shared. `offline_app_data_root`
    disables every provider so the fixture never dials a real network endpoint, but a fully
    offline application with zero enabled providers is genuinely `NOT_READY`
    (`08_Cross_Cutting/08-M_app_lifecycle.md` §5), and production surfaces that state with a
    blocking `QMessageBox.critical(...)` modal the first time the deferred,
    `QTimer.singleShot(0, ...)`-scheduled startup readiness tick resolves it
    (`main_window_shown_readiness_probe_scheduled` -> `QtNotificationService._show_modal` ->
    `.exec()`).

    **Why a one-shot timer armed once, right after `build_app()` returns, is not enough.** That
    0ms readiness timer is armed the moment `window.show()` fires its `showEvent`, but stays
    *pending*, undelivered, until something next pumps the Qt event loop -- which happens only
    once a test starts genuinely waiting on real application state (e.g. the status-bar health
    dot settling). A dismiss timer armed once, at a fixed short delay after build time, can
    easily fire before the modal exists yet if that first real event-loop pump happens later
    than the delay -- the timer then finds nothing to dismiss, and the modal opens afterwards
    into a nested loop nothing will ever unwind, hanging the suite. An event filter watching
    for the moment Qt actually shows a `QMessageBox` is the only thing that reliably catches it
    regardless of when the pump happens.

    **Why the dismiss is scheduled on a delay rather than done synchronously inside the Show
    event.** `QDialog.exec()`'s sequence is `show()` (which is what dispatches the `Show` event
    this filter reacts to) followed by constructing and running its own nested `QEventLoop` --
    that loop object does not exist yet while `show()` is still on the call stack, so hiding
    the widget from directly inside the event filter has nothing to make the nested loop
    return; the loop would still block forever once `exec()` reaches it. Coming back a little
    later, once the nested loop is actually running, is what lets the dismissal take effect.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(
                _NOT_READY_MODAL_DISMISS_DELAY_MS, functools.partial(_dismiss_message_box, watched)
            )
        return False


@pytest.fixture
def build_smoke_app(
    qapp: QApplication, offline_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Build the real composed app against the offline app-data root.

    Installs `_DismissReadinessModalOnShow` on `qapp` for the fixture's lifetime: every app
    built here is fully offline with no enabled provider (see `offline_app_data_root`), so its
    deferred startup readiness tick genuinely resolves NOT_READY and production genuinely opens
    a real blocking `QMessageBox.critical` modal -- the filter catches and dismisses it
    whenever it actually appears, rather than guessing when.
    """
    built: list[AppHandle] = []
    dismiss_not_ready_modal = _DismissReadinessModalOnShow()
    qapp.installEventFilter(dismiss_not_ready_modal)

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build
    qapp.removeEventFilter(dismiss_not_ready_modal)
    for handle in built:
        # `shiboken6.isValid` guards a widget a consuming fixture already fully tore down
        # (e.g. `mounted_app_surfaces` calling `shutdown_handle`, whose own `qtbot.wait` for
        # the geometry-debounce drain flushes pytest-qt's own `_close_widgets` deleteLater --
        # pytest-qt's `pytest_runtest_teardown` wrapper always closes+deleteLater()s every
        # `qtbot.addWidget`-registered widget *before* any fixture finalizer, including this
        # one, runs). Calling `.close()` on an already-C++-deleted widget raises
        # `RuntimeError: Internal C++ object ... already deleted` -- this loop's job is a
        # best-effort close of whatever it built, not a second mandatory shutdown step, so a
        # widget already gone is skipped rather than treated as a failure.
        if shiboken6.isValid(handle.window):
            handle.window.close()


@pytest.fixture
def shutdown_handle(qtbot: QtBot) -> Callable[[AppHandle], None]:
    """Run the ordered shutdown the way production does -- window first, then handle.

    `AppHandle.shutdown` is not idempotent -- a second call raises `sqlite3.ProgrammingError`
    on the already-closed connection. `build_smoke_app`'s finalizer therefore only closes the
    window; a test calls this exactly once per handle.

    **Drains the geometry debounce timer before closing the database.** `window.close()`
    routes through `CloseHandler` -> `_on_confirmed_quit`, which flushes the pending window
    geometry synchronously and then calls `shell.force_close()`. That second, real `close()`
    hides the window, which -- observed empirically under the offscreen Qt platform plugin --
    re-fires a resize/move event that re-arms `DebouncedGeometryWriter`'s single-shot 200ms
    timer with a fresh pending write. Left undrained, that timer only fires once *something
    else* next pumps the Qt event loop (typically the next test), by which point this
    fixture has already closed the write connection underneath it, crashing with
    `sqlite3.ProgrammingError: Cannot operate on a closed database` in a later, unrelated
    test. `qtbot.wait` past the 200ms debounce window lets that trailing write land while
    the connection is still open, so the shutdown below closes it cleanly instead.

    By the time a test calls this, it has already waited for the status-bar health dot to
    settle into NOT_READY (see `_wait_for_not_ready_health_dot` in the test module), so the
    real modal has already appeared and been dismissed by `build_smoke_app`'s installed
    `_DismissReadinessModalOnShow` filter -- this fixture no longer needs its own dismiss
    timer.

    **Guards its own `.close()` and always runs `handle.shutdown(...)`.** pytest-qt's own
    `pytest_runtest_teardown` hook closes and `deleteLater()`s every `qtbot.addWidget`-registered
    widget *before* any fixture's own teardown code runs. A caller that registered
    `handle.window` via `qtbot.addWidget` (e.g. `mounted_app_surfaces`) therefore may already
    have a C++-deleted window by the time this function runs, and `handle.window.close()` on an
    already-deleted widget raises `RuntimeError: Internal C++ object ... already deleted`. Left
    unguarded, that exception would abort this function before it ever reaches
    `handle.shutdown(...)` -- the actual root-cause fix for the non-daemon dispatcher-thread
    hang (see the docstring on `mounted_app_surfaces`) -- silently reopening that hole. The
    `shiboken6.isValid` guard skips the redundant close cleanly instead of raising, and the
    `try/finally` guarantees `handle.shutdown(...)` always runs, whether or not `.close()` ran.
    """

    def _shutdown(handle: AppHandle) -> None:
        try:
            if shiboken6.isValid(handle.window):
                handle.window.close()
                qtbot.wait(_GEOMETRY_DEBOUNCE_DRAIN_MS)
        finally:
            handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    return _shutdown


_INTERACTIVE_TYPES: tuple[type[QWidget], ...] = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)
_COMPOSITE_TYPES: tuple[type[QWidget], ...] = (QComboBox, QAbstractItemView, QAbstractSpinBox)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    Restated from tests/integration/test_a11y_names_shell.py:41-56 (the established,
    deliberate per-tier restatement convention -- no shared tests/support/ module exists).
    """
    parent = cast("QObject | None", widget.parent())
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = cast("QObject | None", parent.parent())
    return False


@pytest.fixture
def interactive_descendants() -> Callable[[QWidget], list[QWidget]]:
    def _walk(root: QWidget) -> list[QWidget]:
        descendants = cast("Iterable[QWidget]", root.findChildren(QWidget))
        found = [
            w
            for w in descendants
            if isinstance(w, _INTERACTIVE_TYPES) and not _has_composite_ancestor(w)
        ]
        if isinstance(root, _INTERACTIVE_TYPES):
            found.append(root)
        return found

    return _walk


def _build_settings_dialog(*, qtbot: QtBot) -> QDialog:
    """Construct the Settings dialog standalone, shown but never exec()'d.

    ``compose.py`` builds this dialog lazily inside ``_open_settings()`` and
    calls ``.exec()``, which would block the whole suite. Building it here
    instead means the screenshot harness never opens a real modal.
    """
    collaborators = SettingsDialogCollaborators(
        gateway=FakeSettingsGateway(),
        event_bus=make_qt_event_bus_deliverer(),
        native_pickers=FakeNativePickers(),
        clipboard=make_clipboard(),
        file_system_actions=make_file_system_actions(),
        notifications=FakeNotificationService(),
    )
    dialog = make_settings_dialog(collaborators=collaborators)
    qtbot.addWidget(dialog)
    dialog.resize(*_DIALOG_SIZE)
    dialog.show()
    qtbot.wait(0)
    return dialog


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
def mounted_app_surfaces(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> Generator[list[QWidget]]:
    """Every top-level surface the accessibility-floor checks (AC-2/3/4) must walk.

    The main window (built via build_smoke_app -- eagerly contains every workspace tab per
    compose.py's construction order), the Settings dialog, and the seven shared modal
    dialogs, all shown but never exec()'d.

    **Runs `shutdown_handle` at teardown.** `build_app` starts the non-daemon
    `pipeline-dispatcher` thread (DD-38) as a side effect of construction; that thread parks on
    `queue.Queue.get()` until `AppHandle.shutdown` enqueues its stop sentinel and joins it.
    `build_smoke_app`'s own finalizer only closes the window (see its docstring), so a fixture
    that never calls `shutdown_handle` leaves that thread running forever -- CPython's
    interpreter-shutdown sequence (`Py_Finalize`) blocks joining every live non-daemon thread,
    so the whole `pytest` process hangs after printing its summary rather than exiting. Every
    other fixture in this tier that builds an `AppHandle` via `build_smoke_app`
    (`test_launch_idle_shutdown_smoke.py`'s three tests) already calls `handle.shutdown`
    explicitly for the same reason -- `test_icon_only_registry_conformance.py`'s `registry_app`
    builds its `AppHandle` via `build_app` directly, not `build_smoke_app`, but calls
    `handle.shutdown` for the identical reason.
    """
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=5000)

    settings_dialog = _build_settings_dialog(qtbot=qtbot)
    common_dialogs = _build_common_dialogs(qtbot=qtbot)

    yield [handle.window, settings_dialog, *common_dialogs.values()]

    shutdown_handle(handle)
