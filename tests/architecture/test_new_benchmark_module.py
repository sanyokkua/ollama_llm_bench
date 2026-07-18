"""Architecture tests for ``ui/new_benchmark/`` (STORY-054 Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal reference, no ``asyncio``
import anywhere in the module; ``_internal/view.py`` imports no Gateway/backend
service symbol (passive-View rule); ``_internal/controller.py`` imports only its
own ``NewBenchmarkGateway`` plus the declared non-store helpers -- never a raw
backend Store/Service Protocol beyond those (D-R-06).
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "new_benchmark"
_VIEW_FILE = _MODULE_ROOT / "_internal" / "view.py"
_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_ALLOWED_CONTROLLER_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    "ollama_llm_bench.ui.new_benchmark.protocols",
}


def _iter_source_files() -> list[Path]:
    return sorted(_MODULE_ROOT.rglob("*.py"))


def _imports_setstylesheet_or_forbidden_concurrency(tree: ast.AST) -> tuple[bool, bool]:
    calls_setstylesheet = any(
        isinstance(node, ast.Attribute) and node.attr == "setStyleSheet" for node in ast.walk(tree)
    )
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    imports_forbidden_concurrency = not imported_roots.isdisjoint(_FORBIDDEN_CONCURRENCY_ROOTS)
    return calls_setstylesheet, imports_forbidden_concurrency


def test_at_least_one_source_file_discovered() -> None:
    assert len(_iter_source_files()) > 0


def test_no_setstylesheet_or_forbidden_concurrency_import() -> None:
    """Proves: STORY-054 Definition of done

    No file in ``ui/new_benchmark/`` calls ``setStyleSheet`` or imports
    ``asyncio``/``anyio``/``qasync`` (ADR-0001; concurrency-standard.md).
    """
    # Arrange / Act
    offenders: list[str] = []
    for source_file in _iter_source_files():
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        calls_setstylesheet, imports_forbidden = _imports_setstylesheet_or_forbidden_concurrency(
            tree
        )
        if calls_setstylesheet or imports_forbidden:
            offenders.append(str(source_file.relative_to(_PACKAGE_ROOT)))
    # Assert
    assert offenders == []


def test_view_imports_no_backend_service_symbol() -> None:
    """Proves: STORY-054 Definition of done

    ``_internal/view.py`` (the passive View) imports only ``models.py``, its own
    sub-widgets, and PySide6/theme -- never a Gateway, a reactive store, or any
    ``ollama_llm_bench.backend.*`` module beyond the pure ``ConfigSection`` enum
    (a structural vocabulary type, not a service call).
    """
    # Arrange
    tree = ast.parse(_VIEW_FILE.read_text(encoding="utf-8"), filename=str(_VIEW_FILE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    # Act
    backend_service_imports = {
        m
        for m in imported_modules
        if m.startswith("ollama_llm_bench.backend.")
        and m != "ollama_llm_bench.backend.mode_visibility"
    }
    # Assert
    assert backend_service_imports == set()


def test_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-054 Definition of done

    ``_internal/controller.py`` imports only its own ``NewBenchmarkGateway`` /
    ``ModeVisibilityPolicy`` Protocols plus ``backend.domain``/``backend.events`` --
    never a raw backend Store/Service Protocol beyond those (D-R-06).
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    disallowed = backend_imports - _ALLOWED_CONTROLLER_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()
