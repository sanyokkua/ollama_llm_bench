"""Proves STORY-049-AC-6 (08-D §16)."""

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.theme import PlatformKind, build_palette, make_dark_theme_tokens


def test_palette_maps_core_roles_to_resolved_values(qapp: QApplication) -> None:
    """Proves: STORY-049-AC-6

    build_palette() maps Window/Base/Text/Highlight to the container's resolved bg.window,
    bg.input, text.primary, and primary.base values respectively.
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    palette = build_palette(tokens)

    assert palette.color(QPalette.ColorRole.Window).name() == tokens.colors.bg_window
    assert palette.color(QPalette.ColorRole.Base).name() == tokens.colors.bg_input
    assert palette.color(QPalette.ColorRole.Text).name() == tokens.colors.text_primary
    assert palette.color(QPalette.ColorRole.Highlight).name() == tokens.colors.primary_base
