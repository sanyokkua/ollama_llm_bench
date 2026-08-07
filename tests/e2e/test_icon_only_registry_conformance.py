"""Proves: STORY-089-AC-1

The single table-driven regression net over every row of the icon-only/ambiguous-control
registry (12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md #72), asserted against the real,
fully composed application -- never a standalone per-widget factory. STORY-097/098/099 each
proved their own partition against standalone widgets/dialogs; this story is what catches a
control silently *moving* between screens later, which a per-module test is structurally
blind to (see STORY-089's own Goal section).

The pinned strings in `_PINNED_ROWS` are written out as literals, deliberately -- copied from
the accessibility registry so the assertion never becomes a tautology against production
(same rationale as `tests/integration/test_a11y_names_shell.py`'s module docstring).

This file writes no application code and imports nothing from `src/` beyond what a test needs
to construct the app and locate widgets. If a row's real value diverges from the table below,
the fix belongs in the child story that owns that row (STORY-097/098/099), not here.
"""

from collections.abc import Callable, Generator
import functools
import os
from pathlib import Path
from typing import cast

import msgspec
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultStatus,
    RunMode,
    RunStatus,
    TaskOrigin,
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
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

_IDLE_TIMEOUT_MS = 10_000
_NOT_READY_HEALTH_LABEL = "Not ready"
_GEOMETRY_DEBOUNCE_DRAIN_MS = 300
_SHUTDOWN_TIMEOUT_MS = 2000

_PLACEHOLDER_RUN_ID = -1
_PROVIDER_ID = "aaaaaaaa-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_TASK_ID = "synthetic_small_1"
_TIMESTAMP = "2026-08-05T12:00:00Z"  # matches conftest.py's `_canned_run` precedent


# (object_name, accessible_name, tooltip)
_PINNED_ROWS: tuple[tuple[str, str, str], ...] = (
    ("settings_menu_button", "Settings", "Open the Settings dialog"),
    (
        "about_menu_button",
        "About",
        "Application information: version, links, data folders",
    ),
    ("workspace_benchmark_button", "Benchmark workspace", "Benchmark workspace"),
    ("workspace_task_editor_button", "Task Editor workspace", "Task Editor workspace"),
    (
        "running_pill_button",
        "Run in progress — open Progress",
        "Switch to the Benchmark workspace and focus the Progress widget",
    ),
    ("rename_run_button", "Rename run", "Rename run"),
)
# Note: `provider_readiness_indicator` is deliberately not in `_PINNED_ROWS` above -- its
# tooltip needs the first-line-only comparison (STORY-097 precedent), so it gets its own,
# separate assertion elsewhere, not a shared-table row.


