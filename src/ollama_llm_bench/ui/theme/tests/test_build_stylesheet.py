"""Proves STORY-049-AC-5 (08-D §16)."""

from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.theme import PlatformKind, build_stylesheet, make_dark_theme_tokens


def test_stylesheet_targets_role_selectors_with_resolved_values(qapp: QApplication) -> None:
    """Proves: STORY-049-AC-5

    build_stylesheet() emits a QSS rule that selects on role="primary-button" and carries the
    container's role-resolved primary.base / text.on-primary values.
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    stylesheet = build_stylesheet(tokens)

    assert 'QPushButton[role="primary-button"]' in stylesheet
    assert tokens.colors.primary_base in stylesheet
    assert tokens.colors.text_on_primary in stylesheet
