"""``NewBenchmarkView`` -- the passive top-level widget assembling all sections
(STORY-054, STORY-055, STORY-071). Renders a ``NewBenchmarkViewModel``; imports no
Gateway, no reactive store, no backend service symbol (passive-View rule) -- only
``ui`` primitives, its own sub-widgets, and ``models.py``.
"""

from PySide6.QtWidgets import QPushButton, QScrollArea, QVBoxLayout, QWidget

from ollama_llm_bench.backend.mode_visibility import ConfigSection
from ollama_llm_bench.ui.new_benchmark._internal.advanced_options import (
    AdvancedOptionsSectionWidget,
)
from ollama_llm_bench.ui.new_benchmark._internal.judge_section import JudgeSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget
from ollama_llm_bench.ui.new_benchmark._internal.performance_matrix import (
    PerformanceMatrixSectionWidget,
)
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget
from ollama_llm_bench.ui.new_benchmark.models import NewBenchmarkViewModel

__all__: list[str] = ["NewBenchmarkView"]


class NewBenchmarkView(QWidget):
    """Assembles the mode selector, every section, and the sticky Start footer."""

    def __init__(
        self,
        *,
        mode_selector: ModeSelectorWidget,
        task_files_section: TaskFilesSectionWidget,
        test_models_section: TestModelsSectionWidget,
        judge_section: JudgeSectionWidget,
        advanced_options_section: AdvancedOptionsSectionWidget,
    ) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.view")
        self.mode_selector = mode_selector
        self.task_files_section = task_files_section
        self.test_models_section = test_models_section
        self.judge_section = judge_section
        self.advanced_options_section = advanced_options_section
        self.performance_matrix_section = PerformanceMatrixSectionWidget()
        self._section_containers: dict[ConfigSection, QWidget] = {
            ConfigSection.RUN_MODE_SELECTOR: self.mode_selector,
            ConfigSection.INPUT_SIZES: self.performance_matrix_section,
            ConfigSection.OUTPUT_SIZES: self.performance_matrix_section,
            ConfigSection.REPEATS: self.performance_matrix_section,
            ConfigSection.TASK_FILES: self.task_files_section,
            ConfigSection.TEST_MODELS_PICKER: self.test_models_section,
            ConfigSection.JUDGE_MODEL_PICKER: self.judge_section,
            ConfigSection.RUN_ANALYSIS_TOGGLE: self.judge_section,
            ConfigSection.EMBEDDING_MODEL_INFO: self.judge_section.embedding_status_row,
            ConfigSection.ADVANCED_OPTIONS: self.advanced_options_section,
        }
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        top_level_widgets = (
            self.mode_selector,
            self.performance_matrix_section,
            self.task_files_section,
            self.test_models_section,
            self.judge_section,
            self.advanced_options_section,
        )
        for widget in top_level_widgets:
            content_layout.addWidget(widget)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.start_button = QPushButton("Start Benchmark")
        self.start_button.setObjectName("new_benchmark.start_button")
        self.start_button.setProperty("role", "primary-button")
        outer.addWidget(self.start_button)

    def apply_view_model(self, view_model: NewBenchmarkViewModel) -> None:
        """Show/hide every section container per ``view_model.visible_sections``,
        push the embedding status row's content, and set the Start button's
        enabled state and tooltip.
        """
        for section, container in self._section_containers.items():
            container.setVisible(section in view_model.visible_sections)
        if view_model.synthetic_estimate_line is not None:
            self.performance_matrix_section.set_estimate_text(view_model.synthetic_estimate_line)
        self.judge_section.apply_embedding_status(view_model.embedding_status)
        self.start_button.setEnabled(view_model.start_enabled)
        self.start_button.setToolTip(view_model.start_tooltip)
