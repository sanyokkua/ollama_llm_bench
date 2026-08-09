"""STORY-118 -- clicking Generate analysis in the assembled app opens the dialog.

No event-bus substitution anywhere: the dialog is constructed by production code against
the application's own real ``QtEventBusDeliverer``. Before this story that construction
raised icontract's ``ViolationError`` and terminated the process.
"""

from collections.abc import Callable, Generator
import functools
from pathlib import Path
from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QTabWidget, QWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultStatus,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.compose import AppHandle

# `allow_qt_warnings`: `build_smoke_app` drives the real NOT_READY modal, exactly as
# `test_launch_idle_shutdown_smoke.py` and `test_icon_only_registry_conformance.py` do.
pytestmark = pytest.mark.allow_qt_warnings

_PLACEHOLDER_RUN_ID = -1
_PROVIDER_ID = "aaaaaaaa-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_TASK_ID = "synthetic_small_1"
_TIMESTAMP = "2026-08-05T12:00:00Z"
_DISMISS_DELAY_MS = 50
_DIALOG_TIMEOUT_MS = 5000

_GENERATE_ANALYSIS_OBJECT_NAME = "common_dialogs.generate_analysis"


def _seed_one_completed_run(app_data_root: Path) -> None:
    """Insert one COMPLETED run, its parent task row, and one result row via the real store
    factories -- never raw SQL.

    ``ResultController.load_initial_state`` auto-selects this run, which is what enables the
    Result tab bar so a real click can reach the Run Analysis tab. No benchmark is ever
    executed; this stays fully offline. The ``benchmark_tasks`` row is required because
    ``benchmark_results`` is foreign-keyed against ``(run_id, task_id)``.

    Restated from ``test_icon_only_registry_conformance.py``'s identical helper rather than
    promoted into ``tests/e2e/conftest.py``: this directory deliberately restates shared
    helpers (see ``_DismissReadinessModalOnShow``) to keep the shared conftest out of an
    unrelated story's blast radius.
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


class _CaptureAndDismissGenerateAnalysisOnShow(QObject):
    """App-wide event filter capturing the Generate Analysis dialog the instant it is shown,
    then dismissing it on a short delay.

    Mirrors ``tests/e2e/conftest.py``'s ``_DismissReadinessModalOnShow`` -- and for the same
    two reasons, which matter more here than anywhere else in this suite:

    - **Why a filter rather than one ``QTimer.singleShot`` armed before the click.**
      ``ResultController._on_run_analysis_generate_clicked`` ends in ``dialog.exec()``
      (``ui/results/_internal/controller.py:177``), a blocking nested event loop. A dismiss
      timer armed at a guessed delay that fires before the dialog exists finds nothing, and
      the modal then opens into a nested loop nothing will ever unwind -- hanging the whole
      run with no output, since no ``pytest-timeout`` is configured. Reacting to the actual
      ``Show`` event cannot miss it.
    - **Why the dismiss is delayed rather than done inside the ``Show`` handler.**
      ``exec()`` is ``show()`` followed by constructing and running its nested ``QEventLoop``.
      That loop does not exist yet while ``show()`` is on the stack, so rejecting from inside
      the filter leaves nothing to make the loop return; it would still block once ``exec()``
      reached it.
    """

    def __init__(self, captured: list[QDialog]) -> None:
        super().__init__()
        self._captured = captured

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QDialog)
            and watched.objectName() == _GENERATE_ANALYSIS_OBJECT_NAME
        ):
            self._captured.append(watched)
            QTimer.singleShot(_DISMISS_DELAY_MS, watched.reject)
        return False


@pytest.fixture
def app_data_root_with_completed_run(offline_app_data_root: Path) -> Path:
    """``offline_app_data_root`` plus the one completed run the Run Analysis tab needs."""
    _seed_one_completed_run(offline_app_data_root)
    return offline_app_data_root


@pytest.fixture
def shown_generate_analysis_dialogs(qapp: QApplication) -> Generator[list[QDialog]]:
    """Every Generate Analysis dialog shown while this fixture is active, auto-dismissed.

    The filter is removed on teardown so it can never dismiss a dialog belonging to a later
    test in the same session.
    """
    captured: list[QDialog] = []
    dismisser = _CaptureAndDismissGenerateAnalysisOnShow(captured)
    qapp.installEventFilter(dismisser)
    yield captured
    qapp.removeEventFilter(dismisser)


def test_generate_analysis_button_opens_dialog_with_the_real_event_bus(
    qtbot: QtBot,
    app_data_root_with_completed_run: Path,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
    shown_generate_analysis_dialogs: list[QDialog],
) -> None:
    """Proves: STORY-118-AC-3

    A real click on Generate analysis in the fully assembled application opens the dialog
    and leaves the process running. No event bus is substituted anywhere in this test.
    """
    # Arrange
    handle = build_smoke_app()
    result_tabs = cast("QTabWidget", handle.window.findChild(QTabWidget, "result_widget.tabs"))
    run_analysis_index = next(
        index
        for index in range(result_tabs.count())
        if result_tabs.widget(index).objectName() == "run_analysis_tab_host"
    )
    QTest.mouseClick(
        result_tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=result_tabs.tabBar().tabRect(run_analysis_index).center(),
    )
    generate_button = cast(
        "QWidget",
        result_tabs.widget(run_analysis_index).findChild(
            QWidget, "run_analysis_tab.generate_button"
        ),
    )

    # Act
    QTest.mouseClick(generate_button, Qt.MouseButton.LeftButton)

    # Assert
    qtbot.waitUntil(lambda: len(shown_generate_analysis_dialogs) == 1, timeout=_DIALOG_TIMEOUT_MS)
    shutdown_handle(handle)
