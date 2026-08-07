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
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTabWidget, QWidget
import pytest

import ollama_llm_bench.adapters.native_pickers._internal.qt_native_pickers as _qt_native_pickers_module
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
import ollama_llm_bench.compose as _compose_module
from ollama_llm_bench.compose import AppHandle, build_app
import ollama_llm_bench.ui.common_dialogs as _common_dialogs_module
from ollama_llm_bench.ui.common_dialogs import (
    GenerateAnalysisCollaborators,
    make_about_dialog as _real_make_about_dialog,
    make_generate_analysis_dialog as _real_make_generate_analysis_dialog,
)

_IDLE_TIMEOUT_MS = 10_000
_NOT_READY_HEALTH_LABEL = "Not ready"
_GEOMETRY_DEBOUNCE_DRAIN_MS = 300
_SHUTDOWN_TIMEOUT_MS = 2000
_DISMISS_DELAY_MS = 50

_PLACEHOLDER_RUN_ID = -1
_PROVIDER_ID = "aaaaaaaa-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_TASK_ID = "synthetic_small_1"
_TIMESTAMP = "2026-08-05T12:00:00Z"  # matches conftest.py's `_canned_run` precedent

# Copied verbatim from `tests/integration/test_a11y_names_result_settings_task_editor.py`'s
# `_SEED_TASK_YAML` (STORY-099's own precedent for mounting the Task Editor's Field Editor
# rows) -- one minimal, schema-valid task so `_add_buffer` auto-selects task index 0 and the
# Field Editor mounts its rows (`ui/task_editor/_internal/controller.py`).
_SEED_TASK_YAML = (
    "schema_version: 1\n"
    "tasks:\n"
    '  - task_id: "t1"\n'
    "    difficulty: medium\n"
    '    question: "What is 2+2?"\n'
    '    golden_answer: "4"\n'
    '    pass_criteria: "answer is correct"\n'
    '    fail_criteria: "answer is incorrect"\n'
    "    required_terms:\n"
    "      exact: []\n"
    "      semantic: []\n"
    "      forbidden: []\n"
)


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
    ("dialog_close_button", "Close dialog", "Close"),
    (
        "open_data_folder_button",
        "Open application data folder",
        "Open the application data folder",
    ),
    (
        "copy_data_folder_path_button",
        "Copy application data folder path",
        "Copy the application data folder path",
    ),
    (
        "judge_model_refresh_button",
        "Refresh judge model list",
        "Refresh the judge provider's model list",
    ),
    ("chart_prev_button", "Previous chart", "Previous chart"),
    ("chart_next_button", "Next chart", "Next chart"),
    (
        "detach_chart_button",
        "Detach chart",
        "Open the chart in its own window",
    ),
    (
        "gate_busy_indicator",
        "Inference in flight — controls temporarily disabled",
        "An inference is in flight; please wait.",
    ),
    ("question_help_button", "Help: Question", "About this field"),
    ("golden_answer_help_button", "Help: Golden answer", "About this field"),
    (
        "validation_summary_button",
        "Validation summary — focus first issue",
        "Click to focus the first task with a warning",
    ),
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


def _dismiss_and_clear_modal_stack(dialog: QDialog) -> None:
    """Hide `dialog` in a way that always removes it from Qt's modal-widget stack.

    Restated verbatim from `tests/integration/test_menu_opens_dialogs.py`'s helper of the
    same name -- see that file's docstring for the full Qt-internals rationale (a plain
    `close()`/`hide()` after a genuinely-blocked `.exec()` leaves a stale entry on
    `QApplication.activeModalWidget()`'s stack that aborts a later `findChild`+click with a
    fatal `QTEST_ASSERT` inside Qt).
    """
    dialog.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    dialog.hide()
    dialog.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _NoOpGenerateAnalysisSubscription:
    """No-op `Subscription` handle; cancellation does nothing."""

    def cancel(self) -> None:
        return None


class _GenerateAnalysisEventBusFake:
    """Structural `EventBus` fake routing this fixture around a real, still-unfixed
    production defect.

    `ui/common_dialogs/_internal/generate_analysis_view.py` calls
    `event_bus.subscribe(signal, handler)` three times with no `owner=` keyword. The
    real `QtEventBusDeliverer.subscribe` carries an `icontract` precondition requiring
    a non-`None` owner (`08-J_event_bus_catalog.md` §2), so building this dialog
    against the app's real event bus raises `icontract.errors.ViolationError` and
    crashes the process -- a genuine defect first surfaced by STORY-087's screenshot
    harness (see that story's Findings section) and worked around identically by
    `tests/integration/conftest.py`'s `_StubGenerateAnalysisEventBus`. Restated here,
    not imported, because fixtures do not cross the `tests/e2e` vs other test-tier
    boundary (same rationale as this file's other restated helpers); global constraints
    for this story forbid touching `src/`, so the fix itself is out of this story's
    scope. It changes no behaviour of its own -- it only accepts the missing-owner
    calls the real bus would reject.
    """

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> _NoOpGenerateAnalysisSubscription:
        return _NoOpGenerateAnalysisSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


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


