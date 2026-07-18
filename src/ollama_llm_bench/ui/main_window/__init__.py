"""Application shell (STORY-053): menu bar, workspace region, status bar, quit sequence.

Source of truth: ``docs/v3_specification/01_Main_Window/``. Public surface is exactly one
symbol -- ``make_main_window`` -- assembling the shell from its ``_internal/`` pieces.
"""

from ollama_llm_bench.ui.main_window.api import make_main_window

__all__: list[str] = ["make_main_window"]
