"""Architecture test: ``backend/inference_progress/`` imports no Qt and no ``asyncio``
(STORY-035, ADR-0006).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§11 (concurrency stack: stdlib + Qt only — no ``asyncio``, no ``anyio``); the generic
"Backend layer is Qt-free" import-linter contract in ``pyproject.toml`` already forbids
``PySide6`` for ``backend.inference_progress`` — this test adds an explicit, module-scoped
AST check plus the ``asyncio``/``async def`` prohibition that import-linter alone cannot
express, mirroring ``tests/architecture/test_settings_module.py`` (STORY-014).
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import inference_progress

_INFERENCE_PROGRESS_PACKAGE_ROOT = Path(inspect.getfile(inference_progress)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")


def _iter_source_files() -> list[Path]:
    return sorted(_INFERENCE_PROGRESS_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_INFERENCE_PROGRESS_PACKAGE_ROOT)) for path in files]
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered() -> None:
    """Proves: STORY-035-AC-8

    Sanity guard for the AST walker itself: ``backend/inference_progress/``
    has at least one discoverable ``.py`` source file, so the parametrized
    checks below are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_inference_progress_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-035-AC-8

    Every source file under ``backend/inference_progress/`` (including its
    colocated tests) imports no ``PySide6``, no ``asyncio``, no ``anyio``,
    and no ``qasync`` — the shared inference-progress helper stays Qt-free
    and asyncio-free (D-R-01).
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
def test_inference_progress_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-035-AC-8

    Every source file under ``backend/inference_progress/`` defines no
    ``async def`` function (DD-43) — the module is ordinary synchronous,
    blocking Python with no event-loop or coroutine scheduling of any kind.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