def _open_benchmark_workspace_and_charts_tab(handle: AppHandle) -> None:
    """Switch to the Benchmark workspace, then click the Result widget's Charts tab.

    Enables the pinned rows for `judge_model_refresh_button` (New Benchmark is the left
    panel's default-active tab -- `compose.py`'s `_make_benchmark_workspace` adds it first,
    so no dedicated New Benchmark click is needed) and for the three Charts-tab controls
    (`chart_prev_button`, `chart_next_button`, `detach_chart_button`), which only exist once
    `charts_tab_host` has been mounted into the visible tab. `_seed_one_completed_run` (run at
    fixture build time, before this call) makes `ResultController.load_initial_state` select a
    run and enable `result_widget.tabs` (`ui/results/_internal/controller.py:219-239`,
    `ui/results/_internal/view.py:137`); this waits for that enablement instead of assuming it
    is already true by the time the workspace switch renders.
    """
    workspace_benchmark_button = cast(
        "QWidget", handle.window.findChild(QWidget, "workspace_benchmark_button")
    )
    QTest.mouseClick(workspace_benchmark_button, Qt.MouseButton.LeftButton)

    result_tabs = cast("QTabWidget", handle.window.findChild(QTabWidget, "result_widget.tabs"))
    _wait_until(result_tabs.isEnabled, timeout_ms=_IDLE_TIMEOUT_MS)
    charts_tab_index = next(
        index
        for index in range(result_tabs.count())
        if result_tabs.widget(index).objectName() == "charts_tab_host"
    )
    QTest.mouseClick(
        result_tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=result_tabs.tabBar().tabRect(charts_tab_index).center(),
    )


def _open_run_analysis_tab_and_generate_dialog(handle: AppHandle) -> QDialog:
    """Click the Result widget's Run Analysis tab, then trigger and dismiss the real
    Generate Analysis dialog via a genuine "Generate analysis" button click.

    Enables the pinned row for `gate_busy_indicator` (STORY-089-AC-1) -- that indicator
    is mounted inside the Generate Analysis dialog itself
    (`ui/common_dialogs/_internal/generate_analysis_view.py`), so it only exists in the
    widget tree once this dialog has been constructed at least once. `_seed_one_completed_run`
    (run at fixture build time) gives the tab's toolbar-gate an enabled "Generate analysis"
    button (`ui/results/_internal/run_analysis_tab/select.py`'s `_button_gate`: a terminal,
    idle-gate run with a `COMPLETED` result), so no extra waiting is needed beyond the tab
    switch itself.

    Unlike `_open_and_dismiss_about_dialog` above -- where `compose.py` imports
    `make_about_dialog` at module scope, patchable at `_compose_module.make_about_dialog` --
    `_on_run_analysis_generate_clicked` (`ui/results/_internal/controller.py`) imports
    `make_generate_analysis_dialog` *inside its own function body*, a deferred import the
    function's own comment says exists to break a transitive import-cycle risk through
    `ui.new_benchmark`. That means there is no persistent
    `ollama_llm_bench.ui.results._internal.controller.make_generate_analysis_dialog`
    attribute to patch -- the name is re-resolved from `ui.common_dialogs`'s own namespace on
    every call. The only working patch target is therefore `ui.common_dialogs` itself, the
    **source** module -- a deliberate, narrow exception to "patch at the point of use, never
    the source module", justified specifically by this deferred-import pattern.

    Returns the constructed dialog so the caller (`registry_app`) can keep a live Python
    reference for the rest of the fixture's lifetime. Confirmed empirically (unlike the About
    dialog's `compose.py:395` chained `make_about_dialog(...).exec()` with no Python reference
    at all, which survives): once every Python reference to this specific dialog drops, the
    next `QApplication.processEvents()` call -- which `pytest-qt`'s own
    `pytest_runtest_setup` hook (`pytestqt/plugin.py`) runs immediately after this fixture's
    `yield`, before the parametrized test body -- destroys the underlying `QLabel` this row
    needs, and `gate_busy_indicator` becomes unfindable from the real test.
    """
    result_tabs = cast("QTabWidget", handle.window.findChild(QTabWidget, "result_widget.tabs"))
    run_analysis_tab_index = next(
        index
        for index in range(result_tabs.count())
        if result_tabs.widget(index).objectName() == "run_analysis_tab_host"
    )
    QTest.mouseClick(
        result_tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=result_tabs.tabBar().tabRect(run_analysis_tab_index).center(),
    )

    generate_button = cast(
        "QWidget",
        result_tabs.widget(run_analysis_tab_index).findChild(
            QWidget, "run_analysis_tab.generate_button"
        ),
    )

    captured_generate_analysis_dialog: list[QDialog] = []

    def _capture_generate_analysis(**kwargs: object) -> QDialog:
        collaborators = cast("GenerateAnalysisCollaborators", kwargs["collaborators"])
        # Route around the live `event_bus.subscribe(...)`-with-no-`owner=` defect this
        # dialog's own constructor hits -- see `_GenerateAnalysisEventBusFake`'s docstring.
        kwargs["collaborators"] = msgspec.structs.replace(
            collaborators, event_bus=_GenerateAnalysisEventBusFake()
        )
        dialog = _real_make_generate_analysis_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real controller kwargs
        captured_generate_analysis_dialog.append(dialog)
        return dialog

    original_make_generate_analysis_dialog = _common_dialogs_module.make_generate_analysis_dialog
    _common_dialogs_module.make_generate_analysis_dialog = _capture_generate_analysis
    try:
        QTimer.singleShot(
            _DISMISS_DELAY_MS,
            lambda: _dismiss_and_clear_modal_stack(captured_generate_analysis_dialog[0]),
        )
        QTest.mouseClick(generate_button, Qt.MouseButton.LeftButton)
    finally:
        _common_dialogs_module.make_generate_analysis_dialog = (
            original_make_generate_analysis_dialog
        )
    return captured_generate_analysis_dialog[0]


