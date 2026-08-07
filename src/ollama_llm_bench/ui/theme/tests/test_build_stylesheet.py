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


def test_stylesheet_targets_destructive_button_role_distinctly_from_primary(
    qapp: QApplication,
) -> None:
    """Proves: STORY-067 spec-conformance fix
    (``06_Settings_Dialog/sub_dialogs/reset_confirmation.md`` §3's "Styled as the
    destructive action").

    build_stylesheet() emits a QSS rule selecting on role="destructive-button",
    carrying the container's error.base / text.on-error values -- a visually
    distinct fill from role="primary-button".
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    stylesheet = build_stylesheet(tokens)

    assert 'QPushButton[role="destructive-button"]' in stylesheet
    assert tokens.colors.error_base in stylesheet
    assert tokens.colors.text_on_error in stylesheet
    assert tokens.colors.error_base != tokens.colors.primary_base


def test_stylesheet_renders_focus_ring_for_focus_retaining_input_types(
    qapp: QApplication,
) -> None:
    """Proves: STORY-091 Definition of Done (08_ACCESSIBILITY_FLOOR.md §5)

    build_stylesheet() emits a :focus rule for every focus-retaining input type --
    QLineEdit, QTextEdit, QComboBox, QAbstractSpinBox, QTableView, QListView, QTreeView --
    using the focus_ring outer width and the border_focus colour. Momentary buttons
    (QPushButton) are deliberately excluded (DD-52).
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    stylesheet = build_stylesheet(tokens)

    assert "QLineEdit:focus" in stylesheet
    assert "QTextEdit:focus" in stylesheet
    assert "QComboBox:focus" in stylesheet
    assert "QAbstractSpinBox:focus" in stylesheet
    assert "QTableView:focus" in stylesheet
    assert "QListView:focus" in stylesheet
    assert "QTreeView:focus" in stylesheet
    assert f"{tokens.focus_ring.outer_width}px solid {tokens.colors.border_focus}" in stylesheet
    assert "QPushButton:focus" not in stylesheet
