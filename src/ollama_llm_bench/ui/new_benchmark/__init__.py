"""New Benchmark configuration surface (STORY-054): mode selector, section
visibility, selection store, Task Files, Test Models. Judge/Advanced/Start
(STORY-055) and Performance Matrix content (a new, not-yet-drafted future story)
are stubbed.

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
