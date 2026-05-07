"""Design tokens for dark, light, and shared QSS theming.

Exports three token dicts (DARK_TOKENS, LIGHT_TOKENS, SHARED_TOKENS) and
a ``get_tokens()`` factory that merges shared and theme-specific tokens.
"""

import logging

logger = logging.getLogger(__name__)


def _get_font_sans() -> str:
    return '"SF Pro Text", "Segoe UI", "Cantarell", "Ubuntu", "Helvetica Neue", "Noto Sans", "DejaVu Sans", sans-serif'


def _get_font_mono() -> str:
    return (
        '"SF Mono", "Cascadia Mono", "Menlo", "Consolas", '
        '"Ubuntu Mono", "DejaVu Sans Mono", "Monaco", "Courier New", monospace'
    )


DARK_TOKENS: dict[str, str] = {
    "bg_primary": "#111827",
    "bg_secondary": "#1F2937",
    "bg_card": "#263044",
    "bg_input": "#1F2937",
    "bg_hover": "#1A3A35",
    "text_primary": "#F9FAFB",
    "text_secondary": "#9CA3AF",
    "text_disabled": "#4B5563",
    "primary": "#14B8A6",
    "success": "#34D399",
    "warning": "#FBBF24",
    "failure": "#FF9999",
    "border": "#374151",
    "border_focus": "#14B8A6",
    "primary_hover": "#0FA898",
    "primary_pressed": "#0D9488",
    "primary_disabled": "#2D5A54",
    "text_on_primary": "#111827",
    "accent": "#A78BFA",
    "accent_light": "#2E1065",
    "success_bg": "#064E3B",
    "failure_bg": "#7F1D1D",
    "warning_bg": "#78350F",
    "selection": "#134E4A",
    "hover": "#1A3A35",
    "scrollbar_bg": "#1F2937",
    "scrollbar_handle": "#4B5563",
    "text_muted": "#CBD5E1",
    "success_text": "#34D399",
    "failure_text": "#FF9999",
}

LIGHT_TOKENS: dict[str, str] = {
    "bg_primary": "#FDFDFD",
    "bg_secondary": "#F3F4F6",
    "bg_card": "#FFFFFF",
    "bg_input": "#FFFFFF",
    "bg_hover": "#F0FDFA",
    "text_primary": "#0F172A",
    "text_secondary": "#5A6478",
    "text_disabled": "#9CA3AF",
    "primary": "#0A7A70",
    "success": "#047857",
    "warning": "#B45309",
    "failure": "#CC2020",
    "border": "#D1D5DB",
    "border_focus": "#0A7A70",
    "primary_hover": "#096B62",
    "primary_pressed": "#085C56",
    "primary_disabled": "#A7D3CF",
    "text_on_primary": "#FFFFFF",
    "accent": "#8B5CF6",
    "accent_light": "#EDE9FE",
    "success_bg": "#ECFDF5",
    "failure_bg": "#FEF2F2",
    "warning_bg": "#FFFBEB",
    "selection": "#CCFBF1",
    "hover": "#F0FDFA",
    "scrollbar_bg": "#E5E7EB",
    "scrollbar_handle": "#9CA3AF",
    "text_muted": "#475569",
    "success_text": "#047857",
    "failure_text": "#CC2020",
}

SHARED_TOKENS: dict[str, str] = {
    "spacing_xs": "4px",
    "spacing_sm": "8px",
    "spacing_md": "12px",
    "spacing_lg": "16px",
    "spacing_xl": "24px",
    "radius_sm": "4px",
    "radius_md": "6px",
    "radius_lg": "8px",
    "radius_pill": "10px",
    "font_sans": _get_font_sans(),
    "font_mono": _get_font_mono(),
}


def get_tokens(theme: str) -> dict[str, str]:
    """Return the merged token dict for the given theme name.

    Args:
        theme: Theme name — "dark" or "light". Falls back to "dark" for unknown values.

    Returns:
        Dict merging SHARED_TOKENS with the requested theme tokens.
        Theme tokens override SHARED_TOKENS for any key collision.
    """
    if theme == "light":
        return {**SHARED_TOKENS, **LIGHT_TOKENS}
    if theme != "dark":
        logger.warning("unknown_theme_requested", extra={"theme": theme, "fallback": "dark"})
    return {**SHARED_TOKENS, **DARK_TOKENS}
