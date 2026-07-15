"""Architecture test: ``backend/log_file_writer/`` imports no Qt and no ``asyncio``
(STORY-037).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§11 (concurrency stack: stdlib + Qt only — no ``asyncio``, no ``anyio``) and
``01_MODULE_INVENTORY.md`` §4.5. The generic "Backend layer is Qt-free" import-linter
contract in ``pyproject.toml`` already forbids ``PySide6`` for the module — this test
adds an explicit, module-scoped AST check plus the ``asyncio``/``async def`` prohibition
that import-linter alone cannot express.
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import log_file_writer

_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")
_MODULE_ROOTS = {
    "log_file_writer": Path(inspect.getfile(log_file_writer)).parent,
}


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    ids: list[str] = []
    for module_name, root in _MODULE_ROOTS.items():
        for source_file in sorted(root.rglob("*.py")):
            files.append(source_file)
            ids.append(f"{module_name}/{source_file.relative_to(root)}")
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered_per_module() -> None:
    """Sanity guard for the AST walker itself: the module has discoverable source."""
    assert len(_SOURCE_FILES) >= len(_MODULE_ROOTS)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Every source file (including colocated tests) imports no ``PySide6``, no
    ``asyncio``, no ``anyio``, and no ``qasync`` — the module stays Qt-free and
    asyncio-free (D-R-01).
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_defines_no_async_function(source_file: Path) -> None:
    """Every source file defines no ``async def`` function (DD-43) — the module is
    ordinary synchronous, blocking Python with no event-loop or coroutine scheduling.
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
