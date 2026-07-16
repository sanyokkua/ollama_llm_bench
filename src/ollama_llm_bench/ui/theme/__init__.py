"""Design tokens (typed Python objects) + the single QSS generator.

The single styling authority (ADR-0001, 08-D §16): holds the Dark/Light token containers,
resolves colour roles, and builds the QSS/QPalette the rest of the UI applies. No other module
may call setStyleSheet().
"""

from ollama_llm_bench.ui.theme.api import (
    build_palette,
    build_stylesheet,
    make_dark_theme_tokens,
    make_light_theme_tokens,
    resolve_color,
    resolve_health_color,
    resolve_verdict_color,
)
from ollama_llm_bench.ui.theme.models import (
    HealthDisplayState,
    PlatformKind,
    ThemeTokens,
    VerdictDisplayState,
)

__all__: list[str] = [
    "HealthDisplayState",
    "PlatformKind",
    "ThemeTokens",
    "VerdictDisplayState",
    "build_palette",
    "build_stylesheet",
    "make_dark_theme_tokens",
    "make_light_theme_tokens",
    "resolve_color",
    "resolve_health_color",
    "resolve_verdict_color",
]
