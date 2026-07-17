"""Colocated unit tests for HealthDot (STORY-051-AC-2, STORY-051-AC-4)."""

from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.shared import make_health_dot
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget
from ollama_llm_bench.ui.theme import (
    HealthDisplayState,
    PlatformKind,
    ThemeSetting,
    make_dark_theme_tokens,
    make_light_theme_tokens,
    make_theme_manager,
    resolve_health_color,
)

_STATE_ROLE_PULSE = [
    (HealthDisplayState.LIVE, "success.base", False),
    (HealthDisplayState.REACHABLE_NO_MODELS, "warning.base", False),
    (HealthDisplayState.DOWN, "error.base", False),
    (HealthDisplayState.NOT_TESTED, "muted.base", False),
    (HealthDisplayState.CHECKING, "muted.base", True),
]


@pytest.mark.parametrize(("state", "role", "pulses"), _STATE_ROLE_PULSE)
def test_health_dot_resolves_role_and_pulses_per_state(
    state: HealthDisplayState,
    role: str,
    pulses: bool,  # noqa: FBT001  # parametrize tuple element
    qapp: QApplication,
) -> None:
    """Proves: STORY-051-AC-2

    For each health state, make_health_dot resolves the 08-D §6 colour role and renders a
    text label; only the checking state runs the opacity pulse.
    """
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    widget = make_health_dot(
        state=state,
        text="Ollama",
        theme_manager=theme_manager,
        platform_kind=PlatformKind.LINUX,
    )

    assert isinstance(widget, HealthDotWidget)
    assert widget.property("healthState") == state.value
    assert widget.text_label == "Ollama"
    assert widget.current_color_hex() == resolve_health_color(tokens, state)
    assert widget.is_pulsing is pulses


def test_health_dot_repaints_on_theme_change(qapp: QApplication, mocker: MockerFixture) -> None:
    """Proves: STORY-051-AC-4

    Given a HealthDot rendered under one active theme, when the theme-changed notification
    fires, then the dot re-reads its colour from the newly active theme container and
    repaints.
    """
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    widget_qwidget = make_health_dot(
        state=HealthDisplayState.LIVE,
        text="Ollama",
        theme_manager=theme_manager,
        platform_kind=PlatformKind.LINUX,
    )
    assert isinstance(widget_qwidget, HealthDotWidget)
    widget = widget_qwidget
    dark_tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    assert widget.current_color_hex() == resolve_health_color(dark_tokens, HealthDisplayState.LIVE)
    update_spy = mocker.spy(widget._glyph, "update")

    theme_manager.set_theme_setting(ThemeSetting.LIGHT)

    light_tokens = make_light_theme_tokens(platform_kind=PlatformKind.LINUX)
    assert widget.current_color_hex() == resolve_health_color(light_tokens, HealthDisplayState.LIVE)
    assert update_spy.call_count == 1
