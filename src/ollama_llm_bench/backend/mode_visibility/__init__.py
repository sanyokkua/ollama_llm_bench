"""Mode-visibility policy: the data-driven RunMode x ConfigSection visibility lookup.

Source of truth: docs/v3_specification/11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md.

Gives the New Benchmark widget one declarative (mode, section) -> Visibility lookup so
the widget contains no hard-coded per-mode conditionals: it asks is_visible(mode, section)
and shows or hides each section accordingly. Pure, stateless, built once at import time;
a module-level self-check fails fast at import if a maintenance gap ever leaves a
(mode, section) cell undefined.
"""

from ollama_llm_bench.backend.mode_visibility.api import is_visible, visible_sections
from ollama_llm_bench.backend.mode_visibility.models import ConfigSection, Visibility

__all__: list[str] = [
    "ConfigSection",
    "Visibility",
    "is_visible",
    "visible_sections",
]