def _open_and_dismiss_about_dialog(handle: AppHandle) -> None:
    """Open the real About dialog via a genuine button click, then dismiss it.

    Enables the pinned rows for the About dialog's controls (Close, Open data folder, Copy
    data-folder path) to be located by the shared test function below. `mocker` (function-
    scoped) cannot be injected into the module-scoped `registry_app` fixture, so the patch on
    `compose.make_about_dialog` is a manual assign/restore instead of `mocker.patch` -- see
    `tests/integration/test_menu_opens_dialogs.py:162,221` for the equivalent
    `mocker.patch("ollama_llm_bench.compose.make_about_dialog", ...)` this mirrors by hand,
    and that same file's `_dismiss_and_clear_modal_stack` for why the dismissal timer must be
    armed *before* the click that opens the dialog, not after.
    """
    captured_about_dialog: list[QDialog] = []

    def _capture_about(**kwargs: object) -> QDialog:
        dialog = _real_make_about_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured_about_dialog.append(dialog)
        return dialog

    original_make_about_dialog = _compose_module.make_about_dialog  # type: ignore[attr-defined]  # patch at the point of use; compose.py imports this name at module scope but does not re-export it
    _compose_module.make_about_dialog = _capture_about  # type: ignore[attr-defined]  # same manual-patch target as above
    try:
        about_button = cast("QWidget", handle.window.findChild(QWidget, "about_menu_button"))
        QTimer.singleShot(
            _DISMISS_DELAY_MS,
            lambda: _dismiss_and_clear_modal_stack(captured_about_dialog[0]),
        )
        QTest.mouseClick(about_button, Qt.MouseButton.LeftButton)
    finally:
        _compose_module.make_about_dialog = original_make_about_dialog  # type: ignore[attr-defined]  # restore the manual patch


