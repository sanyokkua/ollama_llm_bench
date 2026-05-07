"""LogWidget V2 — event-bus-driven structured HTML log panel with 20 Hz streaming buffer."""

import logging
import time
from typing import Final

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, EventBus
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkResultStatus,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    EvalVerdict,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeEvalStartedEvent,
    ModeSwitchEvent,
    PipelineStage,
    StreamingChunkEvent,
    TaskCompletedEvent,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_LOG_MAX_LINES,
    SETTING_LOG_VERBOSITY,
    SETTING_STREAMING_ENABLED,
)
from ollama_llm_bench.backend.utils.time_utils import format_compact_duration
from ollama_llm_bench.ui.style.chart_colors import JUDGE_LOG_COLOR
from ollama_llm_bench.ui.style.theme_loader import get_color
from ollama_llm_bench.ui.style.tokens import SHARED_TOKENS

logger = logging.getLogger(__name__)

_MONO_FONT_CSS: Final[str] = SHARED_TOKENS["font_mono"]

_DEFAULT_MAX_LINES: Final[int] = 10_000
_TIMER_INTERVAL_MS: Final[int] = 50
_SCROLL_BOTTOM_THRESHOLD: Final[int] = 20


class LogWidget(QWidget):
    """Log display widget with 20 Hz streaming buffer, per-entry-type HTML colour coding,
    scrollback cap, and auto-scroll with jump-to-bottom affordance."""

    def __init__(self, *, event_bus: EventBus, app_settings: AppSettingsServiceApi) -> None:
        """Initialize the log widget.

        Args:
            event_bus: Application event bus for subscribing to pipeline events.
            app_settings: Service for reading typed application settings.
        """
        super().__init__()
        _theme = "dark"
        self._color_stream_chunk: str = get_color(_theme, "text_muted")
        self._color_inference_complete: str = get_color(_theme, "primary")
        self._color_judge_pass: str = get_color(_theme, "success_text")
        self._color_judge_fail: str = get_color(_theme, "failure_text")
        self._color_secondary: str = get_color(_theme, "text_secondary")
        self._color_border: str = get_color(_theme, "border")
        self._color_accent: str = get_color(_theme, "primary")
        self._event_bus = event_bus
        self._app_settings = app_settings
        self._chunk_buffer: list[str] = []
        self._had_streaming_output: bool = False
        self._response_label_pending: bool = False
        self._accumulated_stream: str = ""
        self._auto_scroll: bool = True
        self._streaming_display_enabled: bool = True
        self._verbosity_level: int = 1
        self._search_text: str = ""
        self._inference_wall_time: float = 0.0
        # Buffer of (min_verbosity, search_key, html) for retroactive filtering.
        self._log_entries: list[tuple[int, str, str]] = []
        self._create_widgets()
        self._configure_widgets()
        self._build_layout()
        self._subscribe_events()

    def _create_widgets(self) -> None:
        """Create all child widgets."""
        self._text_edit = QTextEdit()
        self._clean_button = QPushButton("🗑 Clear")
        self._jump_button = QPushButton("↓ Jump to bottom")
        self._drain_timer = QTimer()
        self._verbosity_combo = QComboBox()
        self._search_edit = QLineEdit()

    def _configure_widgets(self) -> None:
        """Configure widget properties after creation."""
        self._text_edit.setReadOnly(True)
        self._text_edit.setObjectName("log_text_edit")
        self._jump_button.setVisible(False)
        self._jump_button.setToolTip("Scroll the log view to the most recent entry.")
        self._drain_timer.setInterval(_TIMER_INTERVAL_MS)
        self._verbosity_combo.addItems(["Minimal", "Normal", "Verbose"])
        self._verbosity_combo.setToolTip(
            "Filter log entries by severity level."
            " Only entries at or above the selected level are shown. Takes effect immediately."
        )
        saved_verbosity = self._app_settings.get(SETTING_LOG_VERBOSITY, "verbose") or "verbose"
        _verbosity_map: dict[str, int] = {"minimal": 0, "normal": 1, "verbose": 2}
        init_index = _verbosity_map.get(saved_verbosity, 2)
        self._verbosity_combo.setCurrentIndex(init_index)
        self._verbosity_level = init_index
        self._search_edit.setPlaceholderText("Filter log…")
        self._search_edit.setToolTip(
            "Type to filter log entries by text content. The filter is case-insensitive and updates as you type."
        )
        self._search_edit.setClearButtonEnabled(True)
        self._clean_button.setToolTip(
            "Clear all log entries from the display. Does not affect logs already written to the log file on disk."
        )

    def _build_layout(self) -> None:
        """Compose child widgets into the outer layout."""
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Verbosity:"))
        filter_bar.addWidget(self._verbosity_combo)
        filter_bar.addStretch()
        filter_bar.addWidget(QLabel("Search:"))
        filter_bar.addWidget(self._search_edit)
        filter_bar.addWidget(self._clean_button)

        jump_row = QHBoxLayout()
        jump_row.addStretch()
        jump_row.addWidget(self._jump_button)

        layout = QVBoxLayout()
        layout.addLayout(filter_bar)
        layout.addWidget(self._text_edit, 1)
        layout.addLayout(jump_row)
        self.setLayout(layout)

    def _subscribe_events(self) -> None:
        """Connect all EventBus subscriptions and widget signals."""
        self._event_bus.subscribe_to_inference_started(self._on_inference_started)
        self._event_bus.subscribe_to_streaming_chunk(self._on_streaming_chunk)
        self._event_bus.subscribe_to_task_completed(self._on_task_completed)
        self._event_bus.subscribe_to_judge_completed(self._on_judge_completed)
        self._event_bus.subscribe_to_judge_eval_started(self._on_judge_eval_started)
        self._event_bus.subscribe_to_mode_switch(self._on_mode_switch)
        self._event_bus.subscribe_to_benchmark_started(self._on_benchmark_started)
        self._event_bus.subscribe_to_benchmark_finished(self._on_benchmark_finished)
        self._event_bus.subscribe_to_benchmark_stopped(self._on_benchmark_stopped)
        self._event_bus.subscribe_to_log_clean(self._clear_log_display)
        self._event_bus.subscribe_to_log_append(self._append_plain)
        self._clean_button.clicked.connect(self._clear_log_display)
        self._jump_button.clicked.connect(self._jump_to_bottom)
        scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
        if scrollbar:
            scrollbar.valueChanged.connect(self._on_scroll_changed)
        self._drain_timer.timeout.connect(self._drain_chunk_buffer)
        self._verbosity_combo.currentIndexChanged.connect(self._on_verbosity_changed)
        self._search_edit.textChanged.connect(self._on_search_changed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_benchmark_started(self, event: BenchmarkStartedEvent) -> None:
        """Handle benchmark start: clear log, enable auto-scroll, start drain timer."""
        self._clear_log_display()
        self._streaming_display_enabled = self._app_settings.get_bool(SETTING_STREAMING_ENABLED, True)
        self._auto_scroll = True
        self._jump_button.setVisible(False)
        if self._verbosity_level >= 1:
            self._drain_timer.start()

    def _on_benchmark_finished(self, event: BenchmarkFinishedEvent) -> None:
        """Handle benchmark completion: stop timer, drain buffer, append summary."""
        self._drain_timer.stop()
        self._drain_chunk_buffer()
        summary = (
            f"<span style='color:{self._color_secondary};'>"
            f"&#x2713; Run {event.run_id} finished — "
            f"{event.completed_count} completed, {event.failed_count} failed"
            f"</span>"
        )
        key = f"run {event.run_id} finished"
        self._append_html(summary, min_verbosity=1, search_key=key)

    def _on_benchmark_stopped(self, event: BenchmarkStoppedEvent) -> None:
        """Handle benchmark stop: stop timer, drain buffer, append stopped message."""
        self._drain_timer.stop()
        self._drain_chunk_buffer()
        msg = f"<span style='color:{self._color_secondary};'>&#x25A0; Run {event.run_id} stopped</span>"
        self._append_html(msg, min_verbosity=1, search_key=f"run {event.run_id} stopped")

    def _on_inference_started(self, event: InferenceStartedEvent) -> None:
        """Render task header before streaming output; show prompt at Verbose."""
        display_label = event.model.display_label
        task = event.task_id
        search_key = f"{display_label} {task}"
        if not self._passes_search(search_key):
            return
        if not self._text_edit.document().isEmpty():
            self._append_html(
                f"<hr style='border:0;border-top:1px solid {self._color_border};margin:6px 0;'>",
                min_verbosity=1,
                search_key=search_key,
            )
        header = f"<b style='color:{self._color_secondary};'>&#9654; {display_label} / {task}</b>"
        self._append_html(header, min_verbosity=1, search_key=search_key)
        self._inference_wall_time = time.time()
        start_str = time.strftime("%H:%M:%S", time.localtime(self._inference_wall_time))
        meta_html = f"<span style='color:{self._color_secondary};font-size:10px;'>Start: {start_str}</span>"
        self._append_html(meta_html, min_verbosity=1, search_key=search_key)
        self._response_label_pending = True
        prompt = event.user_prompt[:800].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        prompt_html = (
            f"<b style='color:{self._color_secondary};font-size:10px;'>PROMPT</b><br>"
            f"<span style='color:{self._color_secondary};font-size:11px;'>{prompt}</span>"
        )
        self._append_html(prompt_html, min_verbosity=2, search_key=search_key)

    def _on_streaming_chunk(self, event: StreamingChunkEvent) -> None:
        """Buffer a streaming chunk for batch HTML insertion at the next timer tick."""
        if not self._streaming_display_enabled:
            return
        if not self._passes_search(event.model_name, event.task_id):
            return
        self._chunk_buffer.append(event.chunk_text)

    def _on_task_completed(self, event: TaskCompletedEvent) -> None:
        """Drain buffer then append an inference-complete entry with timing."""
        self._drain_chunk_buffer()
        search_key = f"{event.model.display_label} {event.task_id}"
        if self._accumulated_stream:
            escaped = (
                self._accumulated_stream.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            stream_html = (
                f"<span style='font-family:{_MONO_FONT_CSS};color:{self._color_stream_chunk};'>{escaped}</span>"
            )
            self._log_entries.append((2, search_key, stream_html))
            limit = self._app_settings.get_int(SETTING_LOG_MAX_LINES, _DEFAULT_MAX_LINES)
            if len(self._log_entries) > limit:
                self._log_entries = self._log_entries[-limit:]
            self._accumulated_stream = ""
        if self._response_label_pending:
            self._append_html(
                f"<b style='color:{self._color_accent};font-size:10px;'>RESPONSE</b>",
                min_verbosity=2,
            )
            self._response_label_pending = False
        if self._had_streaming_output:
            self._text_edit.insertHtml("<br>")
            self._had_streaming_output = False
        if not self._passes_search(search_key):
            return
        end_wall = time.time()
        end_str = time.strftime("%H:%M:%S", time.localtime(end_wall))
        duration_str = format_compact_duration(event.total_time_ms) if event.total_time_ms is not None else "\u2013"
        if event.status == BenchmarkResultStatus.FAILED:
            html = (
                f"<b style='color:{self._color_judge_fail};'>"
                f"&#x2717; {event.model.display_label} / {event.task_id}"
                f"</b>"
                f"<span style='color:{self._color_judge_fail};'>"
                f" &#x2014; End: {end_str} | Duration: {duration_str} | FAILED</span>"
            )
        else:
            html = (
                f"<b style='color:{self._color_inference_complete};'>"
                f"&#x2713; {event.model.display_label} / {event.task_id}"
                f"</b>"
                f"<span style='color:{self._color_secondary};'>"
                f" &#x2014; End: {end_str} | Duration: {duration_str}</span>"
            )
        self._append_html(html, min_verbosity=1, search_key=search_key)

    def _on_mode_switch(self, event: ModeSwitchEvent) -> None:
        """Append a phase-transition separator when moving from benchmarking to judging."""
        if event.to_stage == PipelineStage.JUDGING:
            sep = (
                f"<hr style='border:0;border-top:2px solid {self._color_border};margin:8px 0;'>"
                f"<b style='color:{self._color_secondary};'>"
                f"&#9776; BENCHMARKING COMPLETE &#8212; STARTING JUDGING PHASE</b>"
            )
            self._append_html(sep, min_verbosity=1, search_key="judging phase started")

    def _on_judge_eval_started(self, event: JudgeEvalStartedEvent) -> None:
        """Render a judge header block before the 4-layer evaluation output."""
        search_key = f"{event.task_id} {event.judge_model}"
        if not self._passes_search(search_key):
            return
        if not self._text_edit.document().isEmpty():
            self._append_html(
                f"<hr style='border:0;border-top:1px solid {self._color_border};margin:6px 0;'>",
                min_verbosity=1,
                search_key=search_key,
            )
        start_str = time.strftime("%H:%M:%S")
        header = (
            f"<b style='color:{JUDGE_LOG_COLOR};'>&#x2696; JUDGING: {event.task_id}</b>"
            f"<span style='color:{self._color_secondary};'>"
            f" ({event.result_number}/{event.results_total})</span>"
        )
        meta = (
            f"<span style='color:{self._color_secondary};font-size:10px;'>"
            f"Judge: {event.judge_provider_id}/{event.judge_model} | Start: {start_str}</span>"
        )
        self._append_html(header, min_verbosity=1, search_key=search_key)
        self._append_html(meta, min_verbosity=1, search_key=search_key)

    def _on_judge_completed(self, event: JudgeCompletedEvent) -> None:
        """Append a structured judge result entry for the completed evaluation."""
        search_key = f"{event.task_id} {event.layer} {event.verdict}"
        if not self._passes_search(search_key):
            return
        if event.verdict == EvalVerdict.PASS:
            verdict_color = self._color_judge_pass
        elif event.verdict == EvalVerdict.FAIL:
            verdict_color = self._color_judge_fail
        else:
            verdict_color = self._color_secondary

        # Header line (verbosity >= 1)
        header_parts: list[str] = [f"[{event.layer}]"]
        if event.judge_provider_id and event.judge_model:
            header_parts.append(f"Judge: {event.judge_provider_id} · {event.judge_model}")
        if event.judge_prompt_template:
            header_parts.append(f"Template: {event.judge_prompt_template}")
        header_html = (
            f"<span style='color:{JUDGE_LOG_COLOR};border-left:3px solid {JUDGE_LOG_COLOR};"
            f"padding-left:4px;'>" + " | ".join(header_parts) + "</span>"
        )
        self._append_html(header_html, min_verbosity=1, search_key=search_key)

        # Verdict + score line (verbosity >= 1)
        score_str = f"{event.score:.2f}" if event.score is not None else "N/A"
        resolved_str = " ✔" if event.resolved else ""
        verdict_html = (
            f"<span style='color:{verdict_color};font-weight:bold;'>"
            f"{event.verdict.upper()}</span>"
            f"<span style='color:{self._color_secondary};'>"
            f" | Score: {score_str}{resolved_str}</span>"
        )
        self._append_html(verdict_html, min_verbosity=1, search_key=search_key)

        # Resolution layer (verbosity >= 1, only when resolved)
        if event.resolved and event.resolution_layer:
            resolution_html = (
                f"<span style='color:{self._color_secondary};font-size:10px;'>"
                f"Resolution: {event.resolution_layer}</span>"
            )
            self._append_html(resolution_html, min_verbosity=1, search_key=search_key)

        # Reasoning (verbosity >= 2 only)
        if event.reasoning:
            truncated = event.reasoning[:200]
            escaped = truncated.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            reasoning_html = (
                f"<span style='color:{self._color_secondary};font-size:10px;"
                f"font-family:{_MONO_FONT_CSS};'>{escaped}</span>"
            )
            self._append_html(reasoning_html, min_verbosity=2, search_key=search_key)

    def _on_verbosity_changed(self, index: int) -> None:
        """Update verbosity level from combo selection and refilter displayed entries."""
        self._verbosity_level = index
        self._rerender_from_buffer()

    def _on_search_changed(self, text: str) -> None:
        """Update search filter text and refilter displayed entries."""
        self._search_text = text
        self._rerender_from_buffer()

    def _passes_search(self, *fields: str) -> bool:
        """Return True when the search text matches any of the given fields (case-insensitive)."""
        if not self._search_text:
            return True
        needle = self._search_text.lower()
        return any(needle in f.lower() for f in fields)

    def _rerender_from_buffer(self) -> None:
        """Clear the display and re-render buffered entries that pass current filters."""
        self._text_edit.clear()
        limit = self._app_settings.get_int(SETTING_LOG_MAX_LINES, _DEFAULT_MAX_LINES)
        visible = self._log_entries[-limit:]
        for min_verbosity, search_key, html in visible:
            if self._verbosity_level < min_verbosity:
                continue
            if self._search_text and self._search_text.lower() not in search_key.lower():
                continue
            cursor = self._text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._text_edit.setTextCursor(cursor)
            self._text_edit.insertHtml(html + "<br>")
        if self._auto_scroll:
            scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def _drain_chunk_buffer(self) -> None:
        """Flush accumulated streaming chunks using plain-text insertion to preserve spaces."""
        if not self._chunk_buffer:
            return
        text = "".join(self._chunk_buffer)
        self._chunk_buffer.clear()
        self._accumulated_stream += text
        if self._response_label_pending and not self._had_streaming_output:
            self._append_html(
                f"<b style='color:{self._color_accent};font-size:10px;'>RESPONSE</b>",
                min_verbosity=2,
            )
            self._response_label_pending = False
        self._insert_streaming_text(text)
        self._had_streaming_output = True

    def _insert_streaming_text(self, text: str) -> None:
        """Insert streaming text using QTextCharFormat to preserve all whitespace."""
        self._enforce_scrollback_limit()
        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._color_stream_chunk))
        fmt.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self._text_edit.setTextCursor(cursor)
        if self._auto_scroll:
            scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())

    def _append_html_inline(self, html: str) -> None:
        """Append HTML fragment without a trailing line break (used for streaming chunks)."""
        self._enforce_scrollback_limit()
        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.insertHtml(html)
        if self._auto_scroll:
            scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())

    def _append_plain(self, text: str) -> None:
        """Wrap plain text in secondary colour and append as HTML."""
        clean = text.rstrip("\n").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append_html(f"<span style='color:{self._color_secondary};'>{clean}</span>")

    def _append_html(self, html: str, *, min_verbosity: int = 1, search_key: str = "") -> None:
        """Record entry to buffer then append to display if it passes current filters.

        Args:
            html: HTML fragment to append (a ``<br>`` is added automatically).
            min_verbosity: Minimum verbosity level required to show this entry.
            search_key: Concatenated searchable text for this entry (used by rerender).
        """
        self._log_entries.append((min_verbosity, search_key, html))
        limit = self._app_settings.get_int(SETTING_LOG_MAX_LINES, _DEFAULT_MAX_LINES)
        if len(self._log_entries) > limit:
            self._log_entries = self._log_entries[-limit:]
        if self._verbosity_level < min_verbosity:
            return
        if self._search_text and self._search_text.lower() not in search_key.lower():
            return
        self._enforce_scrollback_limit()
        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.insertHtml(html + "<br>")
        if self._auto_scroll:
            scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())

    def _enforce_scrollback_limit(self) -> None:
        """Remove oldest lines when document block count exceeds the configured maximum."""
        limit = self._app_settings.get_int(SETTING_LOG_MAX_LINES, _DEFAULT_MAX_LINES)
        doc = self._text_edit.document()
        excess = doc.blockCount() - limit
        if excess <= 0:
            return
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, excess)
        cursor.removeSelectedText()

    def _on_scroll_changed(self, value: int) -> None:
        """Toggle auto-scroll and jump-button visibility based on scrollbar position.

        Args:
            value: Current scrollbar value.
        """
        scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
        if scrollbar is None:
            return
        at_bottom = value >= scrollbar.maximum() - _SCROLL_BOTTOM_THRESHOLD
        if at_bottom:
            self._auto_scroll = True
            self._jump_button.setVisible(False)
        else:
            self._auto_scroll = False
            self._jump_button.setVisible(True)

    def _jump_to_bottom(self) -> None:
        """Scroll to the bottom of the log and re-enable auto-scroll."""
        scrollbar: QScrollBar | None = self._text_edit.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())
        self._auto_scroll = True
        self._jump_button.setVisible(False)

    def _clear_log_display(self) -> None:
        """Clear all log content and reset auto-scroll state."""
        logger.debug("Clearing log display")
        self._text_edit.clear()
        self._log_entries.clear()
        self._accumulated_stream = ""
        self._had_streaming_output = False
        self._response_label_pending = False
        self._auto_scroll = True
        self._jump_button.setVisible(False)
