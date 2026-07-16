"""Proves STORY-049-AC-4 (08-D §8-§12)."""

import pytest

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens

_tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

_SCALAR_CASES = [
    ("font_size.xs", _tokens.font_size.xs, 11),
    ("font_size.sm", _tokens.font_size.sm, 12),
    ("font_size.base", _tokens.font_size.base, 13),
    ("font_size.md", _tokens.font_size.md, 14),
    ("font_size.lg", _tokens.font_size.lg, 16),
    ("font_size.xl", _tokens.font_size.xl, 20),
    ("font_weight.regular", _tokens.font_weight.regular, 400),
    ("font_weight.semibold", _tokens.font_weight.semibold, 600),
    ("spacing.xs", _tokens.spacing.xs, 2),
    ("spacing.sm", _tokens.spacing.sm, 4),
    ("spacing.md", _tokens.spacing.md, 8),
    ("spacing.lg", _tokens.spacing.lg, 12),
    ("spacing.xl", _tokens.spacing.xl, 16),
    ("spacing.2xl", _tokens.spacing.xxl, 24),
    ("radius.sm", _tokens.radius.sm, 3),
    ("radius.md", _tokens.radius.md, 5),
    ("radius.lg", _tokens.radius.lg, 8),
    ("border.width", _tokens.border.width, 1),
    ("border.width.active", _tokens.border.width_active, 1),
    ("focus.ring.outer_width", _tokens.focus_ring.outer_width, 1),
    ("focus.ring.inner_glow_width", _tokens.focus_ring.inner_glow_width, 2),
    ("focus.ring.inner_glow_opacity", _tokens.focus_ring.inner_glow_opacity, 0.40),
    ("shadow.modal_blur", _tokens.shadow.modal_blur, 24),
    ("shadow.modal_offset_y", _tokens.shadow.modal_offset_y, 8),
    ("shadow.popover_blur", _tokens.shadow.popover_blur, 12),
    ("shadow.popover_offset_y", _tokens.shadow.popover_offset_y, 4),
    ("motion.fast", _tokens.motion.fast_ms, 120),
    ("motion.standard", _tokens.motion.standard_ms, 200),
]


@pytest.mark.parametrize(
    ("label", "actual", "expected"), _SCALAR_CASES, ids=[case[0] for case in _SCALAR_CASES]
)
def test_scalar_token_resolves_to_spec_value(label: str, actual: float, expected: float) -> None:
    """Proves: STORY-049-AC-4

    Every scalar token defined in 08-D §8-§12 resolves to the exact specification value.
    """
    assert actual == expected
