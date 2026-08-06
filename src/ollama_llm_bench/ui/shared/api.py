"""Public factories for ui/shared's reusable visual primitives (08-L §6, §8, §9; 08-D §5, §6)."""

import icontract
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ollama_llm_bench.ui.shared._internal.badge_label import (
    BadgeLabelWidget,
    resolve_badge_color_roles as _resolve_badge_color_roles,
)
from ollama_llm_bench.ui.shared._internal.dialog_close_button import (
    DIALOG_CLOSE_OBJECT_NAME,
    build_dialog_close_button,
)
from ollama_llm_bench.ui.shared._internal.gate_busy_indicator import (
    GATE_BUSY_OBJECT_NAME,
    build_gate_busy_indicator,
)
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget
from ollama_llm_bench.ui.shared._internal.multi_check_filter_button import (
    MultiCheckFilterButtonWidget,
)
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import HealthDisplayState, PlatformKind, ThemeManager

__all__: list[str] = [
    "make_badge_label",
    "make_dialog_close_button",
    "make_gate_busy_indicator",
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


@icontract.require(lambda role: len(role) > 0, "role must name a theme style role")
@icontract.ensure(lambda result: result.objectName() == DIALOG_CLOSE_OBJECT_NAME)
def make_dialog_close_button(*, role: str = "primary-button") -> QPushButton:
    """Build a dialog Close button carrying the pinned registry identity (§7.2).

    Args:
        role: The theme style role -- ``"primary-button"`` when Close is the footer's
            only or right-most action, ``"outlined-muted-button"`` when it sits left
            of a distinct primary confirm.

    Returns:
        The button, unconnected; the mounting dialog wires its own ``clicked`` handler.
    """
    return build_dialog_close_button(role=role)


@icontract.require(lambda message: len(message) > 0, "message must be non-empty")
@icontract.ensure(lambda result: result.objectName() == GATE_BUSY_OBJECT_NAME)
def make_gate_busy_indicator(*, message: str) -> QLabel:
    """Build the hidden gate-busy strip carrying the pinned registry identity (§7.2).

    Args:
        message: The sentence pinned by the mounting surface's own specification.

    Returns:
        The strip, hidden until the mounting surface reveals it.
    """
    return build_gate_busy_indicator(message=message)


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
