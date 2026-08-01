"""Application shell (STORY-053): menu bar, workspace region, status bar, quit sequence.

Source of truth: ``docs/v3_specification/01_Main_Window/``. Public surface is two symbols
-- ``make_status_bar`` (STORY-077 Fix 2, built first so ``compose.py`` can share the one
status-bar instance with ``adapters.notification_service``) and ``make_main_window``, which
assembles the rest of the shell from its ``_internal/`` pieces.
"""

from ollama_llm_bench.ui.main_window.api import make_main_window, make_status_bar

__all__: list[str] = ["make_main_window", "make_status_bar"]
