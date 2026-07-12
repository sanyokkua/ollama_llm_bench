"""Architecture test: backend/mode_visibility/ imports no Qt, no asyncio (STORY-024).

Source of truth: the generic "Backend layer is Qt-free" import-linter contract in
pyproject.toml already forbids PySide6 for every backend/* package including
backend.mode_visibility (pyproject.toml, "Backend layer is Qt-free" contract,
source_modules) -- this test adds an explicit, module-scoped AST check plus the
asyncio/async def prohibition that import-linter alone cannot express, mirroring
tests/architecture/test_concurrency_module.py (STORY-006) and
tests/architecture/test_provider_registry_module.py (STORY-017).
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import mode_visibility

_MODE_VISIBILITY_PACKAGE_ROOT = Path(inspect.getfile(mode_visibility)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")


def _iter_source_files() -> list[Path]:
    return sorted(_MODE_VISIBILITY_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_MODE_VISIBILITY_PACKAGE_ROOT)) for path in files]
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered() -> None:
    """Proves: STORY-024-AC-1

    Sanity guard for the AST walker itself: backend/mode_visibility/ has at
    least one discoverable .py source file, so the parametrized checks below
    are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_mode_visibility_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-024-AC-1

    Every source file under backend/mode_visibility/ (including its colocated
    tests) imports no PySide6, no asyncio, no anyio, and no qasync.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    # Assert
    assert imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_mode_visibility_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-024-AC-1

    Every source file under backend/mode_visibility/ defines no async def
    function -- the module is ordinary synchronous, blocking Python.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
