"""Fixed light/dark inline-style palette (`20_HTML_RENDERING.md` §6.5).

A service-internal constant table only — the service never reads a Qt palette or
a stylesheet, keeping it Qt-free and unit-testable. `_Palette` is intentionally
private: it never crosses this module's `_internal/` boundary.
"""

from dataclasses import dataclass
from typing import Final

from ollama_llm_bench.backend.html_rendering.models import LogSeverity, UiTheme


@dataclass(frozen=True, slots=True)
class _Palette:
    """One theme's full set of inline-style color/background constants."""

    container_bg: str
    container_fg: str
    border: str
    monospace_bg: str
    muted_fg: str
    severity_colors: dict[LogSeverity, str]
    badge_success_bg: str
    badge_success_fg: str
    badge_fail_bg: str
    badge_fail_fg: str
    badge_error_bg: str
    badge_error_fg: str


_LIGHT_PALETTE: Final[_Palette] = _Palette(
    container_bg="#ffffff",
    container_fg="#1a1a1a",
    border="#d0d0d0",
    monospace_bg="#f5f5f5",
    muted_fg="#6b6b6b",
    severity_colors={
        LogSeverity.DEBUG: "#8a8a8a",
        LogSeverity.INFO: "#2b6cb0",
        LogSeverity.SUCCESS: "#2f855a",
        LogSeverity.WARNING: "#b7791f",
        LogSeverity.ERROR: "#c53030",
    },
    badge_success_bg="#c6f6d5",
    badge_success_fg="#22543d",
    badge_fail_bg="#fed7d7",
    badge_fail_fg="#822727",
    badge_error_bg="#fed7d7",
    badge_error_fg="#822727",
)

_DARK_PALETTE: Final[_Palette] = _Palette(
    container_bg="#1e1e1e",
    container_fg="#e6e6e6",
    border="#3a3a3a",
    monospace_bg="#2a2a2a",
    muted_fg="#a0a0a0",
    severity_colors={
        LogSeverity.DEBUG: "#9a9a9a",
        LogSeverity.INFO: "#63b3ed",
        LogSeverity.SUCCESS: "#68d391",
        LogSeverity.WARNING: "#f6ad55",
        LogSeverity.ERROR: "#fc8181",
    },
    badge_success_bg="#22543d",
    badge_success_fg="#c6f6d5",
    badge_fail_bg="#822727",
    badge_fail_fg="#fed7d7",
    badge_error_bg="#822727",
    badge_error_fg="#fed7d7",
)

_PALETTES: Final[dict[UiTheme, _Palette]] = {
    UiTheme.LIGHT: _LIGHT_PALETTE,
    UiTheme.DARK: _DARK_PALETTE,
}


def palette_for(theme: UiTheme) -> _Palette:
    """Return the fixed inline-style palette for a theme."""
    return _PALETTES[theme]
