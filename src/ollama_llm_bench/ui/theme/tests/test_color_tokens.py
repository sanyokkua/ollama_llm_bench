"""Proves STORY-049-AC-1 and STORY-049-AC-2 (08-D §3-§6)."""

import pytest

from ollama_llm_bench.ui.theme import (
    HealthDisplayState,
    PlatformKind,
    VerdictDisplayState,
    make_dark_theme_tokens,
    make_light_theme_tokens,
    resolve_color,
    resolve_health_color,
    resolve_verdict_color,
)

_DARK_ROLE_VALUES = {
    "bg.window": "#0a0f1a",
    "bg.surface": "#111827",
    "bg.raised": "#1f2937",
    "bg.selected": "#263044",
    "bg.input": "#1f2937",
    "bg.context-strip": "#1f2937",
    "border.default": "#374151",
    "border.strong": "#4b5563",
    "border.focus": "#14b8a6",
    "text.primary": "#f9fafb",
    "text.secondary": "#9ca3af",
    "text.disabled": "#4b5563",
    "text.on-primary": "#ffffff",
    "text.on-error": "#ffffff",
    "primary.base": "#14b8a6",
    "primary.hover": "#2dd4bf",
    "primary.pressed": "#0d9488",
    "primary.disabled": "#2d5a54",
    "success.base": "#34d399",
    "success.fill": "rgba(52, 211, 153, 0.18)",
    "warning.base": "#fbbf24",
    "warning.fill": "rgba(251, 191, 36, 0.18)",
    "error.base": "#f87171",
    "error.fill": "rgba(248, 113, 113, 0.18)",
    "info.base": "#60a5fa",
    "info.fill": "rgba(96, 165, 250, 0.18)",
    "muted.base": "#9ca3af",
    "muted.fill": "rgba(156, 163, 175, 0.16)",
    "shadow": "rgba(0, 0, 0, 0.65)",
    "overlay": "rgba(0, 0, 0, 0.55)",
}

_LIGHT_ROLE_VALUES = {
    "bg.window": "#ffffff",
    "bg.surface": "#f3f4f6",
    "bg.raised": "#e5e7eb",
    "bg.selected": "#d1d5db",
    "bg.input": "#ffffff",
    "bg.context-strip": "#e5e7eb",
    "border.default": "#d1d5db",
    "border.strong": "#9ca3af",
    "border.focus": "#0d9488",
    "text.primary": "#111827",
    "text.secondary": "#4b5563",
    "text.disabled": "#9ca3af",
    "text.on-primary": "#ffffff",
    "text.on-error": "#ffffff",
    "primary.base": "#0d9488",
    "primary.hover": "#0f766e",
    "primary.pressed": "#115e59",
    "primary.disabled": "#99f6e4",
    "success.base": "#047857",
    "success.fill": "rgba(4, 120, 87, 0.12)",
    "warning.base": "#b45309",
    "warning.fill": "rgba(180, 83, 9, 0.12)",
    "error.base": "#dc2626",
    "error.fill": "rgba(220, 38, 38, 0.12)",
    "info.base": "#2563eb",
    "info.fill": "rgba(37, 99, 235, 0.10)",
    "muted.base": "#4b5563",
    "muted.fill": "rgba(75, 85, 99, 0.10)",
    "shadow": "rgba(15, 23, 42, 0.20)",
    "overlay": "rgba(15, 23, 42, 0.32)",
}

_FACTORY = {"dark": make_dark_theme_tokens, "light": make_light_theme_tokens}

_COLOUR_CASES = [("dark", role, expected) for role, expected in _DARK_ROLE_VALUES.items()] + [
    ("light", role, expected) for role, expected in _LIGHT_ROLE_VALUES.items()
]


@pytest.mark.parametrize(
    ("theme", "role", "expected"),
    _COLOUR_CASES,
    ids=[f"{theme}:{role}" for theme, role, _expected in _COLOUR_CASES],
)
def test_colour_role_resolves_to_spec_value_per_theme(theme: str, role: str, expected: str) -> None:
    """Proves: STORY-049-AC-1

    Every (theme, colour role) pair in 08-D §3/§4 resolves via resolve_color() to the exact
    specification value — total over all 30 roles in both role tables.
    """
    tokens = _FACTORY[theme](platform_kind=PlatformKind.LINUX)
    assert resolve_color(tokens, role) == expected


_VERDICT_CASES = [
    (VerdictDisplayState.PASS, "success.base"),
    (VerdictDisplayState.FAIL, "error.base"),
    (VerdictDisplayState.PENDING, "muted.base"),
    (VerdictDisplayState.FAILED_STATE, "warning.base"),
]

_HEALTH_CASES = [
    (HealthDisplayState.LIVE, "success.base"),
    (HealthDisplayState.REACHABLE_NO_MODELS, "warning.base"),
    (HealthDisplayState.DOWN, "error.base"),
    (HealthDisplayState.NOT_TESTED, "muted.base"),
    (HealthDisplayState.CHECKING, "muted.base"),
]

_STATE_ROLE_CASES = [("dark", state, role) for state, role in _VERDICT_CASES + _HEALTH_CASES] + [
    ("light", state, role) for state, role in _VERDICT_CASES + _HEALTH_CASES
]


@pytest.mark.parametrize(
    ("theme", "state", "role"),
    _STATE_ROLE_CASES,
    ids=[f"{theme}:{state.value}" for theme, state, _role in _STATE_ROLE_CASES],
)
def test_verdict_and_health_states_map_to_spec_base_role(
    theme: str, state: VerdictDisplayState | HealthDisplayState, role: str
) -> None:
    """Proves: STORY-049-AC-2

    Every verdict (08-D §5) and health (08-D §6) display state maps to the base colour role the
    specification assigns it, in both the Dark and the Light theme.
    """
    tokens = _FACTORY[theme](platform_kind=PlatformKind.LINUX)
    resolver = (
        resolve_verdict_color if isinstance(state, VerdictDisplayState) else resolve_health_color
    )
    assert resolver(tokens, state) == resolve_color(tokens, role)  # type: ignore[arg-type]
    # mypy cannot narrow `resolver`'s parameter type from the ternary branch actually taken;
    # `isinstance` above guarantees `state` matches whichever resolver was selected.
