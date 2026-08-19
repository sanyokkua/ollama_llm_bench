"""Fixtures for the opt-in live tier: a real composed app against a real local server.

Authority: ADR-0011 Decision outcome §1. Nothing in
``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`` describes a live
tier -- §12 fixes CI as fully offline with no scheduled workflow (DD-36), and §6a fixes the
``LLMClient`` contract suite's real leg to the wire stub. This tier is a separate surface
that leaves both untouched: it is selected only when ``OLLAMA_BENCH_LIVE_LOCAL_TESTS=1`` and
carries the ``live_local`` marker, which ``pyproject.toml``'s ``addopts`` deselects from every
bare ``pytest`` invocation.

``tests/e2e/conftest.py`` holds an equivalent offline rig, but a conftest applies only to
descendants of its own directory and there are no ``__init__.py`` files under ``tests/`` to
import a shared helper through, so the rig is restated here -- a deliberate duplication
matching what ``tests/e2e/`` and ``tests/integration/`` already do.

Everything the two provider test modules need is exposed as a **fixture**. They must never do
``from conftest import ...``: pytest registers a plain ``conftest.py`` in ``sys.modules`` under
the bare name ``conftest``, so with several conftests collected the name silently resolves to
whichever was imported last -- returning another directory's symbols without raising
(STORY-086).
"""

from collections.abc import Callable, Generator, Mapping
import functools
import os
from pathlib import Path
import socket
import sqlite3
import threading
from typing import Final, cast
from urllib.parse import urlparse
import warnings

