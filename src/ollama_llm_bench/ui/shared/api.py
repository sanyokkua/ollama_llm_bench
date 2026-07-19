"""Public factories for ui/shared's reusable visual primitives (08-L §6, §8, §9; 08-D §5, §6)."""

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.shared._internal.badge_label import (
    BadgeLabelWidget,
    resolve_badge_color_roles as _resolve_badge_color_roles,
)
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget
from ollama_llm_bench.ui.shared._internal.multi_check_filter_button import (
    MultiCheckFilterButtonWidget,
)
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import HealthDisplayState, PlatformKind, ThemeManager

__all__: list[str] = [
    "make_badge_label",
    "make_health_dot",
    "make_multi_check_filter_button",
    "resolve_badge_color_roles",
]


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


@icontract.require(lambda options: len(options) > 0, "options must be non-empty")
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_multi_check_filter_button(*, label: str, options: tuple[str, ...]) -> QWidget:
    """Build a checkable multi-select filter button (08-L §6)."""
    return MultiCheckFilterButtonWidget(label=label, options=options)


@icontract.require(
    lambda status: isinstance(status, BadgeStatus), "status must be a BadgeStatus member"
)
@icontract.ensure(lambda result: len(result[0]) > 0 and len(result[1]) > 0)
def resolve_badge_color_roles(status: BadgeStatus) -> tuple[str, str]:
    """Return `status`'s ``(base_role, fill_role)`` colour-role names (08-D §5).

    Lets a custom-painted surface (for example a table-cell delegate) render
    the same badge colour language ``BadgeLabelWidget`` uses without
    constructing a full widget instance.
    """
    return _resolve_badge_color_roles(status)
