"""Architecture guard: ui/main_window/ never calls setStyleSheet, never embeds a colour
literal, and imports no asyncio (STORY-053 Definition of Done).

Modelled on ``tests/architecture/test_ui_shared_style_authority.py`` (STORY-051).
"""

import ast
from pathlib import Path
import re

from pytest_archon import archrule

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_MAIN_WINDOW_ROOT = _SRC_ROOT / "ui" / "main_window"
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _iter_non_test_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "tests" not in path.parts)


def _calls_setstylesheet(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr == "setStyleSheet" for node in ast.walk(tree)
    )


def _embeds_colour_literal(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _HEX_COLOR_RE.match(node.value)
        for node in ast.walk(tree)
    )


def test_main_window_never_calls_setstylesheet() -> None:
    """Proves: STORY-053 Definition of Done

    No ui/main_window/ file calls setStyleSheet() (08-D §16); appearance is set only through
    ui/theme role resolution.
    """
    offenders = [
        path
        for path in _iter_non_test_python_files(_MAIN_WINDOW_ROOT)
        if _calls_setstylesheet(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_main_window_embeds_no_colour_literal() -> None:
    """Proves: STORY-053 Definition of Done

    No ui/main_window/ file embeds a literal colour value; colours are resolved from
    ui/theme's role accessors only (08-D §2, §16).
    """
    offenders = [
        path
        for path in _iter_non_test_python_files(_MAIN_WINDOW_ROOT)
        if _embeds_colour_literal(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_main_window_does_not_import_asyncio_or_qasync() -> None:
    """Proves: STORY-053 Definition of Done

    ui/main_window/ imports no asyncio, anyio, or qasync.
    """
    (
        archrule("main-window-no-asyncio")
        .match("ollama_llm_bench.ui.main_window*")
        .should_not_import("asyncio")
        .should_not_import("anyio")
        .should_not_import("qasync")
        .check("ollama_llm_bench")
    )
