"""Architecture tests: ``adapters/store_qt_bridge/`` is the sole adapter allowed to subscribe
to a psygnal signal, and it imports no ``asyncio`` (STORY-044).

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§5 ("``store_qt_bridge`` ... is the only adapter allowed to subscribe to a psygnal signal from
a Qt thread") and ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
("No ``asyncio``, ``anyio``, or ``qasync`` anywhere").
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_STORE_QT_BRIDGE_ROOT = _PACKAGE_ROOT / "adapters" / "store_qt_bridge"
_ALLOWED_PSYGNAL_IMPORTER_PREFIXES = ("adapters/store_qt_bridge/", "backend/stores/")


def _iter_source_files(root: Path, *, exclude: Path | None = None) -> list[Path]:
    files = []
    for path in root.rglob("*.py"):
        if "tests" in path.relative_to(root).parts:
            continue
        if exclude is not None and (path == exclude or exclude in path.parents):
            continue
        files.append(path)
    return sorted(files)


def _imports_psygnal(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "psygnal" or alias.name.startswith("psygnal.") for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == "psygnal" or node.module.startswith("psygnal."))
        ):
            return True
    return False


def _imports_asyncio(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "asyncio" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            return True
    return False


def test_only_store_qt_bridge_and_backend_stores_import_psygnal() -> None:
    """No file outside ``adapters/store_qt_bridge/`` or ``backend/stores/`` imports
    ``psygnal`` — those are the only two modules allowed to know about psygnal signals
    (``store_qt_bridge`` is the sole adapter subscribing to one from a Qt thread; the
    stores own the signals in the first place)."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_PACKAGE_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if not _imports_psygnal(tree):
            continue
        relative_path = source_file.relative_to(_PACKAGE_ROOT).as_posix()
        if not relative_path.startswith(_ALLOWED_PSYGNAL_IMPORTER_PREFIXES):
            offending_files.append(relative_path)

    # Assert
    assert offending_files == []


def test_store_qt_bridge_never_imports_asyncio() -> None:
    """``adapters/store_qt_bridge/`` never imports ``asyncio``, per the concurrency
    standard's synchronous-backend-plus-Qt-thread-pool model."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_STORE_QT_BRIDGE_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_asyncio(tree):
            offending_files.append(str(source_file.relative_to(_PACKAGE_ROOT)))

    # Assert
    assert offending_files == []