import httpx
import msgspec
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
import pytest
from pytestqt.qtbot import QtBot
import shiboken6

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.domain import (
    ModelDescriptor,
    ProviderConfig,
    ProviderIdStr,
    ProviderType,
    ResultStatus,
    RunMode,
    RunStartRequest,
    RunStatus,
)
from ollama_llm_bench.backend.errors import AppError
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
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.backend.provider_openai_compatible.api import (
    LLMClient,
    OpenAICompatibleClientCollaborators,
    make_openai_client,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.stores.inference_activity import make_inference_activity_store
from ollama_llm_bench.compose import AppHandle, build_app
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget

OPT_IN_ENV_VAR: Final[str] = "OLLAMA_BENCH_LIVE_LOCAL_TESTS"
"""Set this to ``OPT_IN_ENABLED_VALUE`` to run the tier. Named to match the ``live_local``
marker and to stay unmistakably distinct from STORY-094's packaging variable."""

OPT_IN_ENABLED_VALUE: Final[str] = "1"

REACHABILITY_TIMEOUT_S: Final[float] = 2.0
"""The bounded connection timeout ADR-0011 requires: an absent server must skip, never hang."""

OLLAMA_BASE_URL: Final[str] = "http://localhost:11434/v1"
LMSTUDIO_BASE_URL: Final[str] = "http://localhost:1234/v1"
"""The two built-in local providers' seeded base URLs, verified against
``_BUILTIN_PROVIDER_SEEDS`` in ``backend/persistence/providers/_internal/store_impl.py``
(``provider_order`` 0 and 1)."""

LIVE_PROVIDER_ORDER_BY_BASE_URL: Final[dict[str, int]] = {
    OLLAMA_BASE_URL: 0,
    LMSTUDIO_BASE_URL: 1,
}
"""``seed_builtin_providers`` inserts Ollama/LM Studio/llama.cpp at ``provider_order`` 0/1/2
with a fresh UUID on each call, so the order column is the only stable handle on a row."""

_NO_MODELS_GUIDANCE: Final[dict[str, str]] = {
    OLLAMA_BASE_URL: (
        "Ollama is running at http://localhost:11434 but its /v1/models catalog is empty -- "
        "run `ollama pull <model>` (e.g. `ollama pull llama3.2:1b`) and re-run this tier"
    ),
    LMSTUDIO_BASE_URL: (
        "LM Studio is running at http://localhost:1234 but its /v1/models catalog is empty -- "
        "open its Developer tab, load a model, and leave the local server running"
    ),
}
"""Skip text an operator can act on without opening this file."""

PROBE_TIMEOUT_MS: Final[int] = 5_000
"""Bounds this tier's own discovery client only (connect + ``GET /v1/models``). It does NOT
bound the benchmark run -- that goes through the client ``build_app`` constructs, and its real
bound is ``RUN_TIMEOUT_MS`` below."""

READINESS_TIMEOUT_MS: Final[int] = 30_000
RUN_TIMEOUT_MS: Final[int] = 300_000
"""A real model is far slower than the wire stub's canned bytes; STORY-085's 30s ceiling is not
enough for a cold first token on a freshly loaded model."""

SHUTDOWN_TIMEOUT_MS: Final[int] = 30_000
"""Bounds `handle.shutdown()`'s dispatcher-thread join only -- `RUN_TIMEOUT_MS` above already
bounds the run itself. This is deliberately far above the 2_000ms this tier copied verbatim
from the offline `tests/e2e/` tier, which never runs a real inference call and so never blocks
the dispatcher thread mid-`chat_stream`.

`OpenAICompatibleClientSettings.hard_cancel_max_ms` (`provider_openai_compatible/models.py`)
documents a 2_000ms *intended* hard-cancel budget, but `CancellationToken.__init__`'s own
docstring says enforcing it "belongs to a later dispatcher story" -- today a hard cancel only
closes the raw stream via `add_hard_cancel_hook` and relies on the OS to unblock whatever
socket read the dispatcher thread is parked in, which is platform-dependent and itself
unbounded in the worst case. 2_000ms is therefore not a safety margin over that at all: on the
`RUN_TIMEOUT_MS` failure path (a real model that never produces a token), the dispatcher thread
can still be blocked in a bare socket read with nothing to unblock it until the close()
propagates. 30_000ms gives roughly 15x headroom over the documented-but-unenforced 2_000ms
bound while staying two orders of magnitude below `RUN_TIMEOUT_MS`, so a merely-slow shutdown
still finishes inside this bound. A shutdown that is genuinely stuck past this bound is not
masked by a silent `Thread.join` timeout -- it is caught immediately below by
`_assert_dispatcher_thread_stopped`, which fails the test loudly instead of letting
`Py_Finalize` hang the process forever after the summary prints."""

GEOMETRY_DEBOUNCE_DRAIN_MS: Final[int] = 300
MODAL_DISMISS_DELAY_MS: Final[int] = 100
WINDOW_VISIBLE_TIMEOUT_MS: Final[int] = 5_000

_DISPATCHER_THREAD_NAME: Final[str] = "pipeline-dispatcher"
"""Verified against `_DISPATCHER_THREAD_NAME` in
`adapters/qt_benchmark_flow/_internal/dispatcher_thread.py:25` -- the non-daemon thread
`AppHandle.shutdown` must join before this fixture's caller returns."""

_CHECKING_HEALTH_LABEL: Final[str] = "Checking"
"""The status-bar health dot's in-flight label; anything else means readiness settled."""

_DISCOVERY_PROVIDER_ID: Final[ProviderIdStr] = "00000000-0000-4000-8000-000000000000"
"""The throwaway id on the ``ProviderConfig`` this tier's own probe/discovery client is built
from. That client never touches the catalog -- it exists only to answer "is there a server and
what models does it have?" before the app is built -- so it needs no persisted row."""

_NO_RUN_CREATED_SENTINEL: Final[int] = 0
"""``BenchmarkFlowApi.start`` returns this instead of a run id when it refuses the request."""

_THIS_DIR: Final[Path] = Path(__file__).parent
"""This conftest's own directory, used by ``pytest_collection_modifyitems`` below to scope the
auto-applied ``live_local`` marker to items collected under here and nowhere else."""

TINY_TASK_FILE_BODY: Final[str] = """schema_version: 1
tasks:
  - task_id: live-smoke-1
    question: Reply with the single word OK.
    golden_answer: OK
"""


def live_local_opt_in_enabled(environ: Mapping[str, str]) -> bool:
    """Return whether the tier's opt-in variable is set to its enabling value.

    Takes the environment as an argument (rather than reading ``os.environ``) so the
    offline gating test in ``tests/unit/`` can exercise both branches without mutating
    process state.
    """
    return environ.get(OPT_IN_ENV_VAR) == OPT_IN_ENABLED_VALUE


def server_reachable(base_url: str, *, timeout_s: float = REACHABILITY_TIMEOUT_S) -> bool:
    """Return whether a TCP connection to ``base_url``'s host:port succeeds within the bound.

    A plain socket connect, not an HTTP request: it is the cheapest thing that distinguishes
    "no server here" from "server here but slow", and it cannot hang past ``timeout_s``.
    Never raises -- every failure mode (refused, unresolvable host, timed out) is a ``False``.
    """
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _lookup_known_base_url[T](mapping: Mapping[str, T], base_url: str, *, mapping_name: str) -> T:
    """Look up ``base_url`` in one of this tier's ``{OLLAMA,LMSTUDIO}_BASE_URL``-keyed maps.

    Both ``ollama_base_url`` and ``lmstudio_base_url`` are the only fixtures this tier exposes
    today, so every real caller hits the two known keys. This exists so a future third local
    provider fixture (llama.cpp is already seeded at ``provider_order`` 2 and one line away)
    that gets added to one map and not the other fails with a message naming exactly which map
    is missing the entry, instead of a bare ``KeyError`` with no context.

    Raises:
        KeyError: ``base_url`` is not a key of ``mapping``.
    """
    try:
        return mapping[base_url]
    except KeyError as exc:
        raise KeyError(
            f"{base_url!r} is not a known live-local base URL in {mapping_name} -- extend "
            "it for any newly seeded local provider (e.g. llama.cpp)"
        ) from exc


@pytest.fixture(autouse=True)
def _require_live_local_opt_in() -> None:
    """Skip every test in this directory unless the opt-in variable is set.

    A fixture, deliberately -- not ``collect_ignore`` and not a module-level skip. Both of
    those remove the node IDs from ``pytest --collect-only``, which is how
    ``scripts/trace.py`` builds the acceptance-criterion-to-test index; the tests would then
    have no proving test on record and ``just trace-check`` would fail the moment STORY-086
    is marked ``done``. Skipping at setup keeps the nodes collected and simply does not run
    them.
    """
    if not live_local_opt_in_enabled(os.environ):
        pytest.skip(f"{OPT_IN_ENV_VAR} is not set to {OPT_IN_ENABLED_VALUE!r}")


@pytest.fixture
def ollama_base_url() -> str:
    """Ollama's seeded local base URL, handed to tests as a fixture so no test module ever
    needs to import from this conftest."""
    return OLLAMA_BASE_URL


@pytest.fixture
def lmstudio_base_url() -> str:
    """LM Studio's seeded local base URL. See ``ollama_base_url``."""
    return LMSTUDIO_BASE_URL


class LiveAppRig(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """A built live app plus the provider id its enabled row was assigned."""

    handle: AppHandle
    provider_id: ProviderIdStr


class LiveSmokeOutcome(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The four facts AC-1 and AC-2 assert, in one comparable value.

    Deliberately normalised (``discovered_any: bool``, not a model count) so a test can assert
    the whole outcome in a single equality against ``expected_live_smoke_outcome`` -- one
    logical assertion, and a failure prints a full struct diff naming exactly which of the four
    facts broke.
    """

    reachable: bool
    discovered_any: bool
    run_status: RunStatus
    first_result_status: ResultStatus


def _disconnect_and_discard_warning(signal: SignalInstance) -> None:
    """Disconnect every slot from ``signal``, discarding whatever warning PySide6 emits.

    ``SignalInstance.disconnect()`` does not raise when nothing is connected -- it emits a
    Python-level ``RuntimeWarning`` straight from the C++ binding and returns normally.
    ``warnings.catch_warnings(record=True)`` combined with ``simplefilter("always")`` captures
    that warning into a local list this function never inspects, so it never escapes to the
    caller or to pytest's warning capture.

    Restated from ``tests/e2e/conftest.py``; see this module's own docstring on the duplication.
    """
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        signal.disconnect()


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Drop the ``colorSchemeChanged`` connection each ``build_app`` leaves on the shared qapp.

    ``ThemeManager`` connects to the session-scoped ``qapp.styleHints()`` and production never
    disconnects it, so without this every built app leaks a connection into the next test.
    """
    yield
    _disconnect_and_discard_warning(qapp.styleHints().colorSchemeChanged)
    qapp.styleHints().unsetColorScheme()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the resolved app-data root into ``tmp_path``.

    The root ``_isolate_filesystem`` fixture sets only the XDG/LOCALAPPDATA variables. On macOS
    the platform detector ignores those and reads ``Path.home()``, so ``HOME`` and
    ``USERPROFILE`` are the only cross-platform lever.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _create_app_data_root_with_schema() -> Path:
    """Create, and apply the schema to, the database at the exact ``<app-data>`` path
    ``build_app`` itself will resolve and open (same detector, same environment).

    Returns the app-data root with the write connection already closed, so the caller can
    reopen it to seed rows before ``build_app`` opens its own connection.
    """
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.close()
    return app_data_root


def _seed_single_live_provider(*, base_url: str, model_name: str) -> ProviderIdStr:
    """Enable exactly the built-in row seeded at ``base_url`` and disable the other two.

    Leaving the catalog empty does not work: ``build_app`` re-seeds the builtins whenever it
    finds ``providers`` empty. Seeding first and then rewriting keeps the catalog non-empty, so
    the re-seed never fires and the startup readiness probe dials one server and no other.

    Closes its own write connection before returning. SQLite here is single-writer and
    ``build_app`` opens its own connection to the same file, so this seeding connection must
    not outlive the call.

    Args:
        base_url: One of ``OLLAMA_BASE_URL`` / ``LMSTUDIO_BASE_URL``; selects the row to enable
            by its seeded ``provider_order``, the only stable handle on a freshly-UUID'd row.
        model_name: The live model discovered on that server, seeded into ``default_models`` so
            the app's model pickers need no discovery call of their own.

    Returns:
        The ``provider_id`` the store assigned to the enabled row.
    """
    live_order = _lookup_known_base_url(
        LIVE_PROVIDER_ORDER_BY_BASE_URL, base_url, mapping_name="LIVE_PROVIDER_ORDER_BY_BASE_URL"
    )
    app_data_root = _create_app_data_root_with_schema()
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    seed_builtin_providers(write_conn, lock)
    store = create_providers_store(write_conn, lock, functools.partial(open_read_connection, db_path))  # fmt: skip
    store.replace_providers(
        tuple(
            msgspec.structs.replace(
                config,
                enabled=config.provider_order == live_order,
                default_models=(model_name,) if config.provider_order == live_order else (),
            )
            for config in store.list_providers()
        )
    )
    provider_id = next(
        config.provider_id
        for config in store.list_providers()
        if config.provider_order == live_order
    )
    write_conn.close()
    return provider_id


def _dismiss_message_box(modal: QMessageBox) -> None:
    """Hide ``modal`` in a way that always removes it from Qt's modal-widget stack.

    Restated verbatim from ``tests/e2e/conftest.py``. ``QDialog.exec()`` (which
    ``QMessageBox.critical()`` calls internally) shows the dialog, which is what pushes it onto
    ``QApplication.activeModalWidget()``'s stack; a plain ``close()``/``hide()`` after the
    nested loop is already running does not reliably pop that stack back off, and a stale entry
    left behind aborts a later, unrelated test's own modal lookup with a fatal ``QTEST_ASSERT``
    inside Qt. Restoring ``WA_ShowModal`` immediately before hiding makes Qt run ``leaveModal``
    and clears the stack properly.
    """
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _DismissReadinessModalOnShow(QObject):
    """App-wide event filter that auto-dismisses a real blocking ``QMessageBox`` the instant it
    is shown, wherever in a test's execution it happens to appear.

    Restated from ``tests/e2e/conftest.py``. **Load-bearing here in a way it is not there.**
    The e2e tier is offline and deterministic; this tier dials a real server that can degrade
    mid-test, and production surfaces a degraded readiness state with a blocking
    ``QMessageBox.critical(...)`` opened via ``.exec()``. With no ``pytest-timeout`` configured
    that hangs the whole run with no output at all.

    **Why a one-shot timer armed after ``build_app()`` is not a substitute.** The startup
    readiness tick is armed by ``window.show()``'s ``showEvent`` but stays *pending*,
    undelivered, until something next pumps the Qt event loop -- which happens only once a test
    starts genuinely waiting on real application state. A dismiss timer armed at a fixed delay
    can fire before the modal exists; the modal then opens afterwards into a nested loop nothing
    will ever unwind. An event filter watching for the moment Qt actually shows a
    ``QMessageBox`` is the only thing that catches it regardless of when the pump happens.

    **Why the dismiss is scheduled on a delay rather than done synchronously inside the Show
    event.** ``QDialog.exec()``'s sequence is ``show()`` (which dispatches the ``Show`` event
    this filter reacts to) followed by constructing and running its own nested ``QEventLoop`` --
    that loop object does not exist yet while ``show()`` is still on the call stack, so hiding
    the widget from directly inside the event filter has nothing to make the nested loop return.
    Coming back a little later, once the nested loop is actually running, is what lets the
    dismissal take effect.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(
                MODAL_DISMISS_DELAY_MS, functools.partial(_dismiss_message_box, watched)
            )
        return False


def _assert_dispatcher_thread_stopped() -> None:
    """Fail loudly if the non-daemon ``pipeline-dispatcher`` thread is still alive.

    ``RunDispatcher.shutdown`` (DD-38) joins the dispatcher thread with a bounded timeout but
    returns silently if that join times out (DD-44) -- a thread left alive here is exactly the
    condition that hangs CPython's ``Py_Finalize`` forever at interpreter exit, *after* pytest
    has already printed its summary, so it reads like success. Calling this immediately after
    every ``handle.shutdown(...)`` converts that silent, un-diagnosable hang into an immediate,
    named test failure at the point the defect actually occurred.

    Raises:
        AssertionError: A thread named ``_DISPATCHER_THREAD_NAME`` is still alive.
    """
    live_thread_names = {thread.name for thread in threading.enumerate()}
    assert _DISPATCHER_THREAD_NAME not in live_thread_names, (
        f"{_DISPATCHER_THREAD_NAME!r} thread is still alive after handle.shutdown("
        f"timeout_ms={SHUTDOWN_TIMEOUT_MS}) -- the dispatcher join timed out silently and "
        "this process will hang at interpreter exit instead of returning"
    )


@pytest.fixture
def shutdown_handle(qtbot: QtBot) -> Callable[[AppHandle], None]:
    """Run the ordered shutdown the way production does -- window first, then handle.

    Restated verbatim from ``tests/e2e/conftest.py``; every guard below is load-bearing.

    ``AppHandle.shutdown`` is not idempotent -- a second call raises
    ``sqlite3.ProgrammingError`` on the already-closed connection -- so exactly one caller runs
    it per handle. In this tier that caller is ``build_live_app``'s ``request.addfinalizer``.

    **Drains the geometry debounce timer before closing the database.** ``window.close()``
    routes through ``CloseHandler`` -> ``_on_confirmed_quit``, which flushes the pending window
    geometry synchronously and then calls ``shell.force_close()``. That second, real
    ``close()`` hides the window, which re-fires a resize/move event that re-arms
    ``DebouncedGeometryWriter``'s single-shot 200ms timer with a fresh pending write. Left
    undrained, that timer only fires once *something else* next pumps the Qt event loop
    (typically the next test), by which point this fixture has already closed the write
    connection underneath it, crashing with ``sqlite3.ProgrammingError: Cannot operate on a
    closed database`` in a later, unrelated test.

    **Guards its own ``.close()`` and always runs ``handle.shutdown(...)``.** pytest-qt's own
    ``pytest_runtest_teardown`` hook closes and ``deleteLater()``s every
    ``qtbot.addWidget``-registered widget *before* any fixture's own teardown code runs, so a
    caller that registered ``handle.window`` may already have a C++-deleted window here, and
    ``.close()`` on it raises ``RuntimeError: Internal C++ object ... already deleted``. Left
    unguarded, that exception would abort this function before it ever reaches
    ``handle.shutdown(...)`` -- the actual root-cause fix for the non-daemon
    ``pipeline-dispatcher`` thread hang. The ``shiboken6.isValid`` guard skips the redundant
    close cleanly, and the ``try/finally`` guarantees ``handle.shutdown(...)`` always runs.

    **Asserts the dispatcher thread actually stopped, immediately after ``shutdown(...)``.**
    ``handle.shutdown(timeout_ms=SHUTDOWN_TIMEOUT_MS)`` can itself return without the thread
    having joined (see ``SHUTDOWN_TIMEOUT_MS``'s docstring) -- ``_assert_dispatcher_thread_stopped``
    turns that silent case into an immediate, named failure here rather than a hang at
    interpreter exit.
    """

    def _shutdown(handle: AppHandle) -> None:
        try:
            if shiboken6.isValid(handle.window):
                handle.window.close()
            qtbot.wait(GEOMETRY_DEBOUNCE_DRAIN_MS)
        finally:
            handle.shutdown(timeout_ms=SHUTDOWN_TIMEOUT_MS)
            _assert_dispatcher_thread_stopped()

    return _shutdown


@pytest.fixture
def build_live_app(
    request: pytest.FixtureRequest,
    qapp: QApplication,
    isolated_home: Path,
    shutdown_handle: Callable[[AppHandle], None],
) -> Generator[Callable[[str, str], LiveAppRig]]:
    """Build the real composed app against an app-data root seeded for one live provider.

    **Registers ``shutdown_handle`` via ``request.addfinalizer`` the instant ``build_app``
    returns.** ``build_app`` starts the non-daemon ``pipeline-dispatcher`` thread (DD-38) as a
    side effect of construction; that thread parks on ``queue.Queue.get()`` until
    ``AppHandle.shutdown`` enqueues its stop sentinel and joins it. CPython's
    ``Py_Finalize`` blocks joining every live non-daemon thread, so a handle that is never shut
    down hangs the whole ``pytest`` process *after* it prints its summary -- which reads like
    success. A post-``yield`` teardown line is not enough: anything between the build and the
    ``yield`` (or, here, anything in the caller's own body) can raise first, and a plain
    teardown line only runs once the generator resumes. ``addfinalizer`` runs either way, and
    because it is registered after this fixture's own generator finalizer it also runs *before*
    the ``removeEventFilter`` below -- so the modal filter is still installed while the app
    shuts down.

    ``isolated_home`` must be active before ``_seed_single_live_provider`` runs: both it and
    ``build_app`` resolve the app-data root through the same platform detector, which reads
    ``HOME`` on macOS.
    """
    dismiss_modal = _DismissReadinessModalOnShow()
    qapp.installEventFilter(dismiss_modal)

    def _build(base_url: str, model_name: str) -> LiveAppRig:
        provider_id = _seed_single_live_provider(base_url=base_url, model_name=model_name)
        handle = build_app(app=qapp, loop=QEventLoop())
        request.addfinalizer(functools.partial(shutdown_handle, handle))
        return LiveAppRig(handle=handle, provider_id=provider_id)

    yield _build
    qapp.removeEventFilter(dismiss_modal)


@pytest.fixture
def tiny_task_file(tmp_path: Path) -> Path:
    """One task file holding the smallest real question this app can benchmark."""
    path = tmp_path / "live_smoke_tasks.yaml"
    path.write_text(TINY_TASK_FILE_BODY, encoding="utf-8")
    return path


@pytest.fixture
def live_client_factory(qapp: QApplication) -> Generator[Callable[[str], LLMClient]]:
    """Build a real ``LLMClient`` against a real local base URL, for probe and discovery only.

    Every collaborator is the production one -- ``make_system_clock``, the real
    ``QtEventBusDeliverer`` (``compose.py``'s own bus; the tier already has a ``QApplication``,
    so no fake bus is needed and none is used), a real inference-activity store, a real
    ``httpx.Client``. No fake and no wire stub stands in for the provider here; that is the
    entire point of this tier (ADR-0011). The client is built through the package's PUBLIC
    ``make_openai_client`` factory, never ``_internal``. Exactly one clock and one event bus are
    constructed and shared between the client's own collaborators and the inference-activity
    store, matching ``compose.py``'s own wiring (one of each for the whole app) -- two of
    either would let the inference-activity store publish onto a bus the client itself never
    reads from, or timestamp against a clock the client never reads from.

    ``resolved_api_key`` is ``""`` and ``api_key_raw`` is ``None``: Ollama and LM Studio are
    keyless, and the field holds only a bare env-var NAME when it holds anything at all --
    never a key value, and never an invented placeholder.

    The benchmark run itself does NOT use this client; it uses the one ``build_app`` constructs.
    ``PROBE_TIMEOUT_MS`` therefore bounds discovery only.
    """
    http_client = httpx.Client()
    clock = make_system_clock()
    event_bus = make_qt_event_bus_deliverer()
    collaborators = OpenAICompatibleClientCollaborators(
        clock=clock,
        event_bus=event_bus,
        inference_activity_store=make_inference_activity_store(clock=clock, event_bus=event_bus),
        http_client=http_client,
    )
    settings = OpenAICompatibleClientSettings(
        connect_timeout_ms=PROBE_TIMEOUT_MS, probe_timeout_ms=PROBE_TIMEOUT_MS
    )
    built: list[LLMClient] = []

    def _make(base_url: str) -> LLMClient:
        config = ProviderConfig(
            provider_id=_DISCOVERY_PROVIDER_ID,
            name="live-local discovery",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            enabled=True,
            base_url=base_url,
            api_key_raw=None,
        )
        client = make_openai_client(config, "", collaborators=collaborators, settings=settings)
        built.append(client)
        return client

    yield _make
    try:
        for client in built:
            # `LLMClient` does not declare `close()`; the concrete client has it.
            cast("_OpenAICompatibleClientProtocolWithClose", client).close()
    finally:
        # A `finally`, not a second unguarded loop line: one failing `client.close()` must not
        # skip closing the shared `httpx.Client` those clients were all built on top of.
        http_client.close()


class _OpenAICompatibleClientProtocolWithClose:
    """Typing-only stand-in naming the ``close()`` the concrete client has but ``LLMClient``
    does not declare. Never instantiated -- ``mypy --strict`` does not cover this directory, so
    this exists purely to keep the ``cast`` above readable. Private: not part of this
    conftest's fixtures-only contract."""

    def close(self) -> None:  # pragma: no cover - never called on this class
        """Release the client's transport resources."""


def _health_dot(handle: AppHandle) -> HealthDotWidget:
    """Locate the status bar's health dot.

    Restated from ``tests/e2e/test_full_run_from_ui_smoke.py``. The dot is rebuilt on every
    render (``StatusBarWidget._rebuild_health_dot``), so it must be re-located on each poll
    rather than resolved once.
    """
    health_region = cast("QWidget", handle.window.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    dot = cast("HealthDotWidget", item.widget())
    assert dot is not None
    return dot


def _read_conn_factory() -> Callable[[], sqlite3.Connection]:
    """A fresh read-only connection onto the same on-disk database ``build_app`` opened.

    Restated from ``tests/e2e/test_full_run_from_ui_smoke.py``. Resolved through the same
    platform detector production uses, so this reads the real ``tmp_path``-backed file.
    """
    db_path = make_platform_detector().detect().app_data_root / DB_FILENAME
    return functools.partial(open_read_connection, db_path)


def _runs_store(handle: AppHandle) -> RunsStore:
    return create_runs_store(handle.write_conn, handle.write_lock, _read_conn_factory())


def _results_store(handle: AppHandle) -> ResultsStore:
    return create_results_store(handle.write_conn, handle.write_lock, _read_conn_factory())


@pytest.fixture
def live_smoke(
    qtbot: QtBot,
    live_client_factory: Callable[[str], LLMClient],
    build_live_app: Callable[[str, str], LiveAppRig],
    tiny_task_file: Path,
) -> Callable[[str], LiveSmokeOutcome]:
    """Probe, discover, and run one tiny real benchmark against ``base_url``.

    The shared body of AC-1 and AC-2. It lives in this conftest rather than in one provider
    module because the tier's modules cannot import from each other (no ``__init__.py`` under
    ``tests/``) and must not restate it -- a fixture is resolved by name, so it needs no import
    at all.

    Skips (never fails) when the server is unreachable within the bounded timeout, or when it is
    reachable but exposes no model: both are "this machine is not set up for the live tier",
    which ADR-0011 requires to be a clean skip. A skipped result is honest evidence, not a pass.

    Discovery and the run are one operation rather than two tests because the model to run
    against is whatever the operator happens to have pulled -- it must be discovered at runtime
    and fed straight into the run. Hardcoding a model name would fail on every machine but one.

    ``RunMode.TASKS`` is the smallest real run this app can perform: ``phase_applies`` runs only
    ``INITIALIZATION`` and ``INFERENCE`` for any non-``GRADED`` mode, so no judge model is built
    and ``run_needs_embeddings`` short-circuits to ``False`` before the DD-48 embedding probe.
    The request carries no ``setting_overrides``: the run must reach ``COMPLETED`` on this
    app's shipped defaults, which leave ``eval.phase_keyword_enabled`` and
    ``eval.phase_cosine_enabled`` ``"true"``. 08-B section 5.1 gates the transition on the mode
    -- ``RUNNING_INFERENCE --> COMPLETED: inference succeeded, mode does not grade`` -- so a
    non-``GRADED`` row completes at inference no matter how those toggles are set. Overriding
    them here would route around exactly the defect this tier caught on its first live run.

    Shutdown is owned by ``build_live_app``'s finaliser, not by a ``finally`` here: registering
    it at build time is what makes it run even when a wait below times out.

    Skips (never lets a raw taxonomy exception escape mid-fixture) when the server answers TCP
    but the probe/discovery client itself raises talking to it -- e.g. LM Studio running with
    its OpenAI-compatible API disabled, so ``GET /v1/models`` errors even though the port is
    open. ``client.list_models()`` translates that into an ``AppError`` leaf (boundary
    translation, ``error-handling-standard.md``); this is exactly the same "not set up for the
    live tier" condition the unreachable-server and no-models skips already cover.
    """

    def _run(base_url: str) -> LiveSmokeOutcome:
        if not server_reachable(base_url):
            pytest.skip(
                f"no live server reachable at {base_url} within {REACHABILITY_TIMEOUT_S}s -- "
                f"start it, or leave this tier unrun"
            )
        client = live_client_factory(base_url)
        try:
            health = client.probe_health()
            models = client.list_models()
        except AppError as exc:
            pytest.skip(
                f"{base_url} answered TCP but talking to it raised "
                f"{type(exc).__name__}: {exc} -- confirm its OpenAI-compatible API is enabled "
                f"and reachable, then re-run this tier"
            )
        if not models:
            pytest.skip(
                _lookup_known_base_url(
                    _NO_MODELS_GUIDANCE, base_url, mapping_name="_NO_MODELS_GUIDANCE"
                )
            )

        model_name = str(models[0])
        rig = build_live_app(base_url, model_name)
        rig.handle.window.show()
        qtbot.waitUntil(rig.handle.window.isVisible, timeout=WINDOW_VISIBLE_TIMEOUT_MS)
        # Start is gated on the single-inference gate, which the startup readiness probe itself
        # holds; starting before it settles produces a rejected run that reads like a pipeline
        # bug.
        qtbot.waitUntil(
            lambda: _health_dot(rig.handle).text_label != _CHECKING_HEALTH_LABEL,
            timeout=READINESS_TIMEOUT_MS,
        )
        run_id = rig.handle.flow.start(
            RunStartRequest(
                run_mode=RunMode.TASKS,
                test_models=(ModelDescriptor(provider_id=rig.provider_id, model_name=model_name),),
                task_paths=(str(tiny_task_file),),
            )
        )
        if run_id == _NO_RUN_CREATED_SENTINEL:
            pytest.fail(
                "flow.start() refused the request and created no run: either the "
                "single-inference gate was still held, or the task file could not be loaded"
            )
        qtbot.waitUntil(lambda: not rig.handle.flow.is_running(), timeout=RUN_TIMEOUT_MS)
        rows = _results_store(rig.handle).list_results(run_id)
        return LiveSmokeOutcome(
            reachable=health.reachable,
            discovered_any=True,
            run_status=_runs_store(rig.handle).get_run(run_id).status,
            # A run that staged nothing settles COMPLETED with zero rows, so an empty
            # `rows` must not read as a pass. `PENDING` -- "nothing was ever executed" -- is
            # the stand-in, and it is deliberately not the expected value.
            first_result_status=rows[0].status if rows else ResultStatus.PENDING,
        )

    return _run


@pytest.fixture
def expected_live_smoke_outcome() -> LiveSmokeOutcome:
    """The outcome a healthy live provider must produce: reachable, at least one model, and a
    run that reached ``COMPLETED`` with a completed first result row.

    Handed over as a fixture so a provider test module never imports ``LiveSmokeOutcome``.
    """
    return LiveSmokeOutcome(
        reachable=True,
        discovered_any=True,
        run_status=RunStatus.COMPLETED,
        first_result_status=ResultStatus.COMPLETED,
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply the ``live_local`` marker to every item collected under this directory.

    Belt-and-suspenders for the module docstring's claim that ``pyproject.toml``'s
    ``addopts`` (``-m "not live_local"``) deselects this whole tier from a bare ``pytest``
    invocation: that claim is only true if every test module under here actually carries the
    marker. Tasks 4/5's test modules are expected to declare ``@pytest.mark.live_local``
    explicitly too, and this hook is idempotent with that -- ``Item.add_marker`` is a no-op if
    the marker is already present, so declaring it twice is harmless. This closes off the
    "a new test module under this directory forgot the marker" failure mode entirely, rather
    than relying on every future author remembering it.

    Scoped to items whose collected path is inside this conftest's own directory: this hook,
    unlike a fixture, is not path-scoped by pytest and would otherwise run against every item
    in the whole session once this conftest is loaded at all.
    """
    for item in items:
        if item.path.is_relative_to(_THIS_DIR):
            item.add_marker(pytest.mark.live_local)
