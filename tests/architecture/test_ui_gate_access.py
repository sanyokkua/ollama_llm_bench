"""Architecture tests: the UI observes the inference-activity gate only through
``adapters/qt_inference_activity_bridge/``, and that bridge imports no ``asyncio``
(STORY-043).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§13 ("the UI observes the gate only through the adapter, never the store directly") and
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` ("No
``asyncio``, ``anyio``, or ``qasync`` anywhere"). Modelled on
``tests/architecture/test_qt_event_bus_module.py`` (STORY-040) and
``tests/architecture/test_stores_module.py`` (STORY-039).
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_UI_ROOT = _PACKAGE_ROOT / "ui"
_BRIDGE_ROOT = _PACKAGE_ROOT / "adapters" / "qt_inference_activity_bridge"
_GATE_MODULE = "ollama_llm_bench.backend.stores.inference_activity"
_FORBIDDEN_IMPORT_ROOTS = ("asyncio", "anyio", "qasync")


def _iter_source_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _imports_gate_module(tree: ast.AST) -> bool:
    """Return ``True`` if ``tree`` imports ``backend/stores/inference_activity/`` (or any
    of its sub-modules) directly, by any of the import spellings this codebase uses."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == _GATE_MODULE or alias.name.startswith(_GATE_MODULE + ".")
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == _GATE_MODULE or node.module.startswith(_GATE_MODULE + "."):
                return True
            if node.module == f"{_GATE_MODULE}".rsplit(".", 1)[0] and any(
                alias.name == "inference_activity" for alias in node.names
            ):
                return True
    return False


def _imports_forbidden_concurrency_root(tree: ast.AST) -> bool:
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    return not imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def _find_gate_importers() -> list[str]:
    offending: list[str] = []
    for source_file in _iter_source_files(_UI_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_gate_module(tree):
            offending.append(str(source_file.relative_to(_PACKAGE_ROOT)))
    return offending


def _find_forbidden_concurrency_importers() -> list[str]:
    offending: list[str] = []
    for source_file in _iter_source_files(_BRIDGE_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_forbidden_concurrency_root(tree):
            offending.append(str(source_file.relative_to(_PACKAGE_ROOT)))
    return offending


def test_at_least_one_ui_source_file_discovered() -> None:
    """Sanity guard for the AST walker itself: ``ui/`` has at least one discoverable
    ``.py`` source file, so the check below is not vacuously true."""
    # Assert
    assert len(_iter_source_files(_UI_ROOT)) > 0


def test_gate_observed_only_through_bridge_on_gui_thread() -> None:
    """Proves: STORY-043-AC-3

    Given a subscriber wired only through ``adapters/qt_inference_activity_bridge/``,
    no file under ``ui/`` imports ``backend/stores/inference_activity/`` (the
    ``InferenceActivityStore``) directly — the UI never subscribes to or imports the
    backend gate itself; it observes gate changes only through the bridge.

    This AST walker proves only the import-isolation half of AC-3. The other half —
    "the subscriber's handler runs on the Qt main thread" — is a runtime property no
    static walker can assert; it is proven by
    ``tests/integration/test_qt_inference_activity_bridge.py::
    test_gate_change_forwards_one_typed_event_on_gui_thread`` (STORY-043-AC-1), which
    subscribes through this same ``bridge.subscribe(...)`` call and asserts the handler's
    ``QThread.currentThread()`` is the GUI thread.
    """
    # Arrange / Act
    offending_files = _find_gate_importers()

    # Assert
    assert offending_files == []


def test_qt_inference_activity_bridge_never_imports_asyncio() -> None:
    """``adapters/qt_inference_activity_bridge/`` imports no ``asyncio``, ``anyio``, or
    ``qasync``, per the concurrency standard's synchronous-backend-plus-Qt-thread-pool
    model."""
    # Arrange / Act
    offending_files = _find_forbidden_concurrency_importers()

    # Assert
    assert offending_files == []
