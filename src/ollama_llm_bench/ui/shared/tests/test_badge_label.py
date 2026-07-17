"""Colocated unit tests for BadgeLabel (STORY-051-AC-1)."""

from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.ui.shared import BadgeStatus, make_badge_label
from ollama_llm_bench.ui.shared._internal.badge_label import BadgeLabelWidget
from ollama_llm_bench.ui.theme import (
    PlatformKind,
    ThemeSetting,
    make_dark_theme_tokens,
    make_theme_manager,
    resolve_color,
)

_STATUS_ROLE = [
    (BadgeStatus.PASS, "success.base"),
    (BadgeStatus.FAIL, "error.base"),
    (BadgeStatus.WARNING, "warning.base"),
    (BadgeStatus.INFO, "info.base"),
    (BadgeStatus.NEUTRAL, "muted.base"),
]


@pytest.mark.parametrize(("status", "role"), _STATUS_ROLE)
def test_badge_sets_role_and_shows_text_per_status(
    status: BadgeStatus, role: str, qapp: QApplication
) -> None:
    """Proves: STORY-051-AC-1

    For each badge status, make_badge_label sets the 08-L §8 / 08-D §5 theme role dynamic
    property and renders the supplied text label alongside the colour.
    """
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    widget = make_badge_label(
        status=status,
        text="Example",
        theme_manager=theme_manager,
        platform_kind=PlatformKind.LINUX,
    )

    assert isinstance(widget, BadgeLabelWidget)
    assert widget.property("badgeStatus") == status.value
    assert widget.text_label == "Example"
    assert widget.current_base_color_hex() == resolve_color(tokens, role)
