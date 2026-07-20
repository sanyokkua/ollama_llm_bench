"""``LogController`` -- the Run Event Log panel: verbosity-aware rendering from a
cached raw-event buffer, case-insensitive search, a view-only Clear action, a
bounded buffer, persisted auto-scroll, the log-write-failure indicator, and
past-run log replay (``04_Progress_Widget/implementation_structure.md`` §4.3;
description.md §8; STORY-060-AC-1..6; EC-LOG-1, EC-LOG-3, EC-PERF-3, EC-PROV-4a).

Depends only on ``ProgressGateway``, ``EventBus``, and ``LogFormatter`` (D-R-06) --
never builds HTML itself; every rendered line comes from ``LogFormatter.format_event``
(or, for a past-run replay line, plain HTML-escaping of a raw log-file line -- no
structured ``RunLogEvent`` is recoverable from a past run's flat file).

The raw-event cache (``_cache``) and its parallel rendered-line cache
(``_rendered``) are both bounded ``deque``s sharing one ``maxlen`` (``EC-PERF-3``'s
buffer cap, read once at construction from ``ui.run_log_max_lines``) so eviction of
the oldest line is automatic. A verbosity change re-renders ``_rendered`` from the
still-full ``_cache`` (EC-LOG-3); the user's Clear action empties the view only,
never ``_cache``/``_rendered`` (AC-4) -- the next state-changing push (a new event or
a verbosity change) shows the full buffer again.

Per-event view repaints are coalesced (``EC-PERF-3``;
``11_Services_and_Algorithms/15_LOG_FORMATTING.md`` §10): a raw log-source event
starts one reusable, view-parented ``QTimer`` (never ``QTimer.singleShot``, so its
lifetime is tied to the view's and it cannot fire against a torn-down widget)
instead of pushing ``apply_log`` immediately, so a burst of near-simultaneous
events collapses into one view repaint. Verbosity changes, the Clear action, and
past-run replay all push immediately -- only the per-event append path is
debounced.
"""

from collections import deque
from typing import Final

from PySide6.QtCore import QTimer
import structlog

