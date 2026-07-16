"""Theme-independent scalar tokens shared by Dark and Light (08-D §8-§12)."""

from ollama_llm_bench.ui.theme.models import (
    BorderTokens,
    FocusRingTokens,
    FontSizeTokens,
    FontWeightTokens,
    MotionTokens,
    RadiusTokens,
    ShadowTokens,
    SpacingTokens,
)

FONT_SIZE_TOKENS = FontSizeTokens(xs=11, sm=12, base=13, md=14, lg=16, xl=20)
FONT_WEIGHT_TOKENS = FontWeightTokens(regular=400, semibold=600)
SPACING_TOKENS = SpacingTokens(xs=2, sm=4, md=8, lg=12, xl=16, xxl=24)
RADIUS_TOKENS = RadiusTokens(sm=3, md=5, lg=8)
BORDER_TOKENS = BorderTokens(width=1, width_active=1)
FOCUS_RING_TOKENS = FocusRingTokens(outer_width=1, inner_glow_width=2, inner_glow_opacity=0.40)
SHADOW_TOKENS = ShadowTokens(modal_blur=24, modal_offset_y=8, popover_blur=12, popover_offset_y=4)
MOTION_TOKENS = MotionTokens(fast_ms=120, standard_ms=200)
