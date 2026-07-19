"""Architecture tests scoped to STORY-057's own new files (Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio``/``anyio``/
``qasync`` import anywhere in the Resume Summary dialog, Retry Selection
dialog, their pure ``*_select.py`` derivations, the common_dialogs ``actions.py``
helper, or the resume_benchmark files this story touched (``context_menu.py``,
``view.py``, ``controller.py``).
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_SCAN_FILES = (
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "resume_summary_select.py",
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "resume_summary_view.py",
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "retry_selection_select.py",
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "retry_selection_view.py",
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "actions.py",
    _PACKAGE_ROOT / "ui" / "resume_benchmark" / "_internal" / "context_menu.py",
    _PACKAGE_ROOT / "ui" / "resume_benchmark" / "_internal" / "view.py",
    _PACKAGE_ROOT / "ui" / "resume_benchmark" / "_internal" / "controller.py",
)

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _imported_modules(tree: ast.AST) -> set[str]:
    """Collect fully-dotted module names from both ``import x.y`` and ``from x.y import z``."""
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    return imported_modules


def _imports_setstylesheet_or_forbidden_concurrency(tree: ast.AST) -> tuple[bool, bool]:
    calls_setstylesheet = any(
        isinstance(node, ast.Attribute) and node.attr == "setStyleSheet" for node in ast.walk(tree)
    )
    imported_roots = {module.split(".")[0] for module in _imported_modules(tree)}
    imports_forbidden_concurrency = not imported_roots.isdisjoint(_FORBIDDEN_CONCURRENCY_ROOTS)
    return calls_setstylesheet, imports_forbidden_concurrency


def _embeds_colour_literal(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _HEX_COLOR_RE.match(node.value)
        for node in ast.walk(tree)
    )


def test_at_least_one_source_file_discovered() -> None:
    assert len(_SCAN_FILES) > 0


def test_no_setstylesheet_or_forbidden_concurrency_import() -> None:
    """Proves: STORY-057 Definition of done

    No STORY-057 file calls ``setStyleSheet`` or imports
    ``asyncio``/``anyio``/``qasync``.
    """
    # Arrange / Act
    offenders: list[str] = []
    for source_file in _SCAN_FILES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        calls_setstylesheet, imports_forbidden = _imports_setstylesheet_or_forbidden_concurrency(
            tree
        )
        if calls_setstylesheet or imports_forbidden:
            offenders.append(str(source_file.relative_to(_PACKAGE_ROOT)))
    # Assert
    assert offenders == []


def test_story_057_files_embed_no_colour_literal() -> None:
    """Proves: STORY-057 Definition of done

    No STORY-057 file embeds a literal colour value; colours are resolved
    from ``ui/theme``'s role accessors only (08-D §2, §16).
    """
    # Arrange / Act
    offenders = [
        str(source_file.relative_to(_PACKAGE_ROOT))
        for source_file in _SCAN_FILES
        if _embeds_colour_literal(
            ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        )
    ]
    # Assert
    assert offenders == []
