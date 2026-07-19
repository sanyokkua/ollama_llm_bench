"""``ProgressHeaderWidget`` -- the header row: stage badge, run-name label, rename
pencil, Pause/Resume, Stop (``04_Progress_Widget/description.md`` §3).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from ollama_llm_bench.ui.progress._internal.stage_badge import StageBadgeWidget
from ollama_llm_bench.ui.progress._internal.theme_lookup import resolve_spacing_tokens
from ollama_llm_bench.ui.progress.models import HeaderAffordances, RunStage
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["ProgressHeaderWidget"]

_PAUSE_TOOLTIP = (
    "Pause — Finish the in-flight task, then freeze the pipeline. The run stays "
    "open; click Resume to continue. Settings cannot be changed while paused."
)
_STOP_TOOLTIP = (
    "Stop — Cancel the in-flight task and end this run. Completed results are "
    "kept; the run status becomes STOPPED and can be resumed later from the "
    "Resume tab."
)


class ProgressHeaderWidget(QWidget):
    """The header row (description.md §3): stage badge, run name + pencil,
    Pause/Resume, Stop. The stage badge is repainted by ``ProgressView.apply_counters``
    (the stage is part of ``CountersViewModel``, not this widget's own ``apply``)."""

    rename_clicked = Signal()
    pause_resume_clicked = Signal()
    stop_clicked = Signal()

    def __init__(
        self,
        *,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("progress.header")
        self._badge = StageBadgeWidget(
            stage=RunStage.INITIALIZING, theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._name_label = QLabel()
        self._name_label.setObjectName("progress.header.run_name")
        self._pencil_button = QToolButton()
        self._pencil_button.setObjectName("progress.header.rename_pencil")
        self._pencil_button.setText("✎")
        self._pencil_button.setToolTip("Rename this run")
        self._pencil_button.setFixedSize(28, 28)
        self._pencil_button.clicked.connect(self.rename_clicked)
        self._pause_resume_button = QPushButton("Pause")
        self._pause_resume_button.setObjectName("progress.header.pause_resume")
        self._pause_resume_button.setToolTip(_PAUSE_TOOLTIP)
        self._pause_resume_button.clicked.connect(self.pause_resume_clicked)
        self._stop_button = QPushButton("Stop")
        self._stop_button.setObjectName("progress.header.stop")
        self._stop_button.setProperty("buttonRole", "destructive")
        self._stop_button.setToolTip(_STOP_TOOLTIP)
        self._stop_button.clicked.connect(self.stop_clicked)
        self._status_label = QLabel()
        self._status_label.setObjectName("progress.header.draining_status")
        self._status_label.setVisible(False)
        self._build_layout(platform_kind)

    def _build_layout(self, platform_kind: PlatformKind) -> None:
        spacing = resolve_spacing_tokens(platform_kind=platform_kind).spacing
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing.sm)
        row.addWidget(self._badge)
        row.addWidget(self._name_label)
        row.addWidget(self._pencil_button)
        row.addStretch(1)
        row.addWidget(self._pause_resume_button)
        row.addWidget(self._stop_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.xs)
        layout.addLayout(row)
        layout.addWidget(self._status_label)

    @property
    def stage_badge(self) -> StageBadgeWidget:
        """The stage-badge pill, repainted by ``ProgressView.apply_counters``."""
        return self._badge

    def apply(self, *, run_name: str, affordances: HeaderAffordances) -> None:
        """Render the header fields owned directly by ``ProgressController`` (AC-2).

        Pause/Stop are hidden entirely (``setVisible``), not merely disabled,
        in ``Empty``/``ViewingPastRun`` -- `08-L_ui_standardization.md` §1's
        no-placeholder-UI rule.
        """
        self._name_label.setText(run_name)
        self._name_label.setToolTip(run_name)
        self._pencil_button.setVisible(affordances.show_rename_pencil)
        self._pause_resume_button.setText(affordances.pause_resume_label)
        self._pause_resume_button.setVisible(affordances.pause_resume_visible)
        self._pause_resume_button.setEnabled(affordances.pause_resume_enabled)
        self._stop_button.setVisible(affordances.stop_visible)
        self._stop_button.setEnabled(affordances.stop_enabled)

    def set_draining_status(self, text: str | None) -> None:
        """Show/hide the SPEC-098 draining sub-state status line (description.md §3.4).

        `text` is one of the two fixed strings the Pausing/Stopping draining
        sub-states read while the drain is in flight; `None` hides the line
        (rendered on settle -- a terminal/paused event, or the bounded
        reconciliation timeout).
        """
        self._status_label.setText(text or "")
        self._status_label.setVisible(text is not None)
