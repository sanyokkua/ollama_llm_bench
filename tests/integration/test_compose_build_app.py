"""Integration tests for the composition root, `build_app` (STORY-077-AC-1, -2, -3, -6,
-7, -8).

Exercises a *real* `build_app(*, app, loop) -> AppHandle` call against a real, isolated
SQLite database (schema applied and one enabled provider seeded by this file's own
fixtures, ahead of `build_app`'s own idempotent schema-check/seed calls -- STORY-078
owns those calls; this file's fixtures merely pre-seed so these STORY-077 tests don't
depend on STORY-078's abort/seed behaviour to pass), a real `QApplication`, and real
widgets -- the multi-module, real-local-resource shape the `testing-standard-pyqt` skill
and `testing.md` reserve for the integration tier.

**Filesystem isolation beyond the root `_isolate_filesystem` fixture.** The real,
non-injected `PlatformDetector` `build_app` constructs (`make_platform_detector()`) resolves
`<app-data>` from `Path.home()` on macOS and Windows, and only falls back to
`XDG_DATA_HOME` on Linux (`backend/platform/_internal/detector.py`). The root `conftest.py`'s
`_isolate_filesystem` fixture only redirects `XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`LOCALAPPDATA`
into `tmp_path` -- so on a macOS/Windows host it does *not* stop a real `build_app()` call
from resolving into this machine's actual user profile directory. `compose.py` is the only
call site in the whole codebase that constructs the real, non-injected
`InjectablePlatformDetector` this way. The `isolated_home` fixture below additionally
redirects `HOME`/`USERPROFILE` into `tmp_path` so every test in this file is safe on every
host platform, regardless of which OS branch `Path.home()` resolves through.
"""

from collections.abc import Callable, Generator
import functools
import gc
from pathlib import Path
import sqlite3
from typing import cast

