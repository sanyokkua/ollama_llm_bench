"""Architecture tests: ``adapters/qt_runnables/`` completes a unit's ``Future`` with no Qt
signal in the completion path, and imports no ``asyncio`` (STORY-041).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter — "no Qt signal participates in the
completion path"), §4a (the dispatcher thread — why the completion path carries no Qt
signal); ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §4 (the
threading contract).
"""

import ast
import inspect
from pathlib import Path

import pytest

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_QT_RUNNABLES_ROOT = _PACKAGE_ROOT / "adapters" / "qt_runnables"
_FORBIDDEN_IMPORT_ROOTS = ("asyncio", "anyio", "qasync")


def _iter_source_files() -> list[Path]:
    files = []
    for path in _QT_RUNNABLES_ROOT.rglob("*.py"):
        if "tests" in path.relative_to(_QT_RUNNABLES_ROOT).parts:
            continue
        files.append(path)
    return sorted(files)


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_QT_RUNNABLES_ROOT)) for path in files]
    return files, ids


def _declares_signal(tree: ast.AST) -> bool:
    """Return ``True`` if ``tree`` contains a class-body ``Signal(...)`` call anywhere."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_signal_call = (isinstance(func, ast.Name) and func.id == "Signal") or (
            isinstance(func, ast.Attribute) and func.attr == "Signal"
        )
        if is_signal_call:
            return True
    return False


def _imports_forbidden_root(tree: ast.AST) -> bool:
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    return not imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered() -> None:
    """Sanity guard for the AST walker itself: ``adapters/qt_runnables/`` has at least
    one discoverable ``.py`` source file, so the parametrized checks below are not
    vacuously true."""
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_qt_runnables_module_declares_no_signal(source_file: Path) -> None:
    """No file under ``adapters/qt_runnables/`` declares a Qt ``Signal`` anywhere — the
    unit-completion path sets the unit's ``concurrent.futures.Future`` result/exception
    directly on the worker thread, never via a queued Qt signal, because the dispatcher
    thread that blocks on that ``Future`` runs no Qt event loop and would never receive
    a queued signal.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not _declares_signal(tree)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_qt_runnables_module_imports_no_asyncio(source_file: Path) -> None:
    """Every source file under ``adapters/qt_runnables/`` imports no ``asyncio``, no
    ``anyio``, and no ``qasync`` — the Qt-backed ``TaskRunner`` adapter uses only
    ``QThreadPool``/``QRunnable`` plus the standard-library ``concurrent.futures.Future``
    to schedule and complete backend work (D-R-01).
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not _imports_forbidden_root(tree)