def _health_dot_settled(handle: AppHandle) -> bool:
    """Whether the status-bar health dot has settled to the offline NOT_READY label.

    Restated from `test_launch_idle_shutdown_smoke.py`'s `_wait_for_not_ready_health_dot`
    (no importable shared home exists under `tests/`), adapted to a plain predicate so a
    manual `QTest.qWait` polling loop can use it -- this fixture is module-scoped and
    cannot take the function-scoped `qtbot` fixture (`.claude/rules/testing.md:190`).
    """
    health_region = cast("QWidget", handle.window.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    if layout is None:
        return False
    item = layout.itemAt(0)
    if item is None:
        return False
    dot = item.widget()
    return dot is not None and getattr(dot, "text_label", None) == _NOT_READY_HEALTH_LABEL


def _wait_until(predicate: Callable[[], bool], *, timeout_ms: int) -> None:
    """Poll `predicate` by pumping the Qt event loop.

    Mirrors `qtbot.waitUntil`'s contract without requiring the function-scoped `qtbot`
    fixture. `QTest.qWaitFor` is not available in this project's pinned PySide6 (verified
    against the installed build), so this is a plain step-and-check loop -- the same
    technique `qtbot.waitUntil` itself uses internally.
    """
    step_ms = 50
    waited_ms = 0
    while not predicate():
        if waited_ms >= timeout_ms:
            message = f"condition not met within {timeout_ms}ms"
            raise AssertionError(message)
        QTest.qWait(step_ms)
        waited_ms += step_ms


def _dismiss_message_box(modal: QMessageBox) -> None:
    """Hide `modal` in a way that always removes it from Qt's modal-widget stack.

    Identical mechanics to `tests/e2e/conftest.py`'s helper of the same name (restated, not
    imported -- fixtures do not cross the `tests/e2e` vs other test-tier boundary and this
    file additionally cannot depend on the function-scoped `qtbot`-based fixtures that
    helper's siblings use).
    """
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _DismissReadinessModalOnShow(QObject):
    """App-wide event filter auto-dismissing the real NOT_READY `QMessageBox` the instant it
    is shown. Restated from `tests/e2e/conftest.py`'s identical class -- see that class's
    docstring for the full timing rationale (why a one-shot timer armed at build time is not
    enough, why this must be an event filter instead).
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(100, functools.partial(_dismiss_message_box, watched))
        return False


def _seed_one_completed_run(app_data_root: Path) -> None:
    """Insert one completed run + one completed result row directly into the seeded,
    schema-initialized database at `app_data_root`, via the real `RunsStore`/`ResultsStore`
    factories -- never raw SQL.

    Enables Result's tab bar (`ResultController.load_initial_state` auto-selects this run,
    see `ui/results/_internal/controller.py:219-232`) so a **real click** can reach the
    Charts and Run Analysis tabs; no benchmark run is ever executed, so this stays fully
    offline like every other e2e/integration fixture in this repo. Shape mirrors
    `tests/integration/conftest.py`'s `_canned_run`/`_canned_results` precedent, except the
    status is COMPLETED (not the precedent's INCOMPLETE/live) since this run must not be
    treated as the live run by the Result widget. Also inserts the one parent
    `benchmark_tasks` row `benchmark_results` is foreign-keyed against
    (`(run_id, task_id)` -- `_canned_run`/`_canned_results` skip this because they only ever
    feed stub gateways, never the real `SqliteResultsStore` this fixture uses).
    """
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    read_conn_factory = functools.partial(open_read_connection, db_path)
    runs_store = create_runs_store(write_conn, lock, read_conn_factory)
    tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
    results_store = create_results_store(write_conn, lock, read_conn_factory)
    run_id = runs_store.create_run(
        BenchmarkRun(
            run_id=_PLACEHOLDER_RUN_ID,
            run_name=None,
            timestamp=_TIMESTAMP,
            run_mode=RunMode.SYNTHETIC,
            status=RunStatus.COMPLETED,
            total_tasks=1,
            completed_tasks=1,
            total_elapsed_ms=1_000,
            schema_version=1,
            created_at=_TIMESTAMP,
        )
    )
    tasks_store.create_tasks(
        run_id,
        (
            BenchmarkTask(
                task_id=_TASK_ID,
                task_origin=TaskOrigin.SYNTHETIC,
                question="What is 2+2?",
            ),
        ),
    )
    results_store.create_results(
        (
            BenchmarkResult(
                result_id=1,
                run_id=run_id,
                task_id=_TASK_ID,
                provider_id=_PROVIDER_ID,
                provider_name="Ollama (local)",
                model_name=_MODEL_NAME,
                status=ResultStatus.COMPLETED,
                created_at=_TIMESTAMP,
            ),
        )
    )
    write_conn.close()


@pytest.fixture(scope="module")
def registry_app(
    tmp_path_factory: pytest.TempPathFactory,
    qapp: QApplication,
) -> Generator[AppHandle]:
    """Build the real, fully composed application ONCE for every parametrized case in this
    file, then drive every real navigation step needed to reach all 17 registry rows.

    Module-scoped so the ~18 parametrized cases in the single test function below share one
    expensive app build + navigation sequence, keeping this file inside the e2e 60s/test
    budget -- see this module's docstring for why `qtbot` (function-scoped only) cannot be
    used here, and why `QTest.mouseClick`/`QTest.qWait` are used instead for every click and
    wait in this fixture. `qapp` is pytest-qt's own session-scoped fixture (wider than this
    fixture's module scope, so it is safe to depend on directly here).
    """
    tmp_path = tmp_path_factory.mktemp("registry_app")
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    original_home = os.environ.get("HOME")
    original_userprofile = os.environ.get("USERPROFILE")
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)

    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.close()

    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    seed_builtin_providers(write_conn, lock)
    providers_store = create_providers_store(
        write_conn, lock, functools.partial(open_read_connection, app_data_root / DB_FILENAME)
    )
    providers_store.replace_providers(
        tuple(
            msgspec.structs.replace(config, enabled=False)
            for config in providers_store.list_providers()
        )
    )
    write_conn.close()

    _seed_one_completed_run(app_data_root)

    dismiss_filter = _DismissReadinessModalOnShow()
    qapp.installEventFilter(dismiss_filter)

    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.show()
    _wait_until(handle.window.isVisible, timeout_ms=_IDLE_TIMEOUT_MS)
    _wait_until(lambda: _health_dot_settled(handle), timeout_ms=_IDLE_TIMEOUT_MS)

    yield handle

    qapp.removeEventFilter(dismiss_filter)
    handle.window.close()
    QTest.qWait(_GEOMETRY_DEBOUNCE_DRAIN_MS)
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    if original_home is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = original_home
    if original_userprofile is None:
        os.environ.pop("USERPROFILE", None)
    else:
        os.environ["USERPROFILE"] = original_userprofile


@pytest.mark.allow_qt_warnings  # offscreen-only: the deferred startup readiness tick opens
# the real NOT_READY modal (every provider is disabled by `registry_app`'s seeding) and that
# dialog resizes a widget before the offscreen platform plugin has a native window to hint,
# which logs "This plugin does not support propagateSizeHints()" -- pre-existing
# offscreen-plugin behaviour (also hit by `tests/e2e/test_launch_idle_shutdown_smoke.py`'s
# identical real-modal path), not a defect in this test or the production dialog wiring.
@pytest.mark.parametrize(("object_name", "accessible_name", "tooltip"), _PINNED_ROWS)
def test_every_registry_control_uses_its_pinned_name_objectname_and_tooltip(
    registry_app: AppHandle,
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-089-AC-1

    For every row of the icon-only/ambiguous-control registry, the control it names, as
    mounted in the real, fully composed application, exposes exactly the pinned objectName,
    accessible name, and tooltip -- no substitute, abbreviated, or generic value.
    """
    # Arrange
    handle = registry_app

    # Act
    control = cast("QWidget | None", handle.window.findChild(QWidget, object_name))

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted in the app"
    assert (control.objectName(), control.accessibleName(), control.toolTip()) == (
        object_name,
        accessible_name,
        tooltip,
    )
