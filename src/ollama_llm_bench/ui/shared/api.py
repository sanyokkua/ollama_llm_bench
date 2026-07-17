"""Public factories for ui/shared's reusable visual primitives (08-L §6, §8, §9; 08-D §5, §6)."""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.shared._internal.badge_label import BadgeLabelWidget
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import HealthDisplayState, PlatformKind, ThemeManager

__all__: list[str] = ["make_badge_label", "make_health_dot"]


@icontract.require(
    lambda status: isinstance(status, BadgeStatus), "status must be a BadgeStatus member"
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_badge_label(
    *, status: BadgeStatus, text: str, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> QWidget:
    """Build a badge pill rendering `status`'s colour role and `text` (08-L §8, 08-D §5)."""
    return BadgeLabelWidget(
        status=status, text=text, theme_manager=theme_manager, platform_kind=platform_kind
    )


@icontract.require(
    lambda state: isinstance(state, HealthDisplayState),
    "state must be a HealthDisplayState member",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_health_dot(
    *,
    state: HealthDisplayState,
    text: str,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> QWidget:
    """Build a status dot resolving `state`'s health colour role, pulsing while CHECKING
    (08-D §6)."""
    return HealthDotWidget(
        state=state, text=text, theme_manager=theme_manager, platform_kind=platform_kind
    )