import httpx
from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QStackedWidget, QTabWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_runnables import make_qt_task_runner
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.model_capabilities import (
    create_model_capabilities_store,
)
from ollama_llm_bench.backend.persistence.providers import (
    create_providers_store,
    seed_builtin_providers,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.backend.provider_anthropic.api import AnthropicClientCollaborators
from ollama_llm_bench.backend.provider_gemini.api import GeminiClientCollaborators
from ollama_llm_bench.backend.provider_openai_compatible.api import (
    OpenAICompatibleClientCollaborators,
)
from ollama_llm_bench.backend.readiness import ReadinessService, make_readiness_service
from ollama_llm_bench.compose import AppHandle, build_app
from ollama_llm_bench.ui.theme import ActiveThemeKind, ThemeManager, make_theme_manager

_DISPATCHER_SHUTDOWN_TIMEOUT_MS = 2000


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Disconnect every `ThemeManager` this file's `build_app` calls attached to
    `qapp.styleHints().colorSchemeChanged` -- nothing in production ever
    disconnects it (STORY-083, not this story, owns runtime theme re-application),
    so a `ThemeManager` built by one test here would otherwise stay connected and
    react to a *later, unrelated* test's own OS-colour-scheme simulation in the
    same session-scoped `qapp` (this contaminated
    `ui/theme/tests/test_theme_selection.py`'s own `test_explicit_override_ignores_
    live_os_change` before this fixture was added). Mirrors the identical cleanup
    `ui/theme/tests/test_theme_selection.py` and `tests/integration/
    test_theme_switching.py` already use for the same signal.
    """
    yield
    qapp.styleHints().colorSchemeChanged.disconnect()
    qapp.styleHints().unsetColorScheme()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` into `tmp_path` -- see the module docstring."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def seeded_app_data_root(isolated_home: Path) -> Path:
    """Pre-create the schema and one enabled builtin provider at the exact `<app-data>`
    path `build_app` itself will resolve and open (same detector, same environment)."""
    # Arrange
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    seed_builtin_providers(write_conn, lock)
    write_conn.close()
    return app_data_root


@pytest.fixture
def app_data_root_no_providers(isolated_home: Path) -> Path:
    """Pre-create the schema only -- zero providers seeded, at the exact `<app-data>` path
    `build_app` itself will resolve and open. Regression fixture for the STORY-077
    remediation's Fix 1: a fresh install (or every provider disabled) must not crash
    `build_app`."""
    # Arrange
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
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


@pytest.fixture
def build_real_app(
    qapp: QApplication, seeded_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Factory building a real `AppHandle` against the seeded, isolated app-data
    directory; every handle it built is torn down at the end of the test."""
    built: list[AppHandle] = []

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build

    for handle in built:
        _shutdown(handle)


def test_build_app_returns_frozen_app_handle_with_window_and_shutdown(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot
) -> None:
    """Proves: STORY-077-AC-1

    Given a constructed `QApplication`, when `build_app` is called, then it returns an
    `AppHandle` that is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)` carrying
    the main window and the raw resource handles (write connection/lock, `TaskRunner`,
    `RunDispatcher`, HTTP client, instance lock) STORY-080's shutdown sequence needs.
    """
    # Act
    handle = build_real_app()
    qtbot.addWidget(handle.window)

    # Assert -- carries the window and the shutdown-sequence resource handles.
    assert isinstance(handle, AppHandle)
    assert handle.window is not None
    handle_fields = set(AppHandle.__struct_fields__)
    assert handle_fields == {
        "window",
        "write_conn",
        "write_lock",
        "task_runner",
        "run_dispatcher",
        "http_client",
        "instance_lock",
        "loop",
        "flow",
    }

    # Assert -- frozen: setting an existing field raises.
    with pytest.raises(AttributeError):
        handle.loop = handle.loop  # type: ignore[misc]  # proving immutability, not a real mutation

    # Assert -- kw_only: a positional construction call is rejected.
    with pytest.raises(TypeError):
        AppHandle(handle.window)  # type: ignore[call-arg]  # proving kw_only, not a real construction

    # Assert -- gc=False: the struct instance is never tracked by the cyclic collector.
    assert gc.is_tracked(handle) is False


def test_build_app_is_synchronous_and_makes_no_network_call(
    seeded_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-077-AC-2

    Given `build_app` is called, when the object graph is constructed, then it issues no
    network call and returns before the deferred readiness probe runs. Every readiness
    probe necessarily issues at least one HTTP reachability request on the shared
    `httpx.Client`, so proving zero calls to `httpx.Client.send` during construction also
    proves no probe ran -- the window is never shown in this test, so the deferred tick
    that would otherwise trigger one (STORY-077-AC-6) never fires either.
    """
    # Arrange
    network_spy = mocker.patch.object(
        httpx.Client,
        "send",
        side_effect=AssertionError("no network call expected during build_app"),
    )

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert
    assert handle.window is not None
    network_spy.assert_not_called()

    # Cleanup
    _shutdown(handle)


def test_build_app_constructs_single_runner_writer_and_http_client(
    seeded_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-077-AC-3

    For every run of `build_app`, exactly one database write connection is opened,
    exactly one `TaskRunner` is constructed, and exactly one synchronous HTTP client is
    constructed -- and the one write connection and its lock are the same objects
    injected into all six per-aggregate persistence stores, and the one HTTP client is
    the same object injected into all three provider client-collaborator bundles.
    """
    # Arrange
    open_write_connection_spy = mocker.patch(
        "ollama_llm_bench.compose.open_write_connection", wraps=open_write_connection
    )
    make_qt_task_runner_spy = mocker.patch(
        "ollama_llm_bench.compose.make_qt_task_runner", wraps=make_qt_task_runner
    )
    runs_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_runs_store", wraps=create_runs_store
    )
    tasks_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_tasks_store", wraps=create_tasks_store
    )
    results_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_results_store", wraps=create_results_store
    )
    providers_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_providers_store", wraps=create_providers_store
    )
    capabilities_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_model_capabilities_store",
        wraps=create_model_capabilities_store,
    )
    app_settings_store_spy = mocker.patch(
        "ollama_llm_bench.compose.create_app_settings_store", wraps=create_app_settings_store
    )
    openai_collabs_spy = mocker.patch(
        "ollama_llm_bench.compose.OpenAICompatibleClientCollaborators",
        wraps=OpenAICompatibleClientCollaborators,
    )
    anthropic_collabs_spy = mocker.patch(
        "ollama_llm_bench.compose.AnthropicClientCollaborators", wraps=AnthropicClientCollaborators
    )
    gemini_collabs_spy = mocker.patch(
        "ollama_llm_bench.compose.GeminiClientCollaborators", wraps=GeminiClientCollaborators
    )

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert -- exactly one write connection and exactly one TaskRunner.
    open_write_connection_spy.assert_called_once()
    make_qt_task_runner_spy.assert_called_once()

    # Assert -- the same write connection/lock reached every one of the six stores.
    assert runs_store_spy.call_args.args[0] is handle.write_conn
    assert runs_store_spy.call_args.args[1] is handle.write_lock
    assert tasks_store_spy.call_args.args[0] is handle.write_conn
    assert tasks_store_spy.call_args.args[1] is handle.write_lock
    assert results_store_spy.call_args.args[0] is handle.write_conn
    assert results_store_spy.call_args.args[1] is handle.write_lock
    assert providers_store_spy.call_args.args[0] is handle.write_conn
    assert providers_store_spy.call_args.args[1] is handle.write_lock
    assert capabilities_store_spy.call_args.args[0] is handle.write_conn
    assert capabilities_store_spy.call_args.args[1] is handle.write_lock
    assert app_settings_store_spy.call_args.args[0] is handle.write_conn
    assert app_settings_store_spy.call_args.args[1] is handle.write_lock

    # Assert -- the one shared HTTP client reached all three provider collaborator bundles.
    assert openai_collabs_spy.call_args.kwargs["http_client"] is handle.http_client
    assert anthropic_collabs_spy.call_args.kwargs["http_client"] is handle.http_client
    assert gemini_collabs_spy.call_args.kwargs["http_client"] is handle.http_client

    # Cleanup
    _shutdown(handle)


def test_show_schedules_single_deferred_readiness_tick(
    seeded_app_data_root: Path, qapp: QApplication, qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-077-AC-6

    Given `build_app` has returned an `AppHandle` and no readiness probe ran during
    `build_app` itself (STORY-077-AC-2), when the main window is shown, then exactly one
    deferred tick fires and it triggers exactly one readiness probe -- the existing
    STORY-053 `MainWindowShell.showEvent` -> `QTimer.singleShot(0, ...)` ->
    `_on_shell_shown` -> `gateway.reprobe()` path, reached through the real gateway
    `build_app` injects; no new show hook is added or exercised here.
    """
    # Arrange
    captured_services: list[ReadinessService] = []

    def _capture_readiness_service(**kwargs: object) -> ReadinessService:
        service = make_readiness_service(**kwargs)  # type: ignore[arg-type]  # forwarding real build_app kwargs
        captured_services.append(service)
        return service

    mocker.patch(
        "ollama_llm_bench.compose.make_readiness_service", side_effect=_capture_readiness_service
    )
    handle = build_app(app=qapp, loop=QEventLoop())
    qtbot.addWidget(handle.window)
    assert len(captured_services) == 1
    probe_all_spy = mocker.patch.object(captured_services[0], "probe_all")

    # Act
    handle.window.show()
    qtbot.waitUntil(lambda: probe_all_spy.call_count >= 1, timeout=2000)

    # Assert
    probe_all_spy.assert_called_once()

    # Cleanup
    _shutdown(handle)


def test_build_app_applies_persisted_theme_before_window_shown(
    seeded_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-077-AC-7

    Given a persisted `ui.theme` setting (`"dark"`, which always resolves to the DARK
    container regardless of the host's OS colour scheme), when `build_app` wires the
    object graph, then it constructs the theme manager and applies the resolved theme to
    the `QApplication` before the main window is shown -- this test never calls
    `.show()`, so a stylesheet already present on `qapp` right after `build_app` returns
    can only have come from construction-time application.
    """
    # Arrange
    _seed_setting(seeded_app_data_root, key="ui.theme", value="dark")
    captured_managers: list[ThemeManager] = []

    def _capture_theme_manager(**kwargs: object) -> ThemeManager:
        manager = make_theme_manager(**kwargs)  # type: ignore[arg-type]  # forwarding real build_app kwargs
        captured_managers.append(manager)
        return manager

    mocker.patch("ollama_llm_bench.compose.make_theme_manager", side_effect=_capture_theme_manager)
    style_before = qapp.styleSheet()

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert
    assert len(captured_managers) == 1
    assert captured_managers[0].active_theme_kind is ActiveThemeKind.DARK
    assert qapp.styleSheet() != style_before
    assert qapp.styleSheet() != ""

    # Cleanup
    _shutdown(handle)


def test_build_app_injects_settings_and_about_callbacks(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-077-AC-8

    Given `build_app` has wired the main window, when the Settings and About menu-bar
    actions are clicked, then each reaches a real, non-`None` callback that calls through
    to `make_settings_dialog`/`make_about_dialog` exactly once -- proving the callbacks
    injected into the main-window controller are live, not the unwired `None` defaults.
    `make_settings_dialog`/`make_about_dialog` are patched to a non-blocking double so
    clicking never opens a real modal `.exec()` loop in the test process.
    """
    # Arrange
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    settings_dialog = mocker.Mock()
    about_dialog = mocker.Mock()
    make_settings_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_settings_dialog", return_value=settings_dialog
    )
    make_about_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_about_dialog", return_value=about_dialog
    )
    settings_button = cast("QPushButton", handle.window.findChild(QPushButton, "settings_action"))
    about_button = cast("QPushButton", handle.window.findChild(QPushButton, "about_action"))
    assert settings_button is not None
    assert about_button is not None

    # Act
    qtbot.mouseClick(settings_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    qtbot.mouseClick(about_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert
    make_settings_dialog_spy.assert_called_once()
    settings_dialog.exec.assert_called_once()
    make_about_dialog_spy.assert_called_once()
    about_dialog.exec.assert_called_once()


def test_build_app_succeeds_with_zero_enabled_providers(
    app_data_root_no_providers: Path, qapp: QApplication
) -> None:
    """Regression coverage for the STORY-077 remediation's Fix 1.

    A fresh install (or a database where every provider has been disabled) has no
    enabled provider to back the embedding service. `build_app` must still return a real
    `AppHandle` with a working, navigable main window instead of raising -- it never
    substitutes an arbitrary enabled provider the user did not choose for the embedding
    selection, and it never crashes startup when none is available.
    """
    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert
    try:
        assert isinstance(handle, AppHandle)
        assert handle.window is not None
    finally:
        _shutdown(handle)


def test_workspace_switch_reuses_pages_and_never_duplicates_the_left_panel(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot
) -> None:
    """Regression coverage for the STORY-077 remediation's workspace/tab wiring.

    `compose.py` builds exactly one `benchmark_left_panel` tab widget with two tabs, "New
    Benchmark" and "Resume". Clicking the real workspace switcher control to Task Editor
    and back to Benchmark changes the container's currently-displayed page each time, the
    `QStackedWidget` never grows past its two pages (no duplicate construction on repeated
    switches), and the same Python widget instances are reused across switches rather than
    rebuilt.
    """
    # Arrange
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    left_panel = cast("QTabWidget | None", handle.window.findChild(QTabWidget, "benchmark_left_panel"))  # fmt: skip
    assert left_panel is not None
    assert left_panel.count() == 2  # noqa: PLR2004  # the two tabs this AC counts
    assert left_panel.tabText(0) == "New Benchmark"
    assert left_panel.tabText(1) == "Resume"
    container = cast("QStackedWidget | None", handle.window.findChild(QStackedWidget, "workspace_region"))  # fmt: skip
    assert container is not None
    assert container.count() == 2  # noqa: PLR2004  # Benchmark + Task Editor pages
    benchmark_page = container.currentWidget()
    task_editor_button = cast("QPushButton", handle.window.findChild(QPushButton, "workspace_switcher_task_editor"))  # fmt: skip
    benchmark_button = cast("QPushButton", handle.window.findChild(QPushButton, "workspace_switcher_benchmark"))  # fmt: skip
    assert task_editor_button is not None
    assert benchmark_button is not None

    # Act -- switch to Task Editor
    qtbot.mouseClick(task_editor_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert -- the container's current page changed; no page was added
    assert container.count() == 2  # noqa: PLR2004  # still exactly Benchmark + Task Editor
    task_editor_page = container.currentWidget()
    assert task_editor_page is not benchmark_page

    # Act -- switch back to Benchmark
    qtbot.mouseClick(benchmark_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert -- the same Benchmark page instance reappears; still exactly two pages
    assert container.count() == 2  # noqa: PLR2004  # still exactly Benchmark + Task Editor
    assert container.currentWidget() is benchmark_page

    # Cleanup -- `build_real_app`'s own fixture teardown already calls `_shutdown(handle)`
    # for every handle it built; a second call here would double-checkpoint the write
    # connection after AppHandle.shutdown()'s new step 4 has already closed it (STORY-080).


def test_app_handle_shutdown_closes_http_client_and_write_connection(
    seeded_app_data_root: Path, qapp: QApplication
) -> None:
    """Proves: STORY-077-AC-1

    `AppHandle.shutdown()` closes the shared `httpx.Client` and checkpoints-then-closes
    the SQLite write connection -- steps 3-4 of the spec's six-step ordered shutdown, the
    two resources this composition-root struct owns outright, proving `AppHandle` carries
    a real shutdown handle rather than just raw, unused fields.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.close()
    handle.run_dispatcher.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)

    # Act
    handle.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)

    # Assert
    assert handle.http_client.is_closed
    with pytest.raises(sqlite3.ProgrammingError):
        handle.write_conn.execute("SELECT 1")
