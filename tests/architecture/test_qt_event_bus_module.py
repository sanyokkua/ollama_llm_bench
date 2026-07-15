"""Architecture tests: ``adapters/qt_event_bus/`` is the sole place connecting the
pure event bus to a Qt signal, and it imports no ``asyncio`` (STORY-040).

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§5 ("``adapters/qt_event_bus/`` is the only place the pure bus is connected to Qt
signals") and ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
("No ``asyncio``, ``anyio``, or ``qasync`` anywhere").
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_QT_EVENT_BUS_ROOT = _PACKAGE_ROOT / "adapters" / "qt_event_bus"


def _iter_source_files(root: Path, *, exclude: Path | None = None) -> list[Path]:
    files = []
    for path in root.rglob("*.py"):
        if "tests" in path.relative_to(root).parts:
            continue
        if exclude is not None and (path == exclude or exclude in path.parents):
            continue
        files.append(path)
    return sorted(files)


def _declares_generic_relay_signal(tree: ast.AST) -> bool:
    """Return ``True`` if ``tree`` contains a class-body ``Signal(str, object)`` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_signal_call = (isinstance(func, ast.Name) and func.id == "Signal") or (
            isinstance(func, ast.Attribute) and func.attr == "Signal"
        )
        if not is_signal_call:
            continue
        arg_names = [arg.id for arg in node.args if isinstance(arg, ast.Name)]
        if arg_names == ["str", "object"]:
            return True
    return False


def _imports_asyncio(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "asyncio" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            return True
    return False


def test_only_qt_event_bus_declares_the_generic_relay_signal() -> None:
    """No file outside ``adapters/qt_event_bus/`` declares a ``Signal(str, object)``
    call — the generic relay signal that marshals every ``EventBus`` emission onto
    the Qt GUI thread is a design decision private to the Qt event-bus adapter; no
    other module reinvents a parallel channel of this exact shape."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_PACKAGE_ROOT, exclude=_QT_EVENT_BUS_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _declares_generic_relay_signal(tree):
            offending_files.append(str(source_file.relative_to(_PACKAGE_ROOT)))

    # Assert
    assert offending_files == []


def test_qt_event_bus_never_imports_asyncio() -> None:
    """``adapters/qt_event_bus/`` never imports ``asyncio``, per the concurrency
    standard's synchronous-backend-plus-Qt-thread-pool model."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_QT_EVENT_BUS_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_asyncio(tree):
            offending_files.append(str(source_file.relative_to(_PACKAGE_ROOT)))

    # Assert
    assert offending_files == []
