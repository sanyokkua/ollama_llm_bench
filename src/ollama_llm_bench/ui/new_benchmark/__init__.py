"""New Benchmark configuration surface: mode selector, section visibility,
selection store, Task Files (with drag-and-drop), Test Models, Judge, Advanced
Options, the Performance Matrix, and Start.

Source of truth: ``docs/v3_specification/02_New_Benchmark_Widget/``. Public
surface is ``make_new_benchmark_widget`` plus the ``NewBenchmarkCollaborators``
bundle a caller must construct to call it -- assembling the widget from its
``_internal/`` pieces.
"""

from ollama_llm_bench.ui.new_benchmark.api import (
    NewBenchmarkCollaborators,
    make_new_benchmark_widget,
)

__all__: list[str] = ["NewBenchmarkCollaborators", "make_new_benchmark_widget"]
