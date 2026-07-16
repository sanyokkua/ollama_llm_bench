"""Builds the QPalette matching a ThemeTokens container's core roles (08-D §16)."""

from PySide6.QtGui import QColor, QPalette

from ollama_llm_bench.ui.theme.models import ThemeTokens


def render_palette(tokens: ThemeTokens) -> QPalette:
    """Build the QPalette for this container (AC-6: Window/Base/Text/Highlight)."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.colors.bg_window))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.colors.bg_input))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.colors.text_primary))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.colors.primary_base))
    return palette
