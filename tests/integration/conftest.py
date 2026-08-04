"""Shared rig for `tests/integration/` tests that build the real composed application.

Moved here from `test_compose_build_app.py` so the theme-reapply and menu-dialog suites
(STORY-083) share one copy instead of triplicating it. The autouse
`_disconnect_os_color_scheme_signal` fixture is load-bearing: every `build_app` constructs a
`ThemeManager` that connects to the session-scoped `qapp.styleHints().colorSchemeChanged`,
and `pytest-randomly` reorders tests, so a leaked connection corrupts a later test.
"""

from collections.abc import Callable, Generator
import functools
from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

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
