"""Architecture test: backend/stores/ imports no Qt, no asyncio (STORY-039).

Source of truth: the generic "Backend layer is Qt-free" import-linter contract in
pyproject.toml already forbids PySide6 for every backend/* package including
backend.stores (pyproject.toml, "Backend layer is Qt-free" contract, source_modules) -- this
test adds an explicit, module-scoped AST check plus the asyncio/async def prohibition that
import-linter alone cannot express, mirroring tests/architecture/test_mode_visibility_module.py
(STORY-024). This walk also harmlessly covers the already Qt-free
backend/stores/inference_activity/ sub-feature (STORY-015).
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import stores

_STORES_PACKAGE_ROOT = Path(inspect.getfile(stores)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")


def _iter_source_files() -> list[Path]:
    return sorted(_STORES_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_STORES_PACKAGE_ROOT)) for path in files]
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered() -> None:
    """Proves: STORY-039-AC-7

    Sanity guard for the AST walker itself: backend/stores/ has at least one
    discoverable .py source file, so the parametrized checks below are not
    vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_stores_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-039-AC-7

    Every source file under backend/stores/ (including its colocated tests and
    the inference_activity sub-feature) imports no PySide6, no asyncio, no
    anyio, and no qasync.
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
def test_stores_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-039-AC-7

    Every source file under backend/stores/ defines no async def function --
    the module is ordinary synchronous, blocking Python.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