from ollama_llm_bench.backend.domain import ResultId, RunId, RunLogEvent
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_COMPLETED,
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_JUDGE_COMPLETED,
    SIGNAL_JUDGE_STARTED,
    SIGNAL_LOG_CLEARED,
    SIGNAL_MODEL_STABILITY_CHANGED,
    SIGNAL_MODEL_SWITCHED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    SIGNAL_PROVIDER_SWITCHED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_STAGE_CHANGED,
    SIGNAL_TASK_COMPLETED,
    SIGNAL_TASK_RETRY,
    EventBus,
    InferenceCompletedEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    LogClearedEvent,
    ModelStabilityChangedEvent,
    ModelSwitchedEvent,
    ProviderRegistryReloadedEvent,
    ProviderSwitchedEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunStoppedEvent,
    StageChangedEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.ui.progress._internal.select import (
    escape_past_run_line,
    filter_search,
    parse_bool_setting,
    parse_max_lines,
    parse_run_log_verbosity,
    select_judge_completed,
    select_judge_started,
    select_model_stability_system_note,
    select_model_switched,
    select_provider_registry_reloaded,
    select_provider_switched,
    select_run_failed,
    select_run_finished,
    select_run_stopped,
    select_stage_changed,
    select_task_completed,
    select_task_retry,
    select_task_start,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import LogLineViewModel, LogViewModel
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = ["LogController"]

logger = structlog.get_logger(__name__)

_SETTING_VERBOSITY = "ui.run_log_verbosity"
_SETTING_MAX_LINES = "ui.run_log_max_lines"
_SETTING_AUTO_SCROLL = "ui.auto_scroll_run_log"

# EC-PERF-3 / 11_Services_and_Algorithms/15_LOG_FORMATTING.md §10: the coalescing
# window for per-event view repaints -- short enough to feel live, long enough to
# collapse a burst of near-simultaneous pipeline events into one `apply_log` call.
_LOG_COALESCE_MS: Final[int] = 50


class LogController:
    """Subscribes the fifteen log-source signals; caches every raw event and
    renders one line per event via ``LogFormatter``."""

    def __init__(
        self, *, gateway: ProgressGateway, event_bus: EventBus, log_formatter: LogFormatter
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._log_formatter = log_formatter
        self._view: ProgressView | None = None
        max_lines = parse_max_lines(gateway.get_setting(_SETTING_MAX_LINES))
        self._cache: deque[RunLogEvent] = deque(maxlen=max_lines)
        self._rendered: deque[LogLineViewModel] = deque(maxlen=max_lines)
        self._verbosity = parse_run_log_verbosity(
            gateway.get_setting(_SETTING_VERBOSITY) or "normal"
        )
        self._auto_scroll = parse_bool_setting(
            gateway.get_setting(_SETTING_AUTO_SCROLL), default=True
        )
        self._search_term = ""
        self._pending_completion: dict[ResultId, InferenceCompletedEvent] = {}
        self._coalesce_scheduled = False
        self._coalesce_timer: QTimer | None = None
        self._past_run_lines: tuple[LogLineViewModel, ...] | None = None
        logger.debug(
            "log_controller_constructed", max_lines=max_lines, verbosity=self._verbosity.value
        )

    def bind(self, view: ProgressView) -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime; wire the
        toolbar's Qt signals."""
        self._view = view
        bus = self._event_bus
        bus.subscribe(SIGNAL_INFERENCE_STARTED, self._on_inference_started, owner=view)
        bus.subscribe(SIGNAL_INFERENCE_COMPLETED, self._on_inference_completed, owner=view)
        bus.subscribe(SIGNAL_TASK_COMPLETED, self._on_task_completed, owner=view)
        bus.subscribe(SIGNAL_JUDGE_STARTED, self._on_judge_started, owner=view)
        bus.subscribe(SIGNAL_JUDGE_COMPLETED, self._on_judge_completed, owner=view)
        bus.subscribe(SIGNAL_TASK_RETRY, self._on_task_retry, owner=view)
        bus.subscribe(SIGNAL_STAGE_CHANGED, self._on_stage_changed, owner=view)
        bus.subscribe(SIGNAL_PROVIDER_SWITCHED, self._on_provider_switched, owner=view)
        bus.subscribe(SIGNAL_MODEL_SWITCHED, self._on_model_switched, owner=view)
        bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_stopped, owner=view)
        bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_finished, owner=view)
        bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_failed, owner=view)
        bus.subscribe(SIGNAL_MODEL_STABILITY_CHANGED, self._on_model_stability_changed, owner=view)
        bus.subscribe(
            SIGNAL_PROVIDER_REGISTRY_RELOADED, self._on_provider_registry_reloaded, owner=view
        )
        bus.subscribe(SIGNAL_LOG_CLEARED, self._on_log_cleared, owner=view)
        view.log_verbosity_changed.connect(self._on_verbosity_changed)
        view.log_search_changed.connect(self._on_search_changed)
        view.log_clear_clicked.connect(self._on_clear_clicked)
        view.log_auto_scroll_changed.connect(self._on_auto_scroll_changed)
        self._push()

    # -- Event Bus handlers -----------------------------------------------------

    def _on_inference_started(self, payload: object) -> None:
        if not isinstance(payload, InferenceStartedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_INFERENCE_STARTED)
        self._append_event(select_task_start(payload))

    def _on_inference_completed(self, payload: object) -> None:
        if not isinstance(payload, InferenceCompletedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_INFERENCE_COMPLETED)
        self._pending_completion[payload.result_id] = payload

    def _on_task_completed(self, payload: object) -> None:
        if not isinstance(payload, TaskCompletedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_TASK_COMPLETED)
        completion = self._pending_completion.pop(payload.result_id, None)
        self._append_event(select_task_completed(payload, completion=completion))

    def _on_judge_started(self, payload: object) -> None:
        if not isinstance(payload, JudgeStartedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_JUDGE_STARTED)
        self._append_event(select_judge_started(payload))

    def _on_judge_completed(self, payload: object) -> None:
        if not isinstance(payload, JudgeCompletedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_JUDGE_COMPLETED)
        self._append_event(select_judge_completed(payload))

    def _on_task_retry(self, payload: object) -> None:
        if not isinstance(payload, TaskRetryEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_TASK_RETRY)
        self._append_event(select_task_retry(payload))

    def _on_stage_changed(self, payload: object) -> None:
        if not isinstance(payload, StageChangedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_STAGE_CHANGED)
        self._append_event(select_stage_changed(payload))

    def _on_provider_switched(self, payload: object) -> None:
        if not isinstance(payload, ProviderSwitchedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_PROVIDER_SWITCHED)
        self._append_event(select_provider_switched(payload))

    def _on_model_switched(self, payload: object) -> None:
        if not isinstance(payload, ModelSwitchedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_MODEL_SWITCHED)
        self._append_event(select_model_switched(payload))

    def _on_run_stopped(self, payload: object) -> None:
        if not isinstance(payload, RunStoppedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_RUN_STOPPED)
        self._append_event(select_run_stopped(payload))

    def _on_run_finished(self, payload: object) -> None:
        if not isinstance(payload, RunFinishedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_RUN_FINISHED)
        self._append_event(select_run_finished(payload))

    def _on_run_failed(self, payload: object) -> None:
        if not isinstance(payload, RunFailedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_RUN_FAILED)
        self._append_event(select_run_failed(payload))

    def _on_model_stability_changed(self, payload: object) -> None:
        if not isinstance(payload, ModelStabilityChangedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_MODEL_STABILITY_CHANGED)
        self._append_event(select_model_stability_system_note(payload))

    def _on_provider_registry_reloaded(self, payload: object) -> None:
        if not isinstance(payload, ProviderRegistryReloadedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_PROVIDER_REGISTRY_RELOADED)
        self._append_event(select_provider_registry_reloaded(payload))

    def _on_log_cleared(self, payload: object) -> None:
        if not isinstance(payload, LogClearedEvent):
            return
        logger.debug("log_event_received", signal_name=SIGNAL_LOG_CLEARED)
        self._cache.clear()
        self._rendered.clear()
        self._pending_completion.clear()
        self._past_run_lines = None
        self._push()

    # -- View (toolbar) signal handlers ------------------------------------------

    def _on_verbosity_changed(self, text: str) -> None:
        verbosity = parse_run_log_verbosity(text)
        logger.debug("log_verbosity_changed", verbosity=verbosity.value)
        self._gateway.set_setting(_SETTING_VERBOSITY, verbosity.value)
        self._verbosity = verbosity
        if self._past_run_lines is not None:
            # A past-run replay's lines are raw file text, never a structured
            # `RunLogEvent` -- there is nothing to re-render at the new verbosity,
            # so the still-untouched `_rendered` (== `_past_run_lines`) is simply
            # re-pushed rather than rebuilt from the (empty) live-run `_cache`.
            self._push()
            return
        self._rendered = deque(
            (
                LogLineViewModel(
                    kind=event.kind.value,
                    html=self._log_formatter.format_event(event=event, verbosity=verbosity),
                )
                for event in self._cache
            ),
            maxlen=self._cache.maxlen,
        )
        self._push()

    def _on_search_changed(self, text: str) -> None:
        logger.debug("log_search_changed", term_length=len(text))
        self._search_term = text
        self._push()

    def _on_clear_clicked(self) -> None:
        logger.debug("log_clear_clicked")
        if self._view is None:
            return
        self._view.apply_log(self._build_view_model(lines=()))

    def _on_auto_scroll_changed(self, active: bool) -> None:  # noqa: FBT001  # Qt bool signal payload
        logger.debug("log_auto_scroll_changed", active=active)
        self._gateway.set_setting(_SETTING_AUTO_SCROLL, "true" if active else "false")
        self._auto_scroll = active
        self._push()

    # -- Past-run replay ----------------------------------------------------------

    def load_past_run(self, run_id: RunId) -> None:
        """Load and replay a past run's saved log file (AC-6, no run active)."""
        logger.debug("log_load_past_run", run_id=run_id)
        self._cache.clear()
        self._pending_completion.clear()
        content = self._gateway.load_past_log(run_id)
        self._rendered = deque(
            (
                LogLineViewModel(kind="system", html=escape_past_run_line(line))
                for line in content.splitlines()
            ),
            maxlen=self._cache.maxlen,
        )
        self._past_run_lines = tuple(self._rendered)
        self._push()

    # -- Rendering ------------------------------------------------------------------

    def _append_event(self, event: RunLogEvent) -> None:
        self._cache.append(event)
        html = self._log_formatter.format_event(event=event, verbosity=self._verbosity)
        self._rendered.append(LogLineViewModel(kind=event.kind.value, html=html))
        self._schedule_push()

    def _schedule_push(self) -> None:
        """Coalesce a burst of per-event pushes into one repaint (EC-PERF-3):
        the raw-event cache/rendered-line updates above are always synchronous,
        but the view repaint itself is debounced by ``_LOG_COALESCE_MS``."""
        if self._coalesce_scheduled or self._view is None:
            return
        self._coalesce_scheduled = True
        if self._coalesce_timer is None:
            # Parented to `self._view` (never `QTimer.singleShot`), matching
            # `ProgressController._begin_draining`'s rationale: a controller is
            # not a QObject, so parenting ties the timer's lifetime to the
            # view's -- it is destroyed, and never fires, the moment the view
            # is, instead of outliving a torn-down view and crashing on a
            # stale C++ widget. One instance is reused across coalesce windows
            # rather than constructing a fresh `QTimer` per burst.
            self._coalesce_timer = QTimer(self._view)
            self._coalesce_timer.setSingleShot(True)
            self._coalesce_timer.timeout.connect(self._flush_coalesced_push)
        self._coalesce_timer.start(_LOG_COALESCE_MS)

    def _flush_coalesced_push(self) -> None:
        self._coalesce_scheduled = False
        self._push()

    def _build_view_model(self, *, lines: tuple[LogLineViewModel, ...]) -> LogViewModel:
        return LogViewModel(
            verbosity=self._verbosity,
            lines=lines,
            search_term=self._search_term,
            auto_scroll=self._auto_scroll,
            file_write_warning=self._gateway.run_log_write_failed(),
        )

    def _push(self) -> None:
        if self._view is None:
            return
        lines = filter_search(tuple(self._rendered), self._search_term)
        vm = self._build_view_model(lines=lines)
        logger.debug("log_applied", line_count=len(lines), verbosity=self._verbosity.value)
        self._view.apply_log(vm)
