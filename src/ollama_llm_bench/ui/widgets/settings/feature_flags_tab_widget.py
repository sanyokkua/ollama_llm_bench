"""FeatureFlagsTabWidget — General settings tab for application configuration."""

from PySide6.QtCore import QLocale, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.app_paths import ensure_log_dir, get_user_data_dir
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_AUTO_SCROLL,
    SETTING_COSINE_ENABLED,
    SETTING_COSINE_THRESHOLD_CONTAINS,
    SETTING_COSINE_THRESHOLD_COVERS,
    SETTING_COSINE_THRESHOLD_EXACT,
    SETTING_EMBEDDING_CUSTOM_PATTERNS,
    SETTING_EMBEDDING_FILTER_ENABLED,
    SETTING_JUDGE_OVERRIDE_COSINE_LOW,
    SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL,
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
    SETTING_KEYWORD_ENABLED,
    SETTING_LOG_MAX_LINES,
    SETTING_LOG_TO_FILE,
    SETTING_LOG_VERBOSITY,
    SETTING_PAUSE_ON_MODEL_SWITCH,
    SETTING_PAUSE_ON_PROVIDER_SWITCH,
    SETTING_PAUSE_ON_STAGE_SWITCH,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_RETRY_COUNT,
    SETTING_RETRY_TIMEOUT_MAX_S,
    SETTING_RETRY_TIMEOUT_MIN_S,
    SETTING_SCORE_DISPLAY_FORMAT,
    SETTING_STOP_ON_PROVIDER_ERROR,
    SETTING_STREAMING_ENABLED,
    SETTING_THEME,
    SETTING_WARMUP_ENABLED,
)


def _make_form() -> QFormLayout:
    """Create a standardised QFormLayout for settings groups."""
    form: QFormLayout = QFormLayout()
    form.setContentsMargins(8, 8, 8, 8)
    form.setSpacing(6)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


def _make_outer(summary_text: str, form: QFormLayout) -> QVBoxLayout:
    """Create an outer QVBoxLayout wrapping a summary label and a form layout."""
    outer: QVBoxLayout = QVBoxLayout()
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(6)
    outer.addWidget(_group_summary(summary_text))
    outer.addLayout(form)
    return outer


