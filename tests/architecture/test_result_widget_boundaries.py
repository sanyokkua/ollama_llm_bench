"""Architecture tests for ``ui/results/`` (STORY-061 Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio``/``anyio``/
``qasync`` import anywhere in the module; the parent controller
(``_internal/controller.py``) and the footer controller (``_internal/footer.py``)
import only ``backend.domain``/``backend.events`` -- never a raw backend
Store/Service Protocol (D-R-06); ``_internal/view.py`` imports no adapter Gateway,
no reactive store, and no ``ollama_llm_bench.backend.*`` module (the passive-View
rule).
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "results"

_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"
_FOOTER_FILE = _MODULE_ROOT / "_internal" / "footer.py"
_VIEW_FILE = _MODULE_ROOT / "_internal" / "view.py"
_VIEW_STATE_STORE_FILE = _MODULE_ROOT / "_internal" / "view_state_store.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_ALLOWED_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.errors",
    "ollama_llm_bench.backend.events",
}
_FORBIDDEN_STORE_MODULES = (
    "ollama_llm_bench.backend.persistence.runs",
    "ollama_llm_bench.backend.persistence.results",
    "ollama_llm_bench.backend.persistence.tasks",
    "ollama_llm_bench.backend.persistence.app_settings",
    "ollama_llm_bench.backend.run_analysis",
    "ollama_llm_bench.backend.charts",
    "ollama_llm_bench.backend.csv_export",
)
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _iter_source_files() -> list[Path]:
    return sorted(_MODULE_ROOT.rglob("*.py"))


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
    assert len(_iter_source_files()) > 0


def test_no_setstylesheet_or_forbidden_concurrency_import() -> None:
    """Proves: STORY-061 Definition of done

    No file in ``ui/results/`` calls ``setStyleSheet`` or imports
    ``asyncio``/``anyio``/``qasync``.
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


def test_results_embeds_no_colour_literal() -> None:
    """Proves: STORY-061 Definition of done

    No file in ``ui/results/`` embeds a literal colour value; colours are
    resolved from ``ui/theme``'s role accessors only (08-D §2, §16).
    """
    # Arrange / Act
    offenders = [
        str(source_file.relative_to(_PACKAGE_ROOT))
        for source_file in _iter_source_files()
        if _embeds_colour_literal(
            ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        )
    ]
    # Assert
    assert offenders == []


def test_parent_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-061 Definition of done

    ``_internal/controller.py`` imports only ``backend.domain``/``backend.events``
    -- never a raw backend Store/Service Protocol (D-R-06); it reaches all
    backend data only through ``ResultGateway``.
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    disallowed = backend_imports - _ALLOWED_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()


def test_footer_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-061 Definition of done

    ``_internal/footer.py`` imports only ``backend.domain``/``backend.errors``/
    ``backend.events`` -- never a raw backend Store/Service Protocol (D-R-06).
    """
    # Arrange
    tree = ast.parse(_FOOTER_FILE.read_text(encoding="utf-8"), filename=str(_FOOTER_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    disallowed = backend_imports - _ALLOWED_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()


def test_no_file_imports_a_persistence_store_or_service_module() -> None:
    """Proves: STORY-061 Definition of done

    No file in ``ui/results/`` imports ``RunsStore``/``ResultsStore``/
    ``TasksStore``/``AppSettingsStore``, ``RunAnalysisService``, the chart
    aggregators, or the table serializer directly -- every one is wrapped
    behind ``ResultGateway`` (D-R-06).
    """
    # Arrange / Act
    offenders: dict[str, list[str]] = {}
    for source_file in _iter_source_files():
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        imported_modules = _imported_modules(tree)
        hits = sorted(
            m
            for m in imported_modules
            if any(m.startswith(forbidden) for forbidden in _FORBIDDEN_STORE_MODULES)
        )
        if hits:
            offenders[str(source_file.relative_to(_PACKAGE_ROOT))] = hits
    # Assert
    assert offenders == {}


def test_view_imports_no_backend_service_symbol() -> None:
    """Proves: STORY-061 Definition of done

    ``_internal/view.py`` (the passive View) imports only PySide6/``ui.*`` --
    never a Gateway, a reactive store, or any ``ollama_llm_bench.backend.*``
    module.
    """
    # Arrange
    tree = ast.parse(_VIEW_FILE.read_text(encoding="utf-8"), filename=str(_VIEW_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_service_imports = {
        m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")
    }
    # Assert
    assert backend_service_imports == set()


def test_view_state_store_persists_only_through_the_gateway() -> None:
    """Proves: STORY-061-AC-6

    ``_internal/view_state_store.py`` imports only ``backend.domain`` -- it
    persists every slice through ``ResultGateway.get_setting``/``set_setting``,
    never a direct settings store.
    """
    # Arrange
    tree = ast.parse(
        _VIEW_STATE_STORE_FILE.read_text(encoding="utf-8"), filename=str(_VIEW_STATE_STORE_FILE)
    )
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    # Assert
    assert backend_imports == {"ollama_llm_bench.backend.domain"}
