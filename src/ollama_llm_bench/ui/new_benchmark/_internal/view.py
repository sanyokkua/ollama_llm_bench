"""``NewBenchmarkView`` -- the passive top-level widget assembling all sections
(STORY-054). Renders a ``NewBenchmarkViewModel``; imports no Gateway, no reactive
store, no backend service symbol (passive-View rule) -- only ``ui`` primitives,
its own sub-widgets, and ``models.py``.
"""

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ollama_llm_bench.backend.mode_visibility import ConfigSection
from ollama_llm_bench.ui.new_benchmark._internal.mode_selector import ModeSelectorWidget
from ollama_llm_bench.ui.new_benchmark._internal.stub_sections import make_stub_section
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget
from ollama_llm_bench.ui.new_benchmark.models import NewBenchmarkViewModel

__all__: list[str] = ["NewBenchmarkView"]

_STUB_TITLES: dict[ConfigSection, str] = {
    ConfigSection.INPUT_SIZES: "Performance Matrix",
    ConfigSection.JUDGE_MODEL_PICKER: "Judge",
    ConfigSection.EMBEDDING_MODEL_INFO: "Embedding status",
    ConfigSection.ADVANCED_OPTIONS: "Advanced Options",
}
# INPUT_SIZES/OUTPUT_SIZES/REPEATS share one "Performance Matrix" container; only
# INPUT_SIZES is used as the dict key below to avoid rendering the stub three times.
_PERFORMANCE_MATRIX_MEMBERS = (
    ConfigSection.INPUT_SIZES,
    ConfigSection.OUTPUT_SIZES,
    ConfigSection.REPEATS,
)


class NewBenchmarkView(QWidget):
    """Assembles the mode selector, stub sections, Task Files, and Test Models."""

    def __init__(
        self,
        *,
        mode_selector: ModeSelectorWidget,
        task_files_section: TaskFilesSectionWidget,
        test_models_section: TestModelsSectionWidget,
    ) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.view")
        self.mode_selector = mode_selector
        self.task_files_section = task_files_section
        self.test_models_section = test_models_section
        self._performance_matrix_stub = make_stub_section("Performance Matrix")
        self._section_containers: dict[ConfigSection, QWidget] = {
            ConfigSection.RUN_MODE_SELECTOR: self.mode_selector,
            ConfigSection.INPUT_SIZES: self._performance_matrix_stub,
            ConfigSection.OUTPUT_SIZES: self._performance_matrix_stub,
            ConfigSection.REPEATS: self._performance_matrix_stub,
            ConfigSection.TASK_FILES: self.task_files_section,
            ConfigSection.TEST_MODELS_PICKER: self.test_models_section,
            ConfigSection.JUDGE_MODEL_PICKER: make_stub_section("Judge"),
            ConfigSection.EMBEDDING_MODEL_INFO: make_stub_section("Embedding status"),
            ConfigSection.RUN_ANALYSIS_TOGGLE: make_stub_section("Run Analysis"),
            ConfigSection.ADVANCED_OPTIONS: make_stub_section("Advanced Options"),
        }
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        for container in dict.fromkeys(self._section_containers.values()):
            content_layout.addWidget(container)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def apply_view_model(self, view_model: NewBenchmarkViewModel) -> None:
        """Show/hide every section container per ``view_model.visible_sections``."""
        for section, container in self._section_containers.items():
            container.setVisible(section in view_model.visible_sections)
