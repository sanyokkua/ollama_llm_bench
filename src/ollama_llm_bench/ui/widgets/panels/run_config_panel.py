"""RunConfigPanel — tabbed left panel for run configuration (V2 redesign)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.constants import RUN_MODE_LABELS
from ollama_llm_bench.backend.core.models import (
    BenchmarkRun,
    BenchmarkRunStatus,
    ModelSelectionKey,
    PerformanceConfig,
    RunMode,
    RunStartEvent,
    RunSummary,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_STREAMING_ENABLED,
    SETTING_WARMUP_ENABLED,
)
from ollama_llm_bench.backend.services.mode_visibility_policy import (
    ModeVisibilityPolicy,
    VisibilityFeatureFlags,
)
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.control.advanced_options_widget import AdvancedOptionsWidget
from ollama_llm_bench.ui.widgets.panels.control.judge_widget import JudgeWidget
from ollama_llm_bench.ui.widgets.panels.control.performance_matrix_widget import (
    PerformanceMatrixWidget,
)
from ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget import PromptVariantsWidget
from ollama_llm_bench.ui.widgets.panels.control.run_mode_widget import RunModeWidget
from ollama_llm_bench.ui.widgets.panels.control.task_files_widget import TaskFilesWidget
from ollama_llm_bench.ui.widgets.panels.control.test_models_widget import TestModelsWidget
from ollama_llm_bench.ui.widgets.panels.resume_summary_dialog import ResumeSummaryDialog
from ollama_llm_bench.ui.widgets.panels.run_summary_dialog import RunSummaryDialog

_logger = logging.getLogger(__name__)

_TAB_NEW_BENCHMARK: Final[int] = 0
_TAB_RESUME_BENCHMARK: Final[int] = 1
_SETTING_ACTIVE_TAB: Final[str] = "ui.left_panel_active_tab"
_RUNS_TABLE_COLUMNS: Final[list[str]] = ["Run name", "Mode", "Started", "Status", "Tasks"]
_RUN_ID_ROLE: Final[int] = int(Qt.ItemDataRole.UserRole)
_RUN_STATUS_ROLE: Final[int] = int(Qt.ItemDataRole.UserRole) + 1
_NO_RUNS_TEXT: Final[str] = "No previous runs found."

_STATUS_LABEL_AND_TOOLTIP: Final[dict[BenchmarkRunStatus, tuple[str, str]]] = {
    BenchmarkRunStatus.NOT_COMPLETED: (
        "In progress / Stopped",
        "The run was stopped or interrupted. Resume to continue from where it stopped.",
    ),
    BenchmarkRunStatus.COMPLETED: (
        "Completed",
        "The run finished successfully. All tasks were processed.",
    ),
    BenchmarkRunStatus.FAILED: (
        "Failed",
        "The run hit an unrecoverable error. Open the log for details.",
    ),
    BenchmarkRunStatus.STOPPED: (
        "Stopped",
        "The run was stopped by the user. Resume to continue.",
    ),
}


def _format_timestamp(raw: str) -> str:
    """Render an ISO 8601 timestamp as 'YYYY-MM-DD HH:mm'; fall back to raw on error."""
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return raw


class RunConfigPanel(QWidget):
    """Left panel: tabbed run configuration surface.

    Tab 0 — New Benchmark: mode selection, provider/model pickers, task files,
    advanced options, and a Start button.
    Tab 1 — Resume Benchmark: previous-run list, Refresh, and Resume buttons.

    Pause and Stop are NOT on this panel — they live in the Center Panel.
    """

    def __init__(self, *, controller: RunConfigController) -> None:
        super().__init__()
        self._controller = controller
        self._policy = ModeVisibilityPolicy()

        self._build_widgets()
        self._build_layout()
        self._wire_signals()
        self._restore_state()
        self._populate_runs_table()

    # ------------------------------------------------------------------
    # Build phases
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        svc = self._controller._app_settings_service

        streaming_default = svc.get_bool(SETTING_STREAMING_ENABLED)
        warmup_default = svc.get_bool(SETTING_WARMUP_ENABLED)
        reasoning_raw = svc.get(SETTING_REASONING_EFFORT_DEFAULT)
        reasoning_default = reasoning_raw if reasoning_raw else "default"

        self._tab_widget = QTabWidget()

        self._run_mode_widget = RunModeWidget()
        self._perf_matrix = PerformanceMatrixWidget()
        self._judge_widget = JudgeWidget(controller=self._controller)
        self._test_models_widget = TestModelsWidget(controller=self._controller)
        self._prompt_variants = PromptVariantsWidget()
        self._task_files_widget = TaskFilesWidget()
        self._advanced_widget = AdvancedOptionsWidget(
            streaming_default=streaming_default,
            warmup_default=warmup_default,
            reasoning_default=reasoning_default,
        )

        self._mode_widgets: dict[str, QWidget] = {
            "performance_matrix": self._perf_matrix,
            "judge_section": self._judge_widget,
            "test_models_section": self._test_models_widget,
            "prompt_variants_section": self._prompt_variants,
            "task_files_section": self._task_files_widget,
            "advanced_section": self._advanced_widget,
        }

        self._is_running: bool = False

        self._start_btn = QPushButton("Start Benchmark")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.setToolTip("Review configuration and start a new benchmark run.")
        self._start_btn.setEnabled(False)

        self._runs_table = QTableView()
        self._runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._runs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._runs_table.setAlternatingRowColors(True)
        self._runs_table.verticalHeader().setVisible(False)

        self._refresh_runs_btn = QPushButton("Refresh")
        self._refresh_runs_btn.setToolTip("Re-query the database for previous runs.")

        self._resume_btn = QPushButton("Resume")
        self._resume_btn.setEnabled(False)
        self._resume_btn.setToolTip("Resume the selected benchmark run.")

        self._no_runs_label = QLabel(_NO_RUNS_TEXT)
        self._no_runs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_runs_label.setVisible(False)

    def _build_layout(self) -> None:
        self._new_inner = QWidget()
        inner_layout = QVBoxLayout(self._new_inner)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(6)
        inner_layout.addWidget(self._run_mode_widget)
        inner_layout.addWidget(self._perf_matrix)
        inner_layout.addWidget(self._judge_widget)
        inner_layout.addWidget(self._test_models_widget)
        inner_layout.addWidget(self._prompt_variants)
        inner_layout.addWidget(self._task_files_widget)
        inner_layout.addWidget(self._advanced_widget)
        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._new_inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        new_tab = QWidget()
        new_tab_layout = QVBoxLayout(new_tab)
        new_tab_layout.setContentsMargins(0, 0, 0, 0)
        new_tab_layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._refresh_runs_btn)
        btn_row.addWidget(self._resume_btn)

        resume_tab = QWidget()
        resume_layout = QVBoxLayout(resume_tab)
        resume_layout.setContentsMargins(4, 4, 4, 4)
        resume_layout.setSpacing(6)
        resume_layout.addWidget(QLabel("Previous Runs"))
        resume_layout.addWidget(self._runs_table)
        resume_layout.addWidget(self._no_runs_label)
        resume_layout.addLayout(btn_row)

        self._tab_widget.addTab(new_tab, "New Benchmark")
        self._tab_widget.addTab(resume_tab, "Resume Benchmark")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._tab_widget)
        root.addWidget(self._start_btn)

    def _wire_signals(self) -> None:
        self._run_mode_widget.mode_changed.connect(self._on_mode_changed)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._refresh_runs_btn.clicked.connect(self._populate_runs_table)
        self._resume_btn.clicked.connect(self._on_resume_clicked)
        self._controller.subscribe_to_benchmark_status_change(self._on_benchmark_status_changed, parent=self)
        self._controller.subscribe_to_runs_change(self._on_runs_changed, parent=self)
        self._controller.subscribe_to_app_readiness_changed(lambda _evt: self._update_start_btn(), parent=self)
        self._task_files_widget.tasks_changed.connect(self._update_start_btn)
        self._task_files_widget.tasks_changed.connect(self._on_task_files_changed)
        self._prompt_variants.variants_changed.connect(self._update_start_btn)

    def _restore_state(self) -> None:
        svc = self._controller._app_settings_service
        try:
            raw = svc.get(_SETTING_ACTIVE_TAB, default="0")
            tab_idx = int(raw) if raw else 0
        except (ValueError, TypeError):
            tab_idx = 0
        self._tab_widget.setCurrentIndex(tab_idx)
        self._start_btn.setVisible(tab_idx == _TAB_NEW_BENCHMARK)
        self._apply_mode_visibility(self._run_mode_widget.current_mode())
        self._update_start_btn()

    # ------------------------------------------------------------------
    # Mode visibility
    # ------------------------------------------------------------------

    def _apply_mode_visibility(self, mode: RunMode) -> None:
        flags = VisibilityFeatureFlags(
            judge_run_analysis_enabled=self._controller._app_settings_service.get_bool(
                SETTING_JUDGE_RUN_ANALYSIS_ENABLED
            )
        )
        visible = self._policy.get_visible_keys(mode, flags)
        for key, widget in self._mode_widgets.items():
            widget.setVisible(key in visible)
        self._new_inner.adjustSize()

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _update_start_btn(self) -> None:
        mode = self._run_mode_widget.current_mode()
        tasks_required = mode != RunMode.PERFORMANCE
        has_tasks = bool(self._task_files_widget.get_task_paths())
        verdict = self._controller.readiness_verdict(mode)
        has_variants = mode != RunMode.PROMPT_EVAL or bool(self._prompt_variants.get_variants())
        can_start = not self._is_running and verdict.is_ready and (not tasks_required or has_tasks) and has_variants
        self._start_btn.setEnabled(can_start)
        if verdict.issues:
            self._start_btn.setToolTip("\n".join(verdict.issues))
        else:
            self._start_btn.setToolTip("Start benchmark")

    def _on_mode_changed(self, mode: RunMode) -> None:
        self._apply_mode_visibility(mode)
        self._update_start_btn()

    def _on_task_files_changed(self) -> None:
        self._prompt_variants.set_task_preview_source(self._task_files_widget.get_task_paths())

    def _on_tab_changed(self, index: int) -> None:
        self._start_btn.setVisible(index == _TAB_NEW_BENCHMARK)
        svc = self._controller._app_settings_service
        try:
            svc.set(_SETTING_ACTIVE_TAB, str(index))
        except Exception:
            _logger.debug("Failed to persist active tab index", exc_info=True)

    def _on_benchmark_status_changed(self, is_running: bool) -> None:
        self._is_running = is_running
        self._update_start_btn()

    def _on_runs_changed(self, _runs: list[tuple[int, str]]) -> None:
        self._populate_runs_table()

    def _on_run_selection_changed(self) -> None:
        sel = self._runs_table.selectionModel()
        if sel is None or not sel.selectedRows():
            self._resume_btn.setEnabled(False)
            self._resume_btn.setToolTip("Select a run to resume.")
            return

        idx = sel.selectedRows()[0]
        raw_model = self._runs_table.model()
        if not isinstance(raw_model, QStandardItemModel):
            self._resume_btn.setEnabled(False)
            return

        item = raw_model.item(idx.row(), 0)
        if item is None:
            self._resume_btn.setEnabled(False)
            return

        run_id = item.data(_RUN_ID_ROLE)
        if run_id is None:
            self._resume_btn.setEnabled(False)
            return

        resumable = self._controller.is_run_resumable(run_id)
        self._resume_btn.setEnabled(resumable)
        self._resume_btn.setToolTip("Resume this run." if resumable else "Run is fully completed — no tasks to resume.")

    def _on_start_clicked(self) -> None:
        event = self._build_run_start_event()
        if event is None:
            return
        summary = self._build_run_summary()
        dlg = RunSummaryDialog(summary=summary, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._controller.handle_start_click(event)

    def _on_resume_clicked(self) -> None:
        run_id = self._selected_run_id()
        if run_id is None:
            return
        dlg = ResumeSummaryDialog(run_id=run_id, controller=self._controller, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_id = dlg.cloned_run_id if dlg.cloned_run_id is not None else run_id
        self._controller.handle_resume_run_click(target_id)

    # ------------------------------------------------------------------
    # Run-start event assembly
    # ------------------------------------------------------------------

    def _build_run_start_event(self) -> RunStartEvent | None:
        mode = self._run_mode_widget.current_mode()
        judge_provider = self._judge_widget.get_selected_provider() or ""
        judge_model = self._judge_widget.get_selected_model() or ""

        store = self._test_models_widget.get_selection_store()
        all_descriptors = store.all()
        if not all_descriptors and mode != RunMode.PERFORMANCE:
            _logger.warning("No test models selected — cannot start run")
            return None

        if mode == RunMode.PROMPT_EVAL:
            variants = self._prompt_variants.get_variants()
            if not variants:
                _logger.warning("No prompt variants defined — cannot start PROMPT_EVAL run")
                return None
        else:
            variants = []

        task_paths = tuple(self._task_files_widget.get_task_paths())
        opts = self._advanced_widget.get_effective_options()

        perf_config: PerformanceConfig | None = None
        if mode == RunMode.PERFORMANCE:
            perf_config = PerformanceConfig(
                input_sizes=tuple(self._perf_matrix.get_selected_input_sizes()),
                output_sizes=tuple(self._perf_matrix.get_selected_output_sizes()),
                repeat_count=self._perf_matrix.get_repeat_count(),
            )

        return RunStartEvent(
            run_mode=mode,
            judge_provider=judge_provider,
            judge_model=judge_model,
            test_models=tuple(all_descriptors),
            task_paths=task_paths,
            streaming_enabled=opts.streaming_enabled,
            warmup_enabled=opts.warmup_enabled,
            reasoning_effort=opts.reasoning_effort,
            performance_config=perf_config,
            prompt_variants=tuple(variants),
        )

    def _build_run_summary(self) -> RunSummary:
        """Build a RunSummary snapshot from the current widget state."""
        mode = self._run_mode_widget.current_mode()
        store = self._test_models_widget.get_selection_store()
        task_paths = list(self._task_files_widget.get_task_paths())
        opts = self._advanced_widget.get_effective_options()

        perf_input_sizes: list[str] = []
        perf_output_sizes: list[str] = []
        perf_repeats = 1
        if mode == RunMode.PERFORMANCE:
            perf_input_sizes = [str(s) for s in self._perf_matrix.get_selected_input_sizes()]
            perf_output_sizes = [str(s) for s in self._perf_matrix.get_selected_output_sizes()]
            perf_repeats = self._perf_matrix.get_repeat_count()

        return RunSummary(
            run_mode=mode,
            judge_provider_id=self._judge_widget.get_selected_provider(),
            judge_model_name=self._judge_widget.get_selected_model(),
            selected_models=[
                ModelSelectionKey(provider_id=d.provider_id, model_name=d.model_name) for d in store.all()
            ],
            task_file_paths=task_paths,
            advanced_options=opts,
            performance_input_sizes=perf_input_sizes,
            performance_output_sizes=perf_output_sizes,
            performance_repeats=perf_repeats,
            judge_run_analysis_enabled=self._controller._app_settings_service.get_bool(
                SETTING_JUDGE_RUN_ANALYSIS_ENABLED
            ),
        )

    # ------------------------------------------------------------------
    # Previous runs table
    # ------------------------------------------------------------------

    def _populate_runs_table(self) -> None:
        runs: list[BenchmarkRun] = self._controller.get_recent_runs()
        self._no_runs_label.setVisible(not runs)
        self._runs_table.setVisible(bool(runs))

        model = QStandardItemModel(len(runs), len(_RUNS_TABLE_COLUMNS))
        model.setHorizontalHeaderLabels(_RUNS_TABLE_COLUMNS)
        for row, run in enumerate(runs):
            display_name = run.run_name if run.run_name else f"Run {run.run_id}"
            name_item = QStandardItem(display_name)
            name_item.setData(run.run_id, _RUN_ID_ROLE)
            name_item.setData(run.status.value, _RUN_STATUS_ROLE)
            model.setItem(row, 0, name_item)

            mode_label = RUN_MODE_LABELS.get(run.run_mode, run.run_mode.value)
            model.setItem(row, 1, QStandardItem(mode_label))

            model.setItem(row, 2, QStandardItem(_format_timestamp(run.timestamp)))

            status_label, status_tooltip = _STATUS_LABEL_AND_TOOLTIP[run.status]
            status_item = QStandardItem(status_label)
            status_item.setToolTip(status_tooltip)
            model.setItem(row, 3, status_item)

            tasks_text = f"{run.completed_tasks} / {run.total_tasks}" if run.total_tasks > 0 else "—"
            model.setItem(row, 4, QStandardItem(tasks_text))

        self._runs_table.setModel(model)
        header = self._runs_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        sel_model = self._runs_table.selectionModel()
        if sel_model is not None:
            sel_model.selectionChanged.connect(self._on_run_selection_changed)
        self._resume_btn.setEnabled(False)

    def _selected_run_id(self) -> int | None:
        sel = self._runs_table.selectionModel()
        if sel is None or not sel.selectedRows():
            return None
        idx = sel.selectedRows()[0]
        raw_model = self._runs_table.model()
        if not isinstance(raw_model, QStandardItemModel):
            return None
        item = raw_model.item(idx.row(), 0)
        if item is None:
            return None
        return int(item.data(_RUN_ID_ROLE))
