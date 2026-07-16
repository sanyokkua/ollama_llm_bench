"""Architecture guard for ui/theme as the sole styling authority (STORY-049 DoD, ADR-0001)."""

import ast
from pathlib import Path

import pytest
from pytest_archon import archrule

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_THEME_ROOT = _SRC_ROOT / "ui" / "theme"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _calls_setstylesheet(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr == "setStyleSheet" for node in ast.walk(tree)
    )


def _references_qfontdatabase(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "QFontDatabase":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "QFontDatabase":
            return True
    return False


def test_setstylesheet_confined_to_ui_theme() -> None:
    """Proves: STORY-049 Definition of Done

    No module outside ui/theme/ calls setStyleSheet().
    """
    offenders = [
        path
        for path in _iter_python_files(_SRC_ROOT)
        if _THEME_ROOT not in path.parents
        and _calls_setstylesheet(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_ui_theme_does_not_reference_qfontdatabase() -> None:
    """Proves: STORY-049 Definition of Done

    ui/theme/ never probes QFontDatabase for per-family availability (08-D §7.5).
    """
    offenders = [
        path
        for path in _iter_python_files(_THEME_ROOT)
        if _references_qfontdatabase(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_ui_theme_does_not_import_asyncio_or_qasync() -> None:
    """Proves: STORY-049 Definition of Done

    ui/theme/ imports no asyncio, anyio, or qasync.
    """
    (
        archrule("ui-theme-no-asyncio")
        .match("ollama_llm_bench.ui.theme*")
        .should_not_import("asyncio")
        .should_not_import("anyio")
        .should_not_import("qasync")
        .check("ollama_llm_bench")
    )


def test_theme_tokens_is_frozen() -> None:
    """Proves: STORY-049 Definition of Done

    ThemeTokens (and its nested ColorTokens) is a frozen msgspec.Struct — attribute assignment
    after construction raises.
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    with pytest.raises(AttributeError):
        tokens.colors = tokens.colors  # type: ignore[misc]
