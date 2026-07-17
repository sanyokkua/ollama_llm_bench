"""Shared visual primitives (BadgeLabel, HealthDot, MultiCheckFilterButton, ...) reused
across ui/* widgets. Pure presentation with dynamic-property roles (01_MODULE_INVENTORY.md
§6) — no domain logic.
"""

from ollama_llm_bench.ui.shared.api import (
    make_badge_label,
    make_health_dot,
    make_multi_check_filter_button,
)
from ollama_llm_bench.ui.shared.models import BadgeStatus, FilterSelectionChanged

__all__: list[str] = [
    "BadgeStatus",
    "FilterSelectionChanged",
    "make_badge_label",
    "make_health_dot",
    "make_multi_check_filter_button",
]