def _group_summary(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class FeatureFlagsTabWidget(QWidget):
    """General settings tab widget for configuring feature flags and application preferences.

    Provides grouped controls for inference, evaluation, benchmark events,
    logging, and display settings. All values are persisted through the
    SettingsWidgetControllerApi. Tracks dirty state and disables Save Changes
    until at least one field has changed since the last load or save.
    """

    def __init__(self, *, controller: SettingsWidgetControllerApi) -> None:
        """Initialize the General settings tab.

        Args:
            controller: Settings controller for reading and writing application settings.
        """
        super().__init__()
        self._controller: SettingsWidgetControllerApi = controller
        self._dirty_keys: set[str] = set()
        self._setup_ui()
        self._setup_signals()
        self._load_settings()

    # ------------------------------------------------------------------
    # Dirty-state API (used by SettingsDialog.closeEvent)
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """Return True if any field has been changed since the last save or load."""
        return bool(self._dirty_keys)

    def _mark_dirty(self, key: str) -> None:
        self._dirty_keys.add(key)
        self._save_button.setEnabled(True)
        self._save_button.setText("Save Changes *")

    def _clear_dirty(self) -> None:
        self._dirty_keys.clear()
        self._save_button.setEnabled(False)
        self._save_button.setText("Save Changes")

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _build_inference_group(self) -> QGroupBox:
        """Build and return the Inference settings group box."""
        self._streaming_checkbox: QCheckBox = QCheckBox()
        self._streaming_checkbox.setToolTip(
            "Stream tokens from the LLM as they arrive (captures TTFT, shows live progress in the log). "
            "Disable for sync inference (single response after completion). "
            "Some providers do not support streaming. "
            "Default for new runs unless overridden in Run Configuration → Advanced."
        )

        self._reasoning_combo: QComboBox = QComboBox()
        for label, data in [
            ("Default (model chooses)", "default"),
            ("Low", "low"),
            ("Medium", "medium"),
            ("High", "high"),
        ]:
            self._reasoning_combo.addItem(label, userData=data)
        self._reasoning_combo.setToolTip(
            "Reasoning budget for thinking-capable models (Anthropic / Gemini / qwen3-thinking / deepseek-r1). "
            "'default' lets the model choose. 'low' / 'medium' / 'high' constrain the budget. "
            "Has no effect on models without thinking blocks."
        )

        self._warmup_checkbox: QCheckBox = QCheckBox()
        self._warmup_checkbox.setToolTip(
            "Send one cheap inference per model before timed tasks. "
            "Loads the model into VRAM so the first timed task is not penalised by a cold start. "
            "Recommended on. Adds ~5-30 s per model per run."
        )

        self._retry_count_spinbox: QSpinBox = QSpinBox()
        self._retry_count_spinbox.setRange(1, 10)
        self._retry_count_spinbox.setSingleStep(1)
        self._retry_count_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._retry_count_spinbox.setToolTip(
            "Number of times to retry a failed inference call before marking the task FAILED. "
            "Each retry uses an exponential backoff between min and max timeout. Default 3."
        )

        self._retry_min_timeout_spinbox: QSpinBox = QSpinBox()
        self._retry_min_timeout_spinbox.setRange(30, 3600)
        self._retry_min_timeout_spinbox.setSingleStep(30)
        self._retry_min_timeout_spinbox.setSuffix(" s")
        self._retry_min_timeout_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._retry_min_timeout_spinbox.setToolTip(
            "Lower bound on the wait between retries. The first retry waits this duration. Default 300 s."
        )

        self._retry_max_timeout_spinbox: QSpinBox = QSpinBox()
        self._retry_max_timeout_spinbox.setRange(60, 7200)
        self._retry_max_timeout_spinbox.setSingleStep(60)
        self._retry_max_timeout_spinbox.setSuffix(" s")
        self._retry_max_timeout_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._retry_max_timeout_spinbox.setToolTip(
            "Upper bound on the wait between retries. Backoff grows exponentially but is capped here. Default 900 s."
        )

        form = _make_form()
        form.addRow("Enable streaming inference", self._streaming_checkbox)
        form.addRow("Default reasoning effort", self._reasoning_combo)
        form.addRow("Enable model warmup", self._warmup_checkbox)
        form.addRow("Retry attempts per task", self._retry_count_spinbox)
        form.addRow("Min timeout per attempt (seconds)", self._retry_min_timeout_spinbox)
        form.addRow("Max timeout (seconds)", self._retry_max_timeout_spinbox)

        group: QGroupBox = QGroupBox("Inference")
        group.setLayout(_make_outer("Settings that control how the test models run.", form))
        return group

    def _build_evaluation_group(self) -> QGroupBox:
        """Build and return the Evaluation settings group box."""
        self._cosine_enabled_checkbox: QCheckBox = QCheckBox()
        self._cosine_enabled_checkbox.setToolTip(
            "Compare the model's response to the golden answer via embedding cosine similarity. "
            "Auto-passes/fails high-confidence cases without calling the judge. "
            "Skipped for code, code review, and reasoning tasks regardless of this setting."
        )

        self._keyword_enabled_checkbox: QCheckBox = QCheckBox()
        self._keyword_enabled_checkbox.setToolTip(
            "Hard-fail tasks whose response misses required exact terms or contains forbidden terms "
            "(per task definition). Skipped for tasks that declare no required_terms."
        )

        self._cosine_threshold_exact_spinbox: QDoubleSpinBox = QDoubleSpinBox()
        self._cosine_threshold_exact_spinbox.setRange(0.0, 1.0)
        self._cosine_threshold_exact_spinbox.setSingleStep(0.05)
        self._cosine_threshold_exact_spinbox.setDecimals(2)
        self._cosine_threshold_exact_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._cosine_threshold_exact_spinbox.setLocale(QLocale.c())
        self._cosine_threshold_exact_spinbox.setToolTip(
            "Cosine similarity ≥ this value auto-passes the task without calling the judge. "
            "Lower than this triggers the judge. Higher = stricter pass criterion. "
            "Sensible range 0.85-0.95. Default 0.92."
        )

        self._cosine_threshold_contains_spinbox: QDoubleSpinBox = QDoubleSpinBox()
        self._cosine_threshold_contains_spinbox.setRange(0.0, 1.0)
        self._cosine_threshold_contains_spinbox.setSingleStep(0.05)
        self._cosine_threshold_contains_spinbox.setDecimals(2)
        self._cosine_threshold_contains_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._cosine_threshold_contains_spinbox.setLocale(QLocale.c())
        self._cosine_threshold_contains_spinbox.setToolTip(
            "Same as above but for tasks where the golden answer is a key phrase the response must include. "
            "Sensible range 0.75-0.90. Default 0.85."
        )

        self._cosine_threshold_covers_spinbox: QDoubleSpinBox = QDoubleSpinBox()
        self._cosine_threshold_covers_spinbox.setRange(0.0, 1.0)
        self._cosine_threshold_covers_spinbox.setSingleStep(0.05)
        self._cosine_threshold_covers_spinbox.setDecimals(2)
        self._cosine_threshold_covers_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._cosine_threshold_covers_spinbox.setLocale(QLocale.c())
        self._cosine_threshold_covers_spinbox.setToolTip(
            "Same as above but for long-form tasks where the response should cover the semantic content "
            "of the golden answer. Sensible range 0.65-0.80. Default 0.75."
        )

        cosine_explainer = QLabel(
            "Cosine similarity ranges from 0 (unrelated) to 1 (identical). "
            "Above 0.85 = very similar. 0.50-0.85 = related. Below 0.50 = unrelated. "
            "Tune carefully — too high = misses correct answers; too low = lets weak answers pass."
        )
        cosine_explainer.setWordWrap(True)

        form = _make_form()
        form.addRow("Enable Layer 3 (cosine similarity)", self._cosine_enabled_checkbox)
        form.addRow("Enable Layer 2 (keyword verification)", self._keyword_enabled_checkbox)
        form.addRow("Auto-pass threshold for response_scope: exact", self._cosine_threshold_exact_spinbox)
        form.addRow("Auto-pass threshold for response_scope: contains", self._cosine_threshold_contains_spinbox)
        form.addRow("Auto-pass threshold for response_scope: covers", self._cosine_threshold_covers_spinbox)

        outer = _make_outer(
            "Layer 2 and Layer 3 evaluation behaviour. Layer 1 (rule-based) and Layer 4 (judge) cannot be disabled.",
            form,
        )
        outer.insertWidget(1, cosine_explainer)

        group: QGroupBox = QGroupBox("Evaluation")
        group.setLayout(outer)
        return group

    def _build_events_group(self) -> QGroupBox:
        """Build and return the Benchmark Events settings group box."""
        self._pause_provider_checkbox: QCheckBox = QCheckBox()
        self._pause_provider_checkbox.setToolTip(
            "When the run finishes all tasks for one provider and starts the next, pause and wait for you "
            "to click Resume. Useful when you want to start the next provider's local model manually."
        )

        self._pause_model_checkbox: QCheckBox = QCheckBox()
        self._pause_model_checkbox.setToolTip("Pause between every model. Use sparingly — large runs become tedious.")

        self._pause_stage_checkbox: QCheckBox = QCheckBox()
        self._pause_stage_checkbox.setToolTip(
            "Pause between Initializing → Benchmarking → Judging → Finished. Use to inspect intermediate state."
        )

        self._stop_on_error_checkbox: QCheckBox = QCheckBox()
        self._stop_on_error_checkbox.setToolTip(
            "During Benchmarking, before each provider group the run pings the provider. "
            "If unhealthy, the run stops and remaining tasks are kept as NOT_COMPLETED for resume."
        )

        form = _make_form()
        form.addRow("Pause when moving to the next provider", self._pause_provider_checkbox)
        form.addRow("Pause when moving to the next model", self._pause_model_checkbox)
        form.addRow("Pause between pipeline stages", self._pause_stage_checkbox)
        form.addRow("Stop the run if a provider's health check fails", self._stop_on_error_checkbox)

        group: QGroupBox = QGroupBox("Benchmark Events")
        group.setLayout(_make_outer("Controls whether the run pauses or stops at key transition points.", form))
        return group

    def _build_logging_group(self) -> QGroupBox:
        """Build and return the Logging settings group box."""
        self._log_to_file_checkbox: QCheckBox = QCheckBox()
        self._log_to_file_checkbox.setToolTip(
            "In addition to the in-app log panel, write each run's log to a file named "
            "`benchmark_<run_id>_<timestamp>.log` in the logs folder."
        )

        self._log_verbosity_combo: QComboBox = QComboBox()
        for label, data in [
            ("Minimal", "minimal"),
            ("Normal", "normal"),
            ("Verbose", "verbose"),
        ]:
            self._log_verbosity_combo.addItem(label, userData=data)
        self._log_verbosity_combo.setToolTip(
            "How much detail the log panel shows: Minimal = task starts + summaries only; "
            "Normal = include prompts and judge results (collapsed); "
            "Verbose = expand everything by default. "
            "The toolbar in the Center Panel can override per session."
        )

        self._log_max_lines_spinbox: QSpinBox = QSpinBox()
        self._log_max_lines_spinbox.setRange(100, 100000)
        self._log_max_lines_spinbox.setSingleStep(100)
        self._log_max_lines_spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self._log_max_lines_spinbox.setToolTip(
            "Maximum log entries kept in memory. Older entries are trimmed from the top when this limit is "
            "exceeded. Higher = more scroll-back history but more RAM. Default 100 000."
        )

        self._auto_scroll_checkbox: QCheckBox = QCheckBox()
        self._auto_scroll_checkbox.setToolTip(
            "Automatically scroll to the latest entry. "
            "Disables itself when you scroll up manually; re-enables when you scroll back to the bottom."
        )

        self._open_log_folder_btn: QPushButton = QPushButton("Open log folder")
        self._open_log_folder_btn.setToolTip("Open the OS file browser at the log directory.")

        self._settings_path_edit: QLineEdit = QLineEdit()
        self._settings_path_edit.setReadOnly(True)
        self._settings_path_edit.setText(str(get_user_data_dir()))
        self._settings_path_edit.setToolTip("Absolute path to the application settings folder.")

        self._copy_path_btn: QToolButton = QToolButton()
        self._copy_path_btn.setText("Copy")
        self._copy_path_btn.setToolTip("Copy the settings folder path to the clipboard.")

        folder_row: QHBoxLayout = QHBoxLayout()
        folder_row.addWidget(QLabel("Log folder:"))
        folder_row.addWidget(self._open_log_folder_btn)
        folder_row.addStretch()

        path_row: QHBoxLayout = QHBoxLayout()
        path_row.addWidget(QLabel("Settings folder:"))
        path_row.addWidget(self._settings_path_edit)
        path_row.addWidget(self._copy_path_btn)

        form = _make_form()
        form.addRow("Write log to file", self._log_to_file_checkbox)
        form.addRow("Default log verbosity", self._log_verbosity_combo)
        form.addRow("Log buffer (lines)", self._log_max_lines_spinbox)
        form.addRow("Auto-scroll log panel", self._auto_scroll_checkbox)
        form.addRow(folder_row)
        form.addRow(path_row)

        group: QGroupBox = QGroupBox("Logging")
        group.setLayout(_make_outer("Log output destination, verbosity level, and panel behaviour.", form))
        return group

    def _build_display_group(self) -> QGroupBox:
        """Build and return the Display settings group box."""
        self._theme_combo: QComboBox = QComboBox()
        for label, data in [
            ("System (follows OS)", "system"),
            ("Dark", "dark"),
            ("Light", "light"),
        ]:
            self._theme_combo.addItem(label, userData=data)
        self._theme_combo.setToolTip(
            "`System` follows your OS dark/light mode and switches automatically. "
            "`Dark` and `Light` lock to the chosen theme."
        )

        self._score_format_combo: QComboBox = QComboBox()
        for label, data in [
            ("Decimal · 0.85", "decimal"),
            ("Percent · 85%", "percent"),
            ("Both · 0.85 / 85%", "both"),
        ]:
            self._score_format_combo.addItem(label, userData=data)
        self._score_format_combo.setToolTip(
            "How scores are shown in tables and charts. "
            "Underlying values are always 0.00-1.00 — only the display changes."
        )

        score_note = QLabel(
            "Underlying scores are always stored as 0.00-1.00. "
            "This setting only affects how they are rendered in the Summary, Detailed, and Charts panels."
        )
        score_note.setWordWrap(True)

        form = _make_form()
        form.addRow("Theme", self._theme_combo)
        form.addRow("Score display format", self._score_format_combo)

        outer = _make_outer("Visual appearance and score rendering options.", form)
        outer.addWidget(score_note)

        group: QGroupBox = QGroupBox("Display")
        group.setLayout(outer)
        return group

    def _build_embedding_group(self) -> QGroupBox:
        """Build and return the Embedding Models settings group box."""
        self._embedding_filter_checkbox: QCheckBox = QCheckBox()
        self._embedding_filter_checkbox.setToolTip(
            "When checked, models whose names suggest they are embedding models "
            "(`embed`, `bge`, `nomic`, `e5`, plus your custom patterns) are hidden from "
            "Test Models and Judge model dropdowns."
        )

        self._embedding_patterns_edit: QLineEdit = QLineEdit()
        self._embedding_patterns_edit.setPlaceholderText("e.g. my-embed, custom-vec")
        self._embedding_patterns_edit.setToolTip(
            "Substrings; case-insensitive; comma-separated. Example: `my-embed, custom-vec`. "
            "Models whose names contain any of these are hidden when filtering is enabled."
        )

        form = _make_form()
        form.addRow("Hide embedding models from model checklists", self._embedding_filter_checkbox)
        form.addRow("Additional patterns (comma-separated)", self._embedding_patterns_edit)

        group: QGroupBox = QGroupBox("Embedding Models")
        group.setLayout(_make_outer("Controls which models appear in the model selection lists.", form))
        return group

    def _build_run_analysis_group(self) -> QGroupBox:
        """Build and return the Run-level analysis settings group box."""
        self._judge_run_analysis_checkbox: QCheckBox = QCheckBox()
        self._judge_run_analysis_checkbox.setToolTip(
            "After a Performance or Speed run finishes benchmarking, call the judge model once to "
            "produce a throughput analysis stored in benchmark_runs.perf_analysis_result and shown "
            "in the Judge Analysis tab. Adds one LLM call per run; requires a judge model to be "
            "selected in Run Configuration."
        )

        form = _make_form()
        form.addRow("Generate run-level analysis with the judge model", self._judge_run_analysis_checkbox)

        group: QGroupBox = QGroupBox("Run-level analysis")
        group.setLayout(
            _make_outer(
                "When enabled, the judge model produces a run-level throughput analysis after "
                "Performance and Speed runs. The analysis appears in the Judge Analysis tab.",
                form,
            )
        )
        return group

    def _build_grading_overrides_group(self) -> QGroupBox:
        """Build and return the Grading-mode judge overrides settings group box."""
        self._judge_override_keyword_checkbox: QCheckBox = QCheckBox()
        self._judge_override_keyword_checkbox.setToolTip(
            "Full Grading / Prompt Eval only. When Layer 2 (keyword verification) hard-fails a task, "
            "also call the judge for analytical context. The judge reasoning is captured in the DB "
            "but does not change the final verdict. Increases run time."
        )

        self._judge_override_cosine_checkbox: QCheckBox = QCheckBox()
        self._judge_override_cosine_checkbox.setToolTip(
            "Full Grading / Prompt Eval only. When Layer 3 (cosine similarity) produces a conclusive "
            "verdict, also call the judge for reasoning. Useful for auditing cosine decisions. "
            "Increases run time."
        )

        form = _make_form()
        form.addRow("When Layer 2 keyword check fails, also call the judge", self._judge_override_keyword_checkbox)
        form.addRow(
            "When Layer 3 cosine score is conclusive, also call the judge for reasoning",
            self._judge_override_cosine_checkbox,
        )

        group: QGroupBox = QGroupBox("Grading-mode judge overrides (Full Grading / Prompt Eval only)")
        group.setLayout(
            _make_outer(
                "Override flags for Full Grading and Prompt Eval modes. Each flag forces an additional "
                "judge call after the named layer resolves. Does not affect Performance or Speed runs.",
                form,
            )
        )
        return group

    def _setup_ui(self) -> None:
        """Construct all child widgets, scroll area, and button row."""
        inner_layout: QVBoxLayout = QVBoxLayout()
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(8)
        inner_layout.addWidget(self._build_inference_group())
        inner_layout.addWidget(self._build_evaluation_group())
        inner_layout.addWidget(self._build_events_group())
        inner_layout.addWidget(self._build_logging_group())
        inner_layout.addWidget(self._build_display_group())
        inner_layout.addWidget(self._build_embedding_group())
        inner_layout.addWidget(self._build_run_analysis_group())
        inner_layout.addWidget(self._build_grading_overrides_group())
        inner_layout.addStretch()

        inner_container: QWidget = QWidget()
        inner_container.setLayout(inner_layout)

        scroll: QScrollArea = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner_container)

        self._save_button: QPushButton = QPushButton("Save Changes")
        self._save_button.setEnabled(False)
        self._reset_button: QPushButton = QPushButton("Reset to Defaults")

        button_row_layout: QHBoxLayout = QHBoxLayout()
        button_row_layout.addWidget(self._save_button)
        button_row_layout.addWidget(self._reset_button)
        button_row_layout.addStretch()

        button_row_container: QWidget = QWidget()
        button_row_container.setLayout(button_row_layout)

        root: QVBoxLayout = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(scroll)
        root.addWidget(button_row_container)

    def _setup_signals(self) -> None:
        """Wire button click signals and input-change signals to handler slots."""
        self._save_button.clicked.connect(self._save_settings)
        self._reset_button.clicked.connect(self._reset_to_defaults)
        self._retry_min_timeout_spinbox.valueChanged.connect(self._clamp_max_timeout)

        self._open_log_folder_btn.clicked.connect(self._open_log_folder)
        self._copy_path_btn.clicked.connect(self._copy_settings_path)

        # Dirty-state wiring — each input marks its corresponding setting key dirty on change
        self._streaming_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_STREAMING_ENABLED))
        self._reasoning_combo.currentIndexChanged.connect(lambda _: self._mark_dirty(SETTING_REASONING_EFFORT_DEFAULT))
        self._warmup_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_WARMUP_ENABLED))
        self._retry_count_spinbox.valueChanged.connect(lambda _: self._mark_dirty(SETTING_RETRY_COUNT))
        self._retry_min_timeout_spinbox.valueChanged.connect(lambda _: self._mark_dirty(SETTING_RETRY_TIMEOUT_MIN_S))
        self._retry_max_timeout_spinbox.valueChanged.connect(lambda _: self._mark_dirty(SETTING_RETRY_TIMEOUT_MAX_S))

        self._cosine_enabled_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_COSINE_ENABLED))
        self._keyword_enabled_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_KEYWORD_ENABLED))
        self._cosine_threshold_exact_spinbox.valueChanged.connect(
            lambda _: self._mark_dirty(SETTING_COSINE_THRESHOLD_EXACT)
        )
        self._cosine_threshold_contains_spinbox.valueChanged.connect(
            lambda _: self._mark_dirty(SETTING_COSINE_THRESHOLD_CONTAINS)
        )
        self._cosine_threshold_covers_spinbox.valueChanged.connect(
            lambda _: self._mark_dirty(SETTING_COSINE_THRESHOLD_COVERS)
        )

        self._pause_provider_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_PAUSE_ON_PROVIDER_SWITCH))
        self._pause_model_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_PAUSE_ON_MODEL_SWITCH))
        self._pause_stage_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_PAUSE_ON_STAGE_SWITCH))
        self._stop_on_error_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_STOP_ON_PROVIDER_ERROR))

        self._log_to_file_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_LOG_TO_FILE))
        self._log_verbosity_combo.currentIndexChanged.connect(lambda _: self._mark_dirty(SETTING_LOG_VERBOSITY))
        self._log_max_lines_spinbox.valueChanged.connect(lambda _: self._mark_dirty(SETTING_LOG_MAX_LINES))
        self._auto_scroll_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_AUTO_SCROLL))

        self._theme_combo.currentIndexChanged.connect(lambda _: self._mark_dirty(SETTING_THEME))
        self._score_format_combo.currentIndexChanged.connect(lambda _: self._mark_dirty(SETTING_SCORE_DISPLAY_FORMAT))

        self._embedding_filter_checkbox.toggled.connect(lambda _: self._mark_dirty(SETTING_EMBEDDING_FILTER_ENABLED))
        self._embedding_patterns_edit.textChanged.connect(lambda _: self._mark_dirty(SETTING_EMBEDDING_CUSTOM_PATTERNS))

        self._judge_run_analysis_checkbox.toggled.connect(
            lambda _: self._mark_dirty(SETTING_JUDGE_RUN_ANALYSIS_ENABLED)
        )
        self._judge_override_keyword_checkbox.toggled.connect(
            lambda _: self._mark_dirty(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL)
        )
        self._judge_override_cosine_checkbox.toggled.connect(
            lambda _: self._mark_dirty(SETTING_JUDGE_OVERRIDE_COSINE_LOW)
        )

    def _clamp_max_timeout(self, min_value: int) -> None:
        """Ensure max timeout is always >= min timeout."""
        if self._retry_max_timeout_spinbox.value() < min_value:
            self._retry_max_timeout_spinbox.setValue(min_value)

    # ------------------------------------------------------------------
    # Load / Save / Reset
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        """Populate all widgets from current controller settings."""
        c = self._controller

        stored = c.get_setting(SETTING_REASONING_EFFORT_DEFAULT) or "default"
        idx = self._reasoning_combo.findData(stored)
        self._reasoning_combo.setCurrentIndex(max(0, idx))
        self._streaming_checkbox.setChecked(c.get_setting_bool(SETTING_STREAMING_ENABLED, default=True))
        self._warmup_checkbox.setChecked(c.get_setting_bool(SETTING_WARMUP_ENABLED, default=True))
        self._retry_count_spinbox.setValue(c.get_setting_int(SETTING_RETRY_COUNT, default=3))
        self._retry_min_timeout_spinbox.setValue(c.get_setting_int(SETTING_RETRY_TIMEOUT_MIN_S, default=300))
        self._retry_max_timeout_spinbox.setValue(c.get_setting_int(SETTING_RETRY_TIMEOUT_MAX_S, default=900))

        self._cosine_enabled_checkbox.setChecked(c.get_setting_bool(SETTING_COSINE_ENABLED, default=True))
        self._keyword_enabled_checkbox.setChecked(c.get_setting_bool(SETTING_KEYWORD_ENABLED, default=True))
        self._cosine_threshold_exact_spinbox.setValue(c.get_setting_float(SETTING_COSINE_THRESHOLD_EXACT, default=0.92))
        self._cosine_threshold_contains_spinbox.setValue(
            c.get_setting_float(SETTING_COSINE_THRESHOLD_CONTAINS, default=0.85)
        )
        self._cosine_threshold_covers_spinbox.setValue(
            c.get_setting_float(SETTING_COSINE_THRESHOLD_COVERS, default=0.75)
        )

        self._pause_provider_checkbox.setChecked(c.get_setting_bool(SETTING_PAUSE_ON_PROVIDER_SWITCH, default=False))
        self._pause_model_checkbox.setChecked(c.get_setting_bool(SETTING_PAUSE_ON_MODEL_SWITCH, default=False))
        self._pause_stage_checkbox.setChecked(c.get_setting_bool(SETTING_PAUSE_ON_STAGE_SWITCH, default=False))
        self._stop_on_error_checkbox.setChecked(c.get_setting_bool(SETTING_STOP_ON_PROVIDER_ERROR, default=False))

        self._log_to_file_checkbox.setChecked(c.get_setting_bool(SETTING_LOG_TO_FILE, default=False))
        stored = c.get_setting(SETTING_LOG_VERBOSITY) or "verbose"
        idx = self._log_verbosity_combo.findData(stored)
        self._log_verbosity_combo.setCurrentIndex(max(0, idx))
        self._log_max_lines_spinbox.setValue(c.get_setting_int(SETTING_LOG_MAX_LINES, default=10000))
        self._auto_scroll_checkbox.setChecked(c.get_setting_bool(SETTING_AUTO_SCROLL, default=True))

        stored = c.get_setting(SETTING_THEME) or "system"
        idx = self._theme_combo.findData(stored)
        self._theme_combo.setCurrentIndex(max(0, idx))
        stored = c.get_setting(SETTING_SCORE_DISPLAY_FORMAT) or "decimal"
        idx = self._score_format_combo.findData(stored)
        self._score_format_combo.setCurrentIndex(max(0, idx))

        self._embedding_filter_checkbox.setChecked(c.get_setting_bool(SETTING_EMBEDDING_FILTER_ENABLED, default=False))
        self._embedding_patterns_edit.setText(c.get_setting(SETTING_EMBEDDING_CUSTOM_PATTERNS) or "")

        self._judge_run_analysis_checkbox.setChecked(
            c.get_setting_bool(SETTING_JUDGE_RUN_ANALYSIS_ENABLED, default=False)
        )
        self._judge_override_keyword_checkbox.setChecked(
            c.get_setting_bool(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL, default=False)
        )
        self._judge_override_cosine_checkbox.setChecked(
            c.get_setting_bool(SETTING_JUDGE_OVERRIDE_COSINE_LOW, default=False)
        )

        self._clear_dirty()

    def _save_settings(self) -> None:
        """Persist only dirty field values to application settings via the controller."""
        if not self._dirty_keys:
            return
        c = self._controller
        saved_keys: list[str] = []

        def _save_if_dirty(key: str, value: str) -> None:
            if key in self._dirty_keys:
                c.set_setting(key, value)
                saved_keys.append(key)

        _save_if_dirty(SETTING_STREAMING_ENABLED, "true" if self._streaming_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_REASONING_EFFORT_DEFAULT, self._reasoning_combo.currentData() or "default")
        _save_if_dirty(SETTING_WARMUP_ENABLED, "true" if self._warmup_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_RETRY_COUNT, str(self._retry_count_spinbox.value()))
        _save_if_dirty(SETTING_RETRY_TIMEOUT_MIN_S, str(self._retry_min_timeout_spinbox.value()))
        _save_if_dirty(SETTING_RETRY_TIMEOUT_MAX_S, str(self._retry_max_timeout_spinbox.value()))
        _save_if_dirty(SETTING_COSINE_ENABLED, "true" if self._cosine_enabled_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_KEYWORD_ENABLED, "true" if self._keyword_enabled_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_COSINE_THRESHOLD_EXACT, f"{self._cosine_threshold_exact_spinbox.value():.2f}")
        _save_if_dirty(SETTING_COSINE_THRESHOLD_CONTAINS, f"{self._cosine_threshold_contains_spinbox.value():.2f}")
        _save_if_dirty(SETTING_COSINE_THRESHOLD_COVERS, f"{self._cosine_threshold_covers_spinbox.value():.2f}")
        _save_if_dirty(
            SETTING_PAUSE_ON_PROVIDER_SWITCH, "true" if self._pause_provider_checkbox.isChecked() else "false"
        )
        _save_if_dirty(SETTING_PAUSE_ON_MODEL_SWITCH, "true" if self._pause_model_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_PAUSE_ON_STAGE_SWITCH, "true" if self._pause_stage_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_STOP_ON_PROVIDER_ERROR, "true" if self._stop_on_error_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_LOG_TO_FILE, "true" if self._log_to_file_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_LOG_VERBOSITY, self._log_verbosity_combo.currentData() or "verbose")
        _save_if_dirty(SETTING_LOG_MAX_LINES, str(self._log_max_lines_spinbox.value()))
        _save_if_dirty(SETTING_AUTO_SCROLL, "true" if self._auto_scroll_checkbox.isChecked() else "false")
        _save_if_dirty(SETTING_THEME, self._theme_combo.currentData() or "system")
        _save_if_dirty(SETTING_SCORE_DISPLAY_FORMAT, self._score_format_combo.currentData() or "decimal")
        _save_if_dirty(
            SETTING_EMBEDDING_FILTER_ENABLED,
            "true" if self._embedding_filter_checkbox.isChecked() else "false",
        )
        _save_if_dirty(SETTING_EMBEDDING_CUSTOM_PATTERNS, self._embedding_patterns_edit.text().strip())
        _save_if_dirty(
            SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
            "true" if self._judge_run_analysis_checkbox.isChecked() else "false",
        )
        _save_if_dirty(
            SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL,
            "true" if self._judge_override_keyword_checkbox.isChecked() else "false",
        )
        _save_if_dirty(
            SETTING_JUDGE_OVERRIDE_COSINE_LOW,
            "true" if self._judge_override_cosine_checkbox.isChecked() else "false",
        )

        if saved_keys:
            c.emit_settings_changed(saved_keys)

        self._clear_dirty()

    def save_settings(self) -> None:
        """Public entry point for save — used by SettingsDialog.closeEvent."""
        self._save_settings()

    def _restore_save_button(self) -> None:
        """Restore the Save button to its default state after the feedback delay."""
        if not self.is_dirty:
            self._save_button.setText("Save Changes")
            self._save_button.setEnabled(False)

    def _reset_to_defaults(self) -> None:
        """Reset all settings to factory defaults after user confirmation."""
        answer = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all General settings to defaults? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._controller.reset_settings()
        self._load_settings()
        from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

        self._controller.emit_settings_changed(list(_DEFAULTS.keys()))

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _open_log_folder(self) -> None:
        log_dir = ensure_log_dir()
        url = QUrl.fromLocalFile(str(log_dir))
        if not QDesktopServices.openUrl(url):
            QMessageBox.information(self, "Log Folder", f"Log folder path:\n{log_dir}")

    def _copy_settings_path(self) -> None:
        path = str(get_user_data_dir())
        QApplication.clipboard().setText(path)

    # ------------------------------------------------------------------
    # Unused timer reference kept to avoid garbage-collection of QTimer
    # ------------------------------------------------------------------
    _timer_ref: QTimer | None = None
