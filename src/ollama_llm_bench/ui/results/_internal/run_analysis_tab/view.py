"""``JudgeAnalysisTabView`` -- the Run Analysis tab's passive Qt view (STORY-065).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/run_analysis_tab.md``
§2 (layout), §5 (metadata line), §6 (rendering, no length cap), §7 (toolbar), §9
(empty/generating/ready/failed states). Passive View: renders a
``JudgeAnalysisViewModel`` via ``apply()`` and emits widget-local Qt signals on user
interaction; imports no adapter gateway, reactive store, or backend symbol beyond
``backend.domain`` DTOs it never touches directly here (none needed).

Narrative rendering uses ``QTextBrowser.setMarkdown()`` (read-only, scrollable):
``QTextDocument`` lays out its content incrementally as the viewport scrolls, which is
this view's "lazy for very long narratives" behaviour (§6, EC-RES-3) -- there is no
separate virtualised-rendering widget in this codebase to reuse. The browser inherits
the application palette the theme module installs on ``QApplication`` (no
``setStyleSheet`` call here), satisfying the "theme-aware" requirement (§6) with no
custom-painted surface.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ollama_llm_bench.ui.results._internal.theme_lookup import resolve_spacing_tokens
from ollama_llm_bench.ui.results.models import JudgeAnalysisViewModel
from ollama_llm_bench.ui.theme import PlatformKind

if TYPE_CHECKING:
    # Only for the type annotation on `bind_controller` -- controller.py imports this
    # module for JudgeAnalysisTabController's `_view` reference, so a real module-level
    # import here would be a runtime import cycle (mirrors every sibling tab's view.py).
    from ollama_llm_bench.ui.results._internal.run_analysis_tab.controller import (
        JudgeAnalysisTabController,
    )

__all__: list[str] = ["JudgeAnalysisTabView"]


class JudgeAnalysisTabView(QWidget):
    """Passive Run Analysis tab body: the metadata/toolbar strip, the narrative
    body, and the soft error banner."""

    generate_clicked = Signal()

    def __init__(self, *, platform_kind: PlatformKind = PlatformKind.UNKNOWN) -> None:
        super().__init__()
        self.setObjectName("run_analysis_tab.view")
        self._platform_kind = platform_kind
        self._controller: JudgeAnalysisTabController | None = None
        self._export_enabled = False
        self._build_ui()

    def _build_ui(self) -> None:
        tokens = resolve_spacing_tokens(platform_kind=self._platform_kind)
        spacing = tokens.spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(spacing.sm)

        toolbar = QHBoxLayout()
        self._metadata_label = QLabel("")
        self._metadata_label.setObjectName("run_analysis_tab.metadata_line")
        self._metadata_label.setProperty("role", "muted-caption")
        toolbar.addWidget(self._metadata_label)
        toolbar.addStretch()
        self._copy_button = QPushButton("Copy")
        self._copy_button.setObjectName("run_analysis_tab.copy_button")
        self._copy_button.setAccessibleName("Copy analysis")
        self._copy_button.setProperty("role", "outlined-muted-button")
        self._copy_button.clicked.connect(self._on_copy_clicked)
        toolbar.addWidget(self._copy_button)
        self._generate_button = QPushButton("Generate analysis")
        self._generate_button.setObjectName("run_analysis_tab.generate_button")
        self._generate_button.setAccessibleName("Generate analysis")
        self._generate_button.setProperty("role", "primary-button")
        self._generate_button.clicked.connect(self._on_generate_clicked)
        toolbar.addWidget(self._generate_button)
        root.addLayout(toolbar)

        self._error_banner = QLabel("")
        self._error_banner.setObjectName("run_analysis_tab.error_banner")
        self._error_banner.setProperty("role", "warning-callout")
        self._error_banner.setWordWrap(True)
        self._error_banner.setVisible(False)
        root.addWidget(self._error_banner)

        self._empty_label = QLabel("")
        self._empty_label.setObjectName("run_analysis_tab.empty_message")
        self._empty_label.setProperty("role", "muted-caption")
        self._empty_label.setWordWrap(True)
        root.addWidget(self._empty_label)

        self._narrative_body = QTextBrowser()
        self._narrative_body.setObjectName("run_analysis_tab.narrative_body")
        self._narrative_body.setOpenExternalLinks(False)
        self._narrative_body.setReadOnly(True)
        root.addWidget(self._narrative_body, 1)

    def bind_controller(self, controller: "JudgeAnalysisTabController") -> None:
        """Attach the sub-controller every user-interaction signal routes to."""
        self._controller = controller

    def apply(self, vm: JudgeAnalysisViewModel) -> None:
        """Render the full tab body from ``vm`` (§5-§9)."""
        self._metadata_label.setText(vm.metadata_line or "")
        self._metadata_label.setVisible(vm.metadata_line is not None)
        self._copy_button.setEnabled(vm.copy_enabled)
        self._generate_button.setText(vm.generate_button_label)
        self._generate_button.setEnabled(vm.generate_button_enabled)
        self._generate_button.setToolTip(vm.generate_button_tooltip or "")
        self._error_banner.setText(vm.error_banner or "")
        self._error_banner.setVisible(vm.error_banner is not None)
        self._apply_body(vm)

    def _apply_body(self, vm: JudgeAnalysisViewModel) -> None:
        show_narrative = vm.state in ("ready", "failed") and vm.narrative_markdown is not None
        self._narrative_body.setVisible(show_narrative)
        self._empty_label.setVisible(not show_narrative)
        if show_narrative and vm.narrative_markdown is not None:
            self._narrative_body.setMarkdown(vm.narrative_markdown)
        else:
            self._empty_label.setText(vm.empty_state_message or "")

    def set_export_enabled(self, *, enabled: bool) -> None:
        """Track the run's terminal-state readiness for the footer's export action.

        The uniform footer (``ui/results/_internal/footer.py``) already owns the
        ``run_analysis`` export button's enablement from its own run-terminal/
        has-completed-results check (STORY-061); this tab holds no export control of
        its own, so this only retains the state for parity with the sibling tabs'
        identical method (``set_run_terminal_state`` calls it uniformly).
        """
        self._export_enabled = enabled

    def _on_copy_clicked(self) -> None:
        if self._controller is not None:
            self._controller.on_copy_clicked()

    def _on_generate_clicked(self) -> None:
        # Opening the Generate Analysis dialog needs the shared provider/model
        # dropdown collaborators the parent `ResultController` holds (D-R-06) --
        # this tab's own controller depends only on `ResultGateway`/`EventBus`/
        # `Clipboard` (the story's design constraint), so the click is surfaced as a
        # plain Qt signal for the parent to handle, exactly like `detach_clicked` on
        # `ChartsTabView`.
        self.generate_clicked.emit()
