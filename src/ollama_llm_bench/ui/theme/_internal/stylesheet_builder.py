"""Compiles a ThemeTokens container into the application-level QSS (08-D §16)."""

from ollama_llm_bench.ui.theme.models import ThemeTokens

_GENERIC_FAMILIES = frozenset({"sans-serif", "monospace"})


def _render_font_family(chain: tuple[str, ...]) -> str:
    return ", ".join(family if family in _GENERIC_FAMILIES else f'"{family}"' for family in chain)


def render_stylesheet(tokens: ThemeTokens) -> str:
    """Build the QSS string for this container, targeting dynamic-property role selectors."""
    sans_family = _render_font_family(tokens.fonts.sans)
    return (
        "QMainWindow, QDialog, QWidget {\n"
        f"    background-color: {tokens.colors.bg_window};\n"
        f"    color: {tokens.colors.text_primary};\n"
        f"    font-family: {sans_family};\n"
        f"    font-size: {tokens.font_size.base}px;\n"
        "}\n"
        "\n"
        'QPushButton[role="primary-button"] {\n'
        f"    background-color: {tokens.colors.primary_base};\n"
        f"    color: {tokens.colors.text_on_primary};\n"
        f"    border-radius: {tokens.radius.md}px;\n"
        f"    padding: {tokens.spacing.sm}px {tokens.spacing.md}px;\n"
        "}\n"
        "\n"
        'QPushButton[role="primary-button"]:hover {\n'
        f"    background-color: {tokens.colors.primary_hover};\n"
        "}\n"
        "\n"
        'QPushButton[role="primary-button"]:pressed {\n'
        f"    background-color: {tokens.colors.primary_pressed};\n"
        "}\n"
        "\n"
        'QPushButton[role="primary-button"]:disabled {\n'
        f"    background-color: {tokens.colors.primary_disabled};\n"
        "}\n"
        "\n"
        'QPushButton[role="filter-chip-active"] {\n'
        f"    background-color: {tokens.colors.bg_selected};\n"
        f"    border: {tokens.border.width_active}px solid {tokens.colors.border_focus};\n"
        f"    border-radius: {tokens.radius.md}px;\n"
        f"    padding: {tokens.spacing.sm}px {tokens.spacing.md}px;\n"
        "}\n"
        "\n"
        'QPushButton[role="destructive-button"] {\n'
        f"    background-color: {tokens.colors.error_base};\n"
        f"    color: {tokens.colors.text_on_error};\n"
        f"    border-radius: {tokens.radius.md}px;\n"
        f"    padding: {tokens.spacing.sm}px {tokens.spacing.md}px;\n"
        "}\n"
    )
