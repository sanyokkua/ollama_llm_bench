"""Architecture guard: ui/shared/ never calls setStyleSheet, never embeds a colour literal,
and imports no asyncio (STORY-051 Definition of Done).
"""

import ast
from pathlib import Path
import re

from pytest_archon import archrule

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_SHARED_ROOT = _SRC_ROOT / "ui" / "shared"
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


def test_ui_shared_never_calls_setstylesheet() -> None:
    """Proves: STORY-051 Definition of Done

    No ui/shared/ primitive calls setStyleSheet() (08-D §16).
    """
    offenders = [
        path
        for path in _iter_non_test_python_files(_SHARED_ROOT)
        if _calls_setstylesheet(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_ui_shared_embeds_no_colour_literal() -> None:
    """Proves: STORY-051 Definition of Done

    No ui/shared/ primitive embeds a literal colour value; colours are resolved from
    ui/theme's role accessors only (08-D §2, §16).
    """
    offenders = [
        path
        for path in _iter_non_test_python_files(_SHARED_ROOT)
        if _embeds_colour_literal(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_ui_shared_does_not_import_asyncio_or_qasync() -> None:
    """Proves: STORY-051 Definition of Done

    ui/shared/ imports no asyncio, anyio, or qasync.
    """
    (
        archrule("ui-shared-no-asyncio")
        .match("ollama_llm_bench.ui.shared*")
        .should_not_import("asyncio")
        .should_not_import("anyio")
        .should_not_import("qasync")
        .check("ollama_llm_bench")
    )


def test_provider_dropdown_and_model_dropdown_do_not_import_each_other() -> None:
    """Proves: STORY-052 Definition of Done

    ui/shared/provider_dropdown/ and ui/shared/model_dropdown/ are independent sibling
    sub-packages with no coupling between them (01_MODULE_INVENTORY.md §6).
    """
    (
        archrule("provider-dropdown-does-not-import-model-dropdown")
        .match("ollama_llm_bench.ui.shared.provider_dropdown*")
        .should_not_import("ollama_llm_bench.ui.shared.model_dropdown")
        .check("ollama_llm_bench")
    )
    (
        archrule("model-dropdown-does-not-import-provider-dropdown")
        .match("ollama_llm_bench.ui.shared.model_dropdown*")
        .should_not_import("ollama_llm_bench.ui.shared.provider_dropdown")
        .check("ollama_llm_bench")
    )
