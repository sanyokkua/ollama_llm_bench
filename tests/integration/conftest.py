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

**No cross-module import.** `_seed_setting`, `_shutdown`, and `_DISPATCHER_SHUTDOWN_TIMEOUT_MS`
stay module-private here and are handed to test modules only through the `seed_setting`,
`shutdown_handle`, and `dispatcher_shutdown_timeout_ms` fixtures below -- pytest auto-injects
fixtures by name, so no test module needs `from tests.integration.conftest import ...`. There
are zero `__init__.py` files anywhere under `tests/`; adding one just to support that kind of
import would be a wider, unrelated change to how this repository's test tree is packaged.
"""

from collections.abc import Callable, Generator
import functools
from pathlib import Path
import warnings

import msgspec
from PySide6.QtCore import QEventLoop, SignalInstance
from PySide6.QtWidgets import QApplication
import pytest
from pytestqt.qtbot import QtBot

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
from ollama_llm_bench.compose import AppHandle, build_app

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