def _open_task_editor_with_seeded_file(handle: AppHandle, seed_task_path: Path) -> None:
    """Switch to the Task Editor workspace, then load `seed_task_path` through a genuine
    click on the real "Open File" toolbar button, with only `QFileDialog.getOpenFileNames`
    stubbed at the Qt level.

    Enables the pinned rows for `question_help_button`/`golden_answer_help_button` (the
    Field Editor mounts its rows only once a task buffer with at least one task is open --
    `ui/task_editor/_internal/controller.py`'s `_add_buffer` auto-selects task index 0, see
    `on_open_file_clicked`/`_open_path`) and for `validation_summary_button` (mounted on the
    toolbar itself, but only exercised meaningfully once a buffer exists). The Open File
    button (`task_editor.toolbar.open_file`) drives `NativePickers.open_file` with
    `allow_multiple=True` (`ui/task_editor/_internal/controller.py:186-192`), which calls the
    plural `QFileDialog.getOpenFileNames` -- the exact patch target this mirrors from
    `src/ollama_llm_bench/adapters/native_pickers/tests/test_native_pickers.py:109-118`.
    Everything downstream of the stubbed dialog call -- the real `NativePickers` adapter,
    `TaskEditorController.on_open_file_clicked`, buffer loading, and Field Editor mounting --
    stays real; this is the first test in this file driving `NativePickers` through a genuine
    button click rather than calling `QtNativePickers.open_file` directly. `mocker` (function-
    scoped) cannot be injected into this module-scoped fixture, so the patch is a manual
    assign/restore, same as `_open_and_dismiss_about_dialog`'s and
    `_open_run_analysis_tab_and_generate_dialog`'s patches above.
    """
    workspace_task_editor_button = cast(
        "QWidget", handle.window.findChild(QWidget, "workspace_task_editor_button")
    )
    QTest.mouseClick(workspace_task_editor_button, Qt.MouseButton.LeftButton)

    original_get_open_file_names = _qt_native_pickers_module.QFileDialog.getOpenFileNames  # type: ignore[attr-defined]  # manual patch mirroring test_native_pickers.py:109-118; module-scoped fixture cannot take mocker
    _qt_native_pickers_module.QFileDialog.getOpenFileNames = staticmethod(  # type: ignore[attr-defined, method-assign]  # same manual-patch target as above
        lambda *_args, **_kwargs: ([str(seed_task_path)], "")
    )
    try:
        open_file_button = cast(
            "QWidget",
            handle.window.findChild(QWidget, "task_editor.toolbar.open_file"),
        )
        QTest.mouseClick(open_file_button, Qt.MouseButton.LeftButton)
    finally:
        _qt_native_pickers_module.QFileDialog.getOpenFileNames = original_get_open_file_names  # type: ignore[attr-defined, method-assign]  # restore the manual patch


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

    _open_and_dismiss_about_dialog(handle)
    _open_benchmark_workspace_and_charts_tab(handle)
    # Held for the fixture's whole lifetime (not just discarded once dismissed) -- see
    # `_open_run_analysis_tab_and_generate_dialog`'s docstring: this dialog's `QLabel`
    # children are destroyed by `pytest-qt`'s post-setup `processEvents()` call the moment
    # no Python reference to the dialog survives, unlike every other dialog this file opens.
    generate_analysis_dialog = _open_run_analysis_tab_and_generate_dialog(handle)

    # A second, separate temp dir from `tmp_path` above (the app-data home) -- keeps the
    # seeded task file's concerns separate from the app-data-root filesystem isolation.
    task_files_root = tmp_path_factory.mktemp("task_files")
    seed_task_path = task_files_root / "sample_tasks.yaml"
    seed_task_path.write_text(_SEED_TASK_YAML, encoding="utf-8")
    _open_task_editor_with_seeded_file(handle, seed_task_path)

    yield handle

    del generate_analysis_dialog
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


_READINESS_DOT_OBJECT_NAME = "provider_readiness_indicator"
_READINESS_DOT_TOOLTIP_FIRST_LINE = "Provider readiness — click to open Settings / Providers"


def test_provider_readiness_indicator_tooltip_leads_with_the_pinned_sentence(
    registry_app: AppHandle,
) -> None:
    """Proves: STORY-089-AC-1

    The provider-readiness dot reports the pinned objectName and accessible name, and its
    tooltip's FIRST line is the registry's pinned sentence. Only the first line is pinned:
    the lines beneath it carry the per-provider reachability detail the Main Window
    specification separately requires, which the registry's one sentence does not include --
    identical scope to STORY-097-AC-2's own assertion for this same control
    (`tests/integration/test_a11y_names_shell.py::test_readiness_dot_tooltip_leads_with_the_pinned_sentence`).
    """
    # Arrange
    handle = registry_app

    # Act
    dot = cast("QWidget | None", handle.window.findChild(QWidget, _READINESS_DOT_OBJECT_NAME))

    # Assert
    assert dot is not None, "no provider-readiness dot is mounted in the app"
    assert (dot.objectName(), dot.accessibleName(), dot.toolTip().splitlines()[0]) == (
        _READINESS_DOT_OBJECT_NAME,
        "Provider readiness status",
        _READINESS_DOT_TOOLTIP_FIRST_LINE,
    )
