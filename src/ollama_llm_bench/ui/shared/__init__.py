"""Shared visual primitives (BadgeLabel, HealthDot, MultiCheckFilterButton, ...) reused
across ui/* widgets. Pure presentation with dynamic-property roles (01_MODULE_INVENTORY.md
§6) — no domain logic.
"""

from ollama_llm_bench.ui.shared.api import (
    ensure_tab_bar_scroll_buttons_meet_click_target,
    make_badge_label,
    make_dialog_close_button,
    make_gate_busy_indicator,
    make_health_dot,
    make_multi_check_filter_button,
    resolve_badge_color_roles,
)
from ollama_llm_bench.ui.shared.models import BadgeStatus, FilterSelectionChanged

__all__: list[str] = [
    "BadgeStatus",
    "FilterSelectionChanged",
    "ensure_tab_bar_scroll_buttons_meet_click_target",
    "make_badge_label",
    "make_dialog_close_button",
    "make_gate_busy_indicator",
    "make_health_dot",
    "make_multi_check_filter_button",
    "resolve_badge_color_roles",
]
