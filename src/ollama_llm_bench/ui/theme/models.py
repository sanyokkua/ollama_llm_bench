"""Design-token containers, platform classification, and display-state enums for the theme
module (08-D_color_palette_and_typography.md §1-§12, §16).

This module imports PySide6, the standard library, and msgspec only (STORY-049 design
constraints) — it never imports backend.platform.PlatformKind. The adapters layer translates
the real detected platform into this module's own PlatformKind when it wires the live
application theme (see STORY-050).
"""

from enum import StrEnum

import msgspec

# --- 1. Platform classification (08-D §7.1-§7.2) ---


class PlatformKind(StrEnum):
    """The four host classifications the theme module selects a font chain for (08-D §7.2)."""

    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


# --- 2. Verdict and health display states (08-D §5, §6) ---


class VerdictDisplayState(StrEnum):
    """The verdict-adjacent display states 08-D §5 maps to a base colour role."""

    PASS = "pass"  # noqa: S105  # display state, not a credential
    FAIL = "fail"
    PENDING = "pending"
    FAILED_STATE = "failed_state"


class HealthDisplayState(StrEnum):
    """The provider/endpoint health display states 08-D §6 maps to a base colour role."""

    LIVE = "live"
    REACHABLE_NO_MODELS = "reachable_no_models"
    DOWN = "down"
    NOT_TESTED = "not_tested"
    CHECKING = "checking"


# --- 2a. Theme-switching enums (08-D §13, STORY-050) ---


class ThemeSetting(StrEnum):
    """The three values of the `ui.theme` setting this module consumes (08-D §13).

    This module never reads or parses the raw `ui.theme` setting string itself (owned by
    the settings service, STORY-014) — the caller resolves the string to this enum before
    calling into ui/theme.
    """

    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


class OsColorScheme(StrEnum):
    """The OS-reported colour-scheme preference (08-D §13), read via Qt QStyleHints."""

    DARK = "dark"
    LIGHT = "light"


class ActiveThemeKind(StrEnum):
    """Which token container is currently selected (08-D §13 AC-1)."""

    DARK = "dark"
    LIGHT = "light"


# --- 3. Colour tokens (08-D §3 Dark / §4 Light) ---


class ColorTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Every one of the 30 colour roles from 08-D §3 (Dark) / §4 (Light)."""

    bg_window: str
    bg_surface: str
    bg_raised: str
    bg_selected: str
    bg_input: str
    bg_context_strip: str
    border_default: str
    border_strong: str
    border_focus: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_on_primary: str
    text_on_error: str
    primary_base: str
    primary_hover: str
    primary_pressed: str
    primary_disabled: str
    success_base: str
    success_fill: str
    warning_base: str
    warning_fill: str
    error_base: str
    error_fill: str
    info_base: str
    info_fill: str
    muted_base: str
    muted_fill: str
    shadow: str
    overlay: str


# --- 4. Font tokens (08-D §7, §8) ---


class FontChainTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The ordered sans/mono family chains for one platform (08-D §7.2)."""

    sans: tuple[str, ...]
    mono: tuple[str, ...]


class FontSizeTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The font-size scale in pixels (08-D §8)."""

    xs: int
    sm: int
    base: int
    md: int
    lg: int
    xl: int


class FontWeightTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The two permitted font weights (08-D §8)."""

    regular: int
    semibold: int


# --- 5. Spacing, radius, border, focus, shadow, motion tokens (08-D §9-§12) ---


class SpacingTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The spacing scale in pixels (08-D §9). `xxl` is the "2xl" token."""

    xs: int
    sm: int
    md: int
    lg: int
    xl: int
    xxl: int


class RadiusTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The corner-radius scale in pixels (08-D §10)."""

    sm: int
    md: int
    lg: int


class BorderTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Neutral and active border widths in pixels (08-D §11)."""

    width: int
    width_active: int


class FocusRingTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The focus-ring geometry: outer line + inner glow (08-D §11)."""

    outer_width: int
    inner_glow_width: int
    inner_glow_opacity: float


class ShadowTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Modal and popover drop-shadow geometry in pixels (08-D §12). Colour comes from
    ColorTokens.shadow — this struct holds only blur/offset geometry."""

    modal_blur: int
    modal_offset_y: int
    popover_blur: int
    popover_offset_y: int


class MotionTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Transition durations in milliseconds (08-D §12)."""

    fast_ms: int
    standard_ms: int


# --- 6. The complete per-theme container (08-D §16) ---


class ThemeTokens(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The complete design-token set for one theme, Dark or Light (08-D §3-§12)."""

    colors: ColorTokens
    fonts: FontChainTokens
    font_size: FontSizeTokens
    font_weight: FontWeightTokens
    spacing: SpacingTokens
    radius: RadiusTokens
    border: BorderTokens
    focus_ring: FocusRingTokens
    shadow: ShadowTokens
    motion: MotionTokens
