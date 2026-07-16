"""Public surface for the theme module (STORY-049): design-token containers, the QSS
generator, and the QPalette builder (08-D_color_palette_and_typography.md).
"""

import icontract
from PySide6.QtGui import QPalette

from ollama_llm_bench.ui.theme._internal.color_resolution import resolve_color_value
from ollama_llm_bench.ui.theme._internal.factory import (
    assemble_dark_theme_tokens,
    assemble_light_theme_tokens,
)
from ollama_llm_bench.ui.theme._internal.palette_builder import render_palette
from ollama_llm_bench.ui.theme._internal.stylesheet_builder import render_stylesheet
from ollama_llm_bench.ui.theme._internal.theme_selection import resolve_active_theme_kind
from ollama_llm_bench.ui.theme._internal.verdict_health import (
    health_color_value,
    verdict_color_value,
)
from ollama_llm_bench.ui.theme.models import (
    ActiveThemeKind,
    HealthDisplayState,
    OsColorScheme,
    PlatformKind,
    ThemeSetting,
    ThemeTokens,
    VerdictDisplayState,
)


@icontract.require(
    lambda platform_kind: isinstance(platform_kind, PlatformKind),
    "platform_kind must be a PlatformKind member",
)
@icontract.ensure(lambda result: len(result.fonts.sans) > 0 and len(result.fonts.mono) > 0)
def make_dark_theme_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Build the Dark theme's token container for the given platform (08-D §3, §7)."""
    return assemble_dark_theme_tokens(platform_kind=platform_kind)


@icontract.require(
    lambda platform_kind: isinstance(platform_kind, PlatformKind),
    "platform_kind must be a PlatformKind member",
)
@icontract.ensure(lambda result: len(result.fonts.sans) > 0 and len(result.fonts.mono) > 0)
def make_light_theme_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Build the Light theme's token container for the given platform (08-D §4, §7)."""
    return assemble_light_theme_tokens(platform_kind=platform_kind)


@icontract.require(
    lambda tokens, role: hasattr(tokens.colors, role.replace(".", "_").replace("-", "_")),
    "role must name a real ColorTokens attribute",
)
def resolve_color(tokens: ThemeTokens, role: str) -> str:
    """Resolve a colour role (for example "bg.surface") for this container (08-D §2)."""
    return resolve_color_value(tokens, role)


@icontract.ensure(lambda result: result.startswith("#"))
def resolve_verdict_color(tokens: ThemeTokens, state: VerdictDisplayState) -> str:
    """Resolve a verdict display state to its base colour role's value (08-D §5)."""
    return verdict_color_value(tokens, state)


@icontract.ensure(lambda result: result.startswith("#"))
def resolve_health_color(tokens: ThemeTokens, state: HealthDisplayState) -> str:
    """Resolve a health display state to its base colour role's value (08-D §6)."""
    return health_color_value(tokens, state)


@icontract.require(
    lambda theme_setting: isinstance(theme_setting, ThemeSetting),
    "theme_setting must be a ThemeSetting member",
)
@icontract.require(
    lambda os_color_scheme: isinstance(os_color_scheme, OsColorScheme),
    "os_color_scheme must be an OsColorScheme member",
)
@icontract.ensure(lambda result: isinstance(result, ActiveThemeKind))
def select_active_theme_kind(
    *, theme_setting: ThemeSetting, os_color_scheme: OsColorScheme
) -> ActiveThemeKind:
    """Select which container (Dark/Light) applies for this setting + OS scheme (08-D §13)."""
    return resolve_active_theme_kind(theme_setting=theme_setting, os_color_scheme=os_color_scheme)


@icontract.ensure(lambda result: 'role="primary-button"' in result)
def build_stylesheet(tokens: ThemeTokens) -> str:
    """Compile a token container into the application-level Qt stylesheet (08-D §16)."""
    return render_stylesheet(tokens)


@icontract.ensure(
    lambda result, tokens: result.color(QPalette.ColorRole.Window).name() == tokens.colors.bg_window
)
def build_palette(tokens: ThemeTokens) -> QPalette:
    """Build the QPalette matching a token container's core roles (08-D §16, AC-6)."""
    return render_palette(tokens)
