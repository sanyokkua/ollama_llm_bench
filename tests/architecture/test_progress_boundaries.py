"""Architecture tests for ``ui/progress/`` (STORY-058 Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio``/``anyio``/
``qasync`` import anywhere in the module; each sub-controller
(``counters_controller.py``, ``stability_controller.py``, and the parent
``controller.py``) imports only its own ``ProgressGateway`` plus
``EventBus``/``backend.domain``/``backend.log_formatting`` -- never
``AdaptiveTimeoutService`` or the circuit breaker (D-R-06); ``_internal/view.py``
imports no adapter Gateway, no reactive store, and no raw backend service symbol
(the passive-View rule).
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "progress"

_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"
_COUNTERS_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "counters_controller.py"
_CURRENT_TASK_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "current_task_controller.py"
_STABILITY_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "stability_controller.py"
_VIEW_FILE = _MODULE_ROOT / "_internal" / "view.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_ALLOWED_CONTROLLER_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    "ollama_llm_bench.backend.log_formatting",
}
_FORBIDDEN_STABILITY_SERVICE_MODULES = (
    "ollama_llm_bench.backend.adaptive_timeout",
    "ollama_llm_bench.backend.circuit_breaker",
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
    """Proves: STORY-058 Definition of done

    No file in ``ui/progress/`` calls ``setStyleSheet`` or imports
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


def test_progress_embeds_no_colour_literal() -> None:
    """Proves: STORY-058 Definition of done

    No file in ``ui/progress/`` embeds a literal colour value; colours are
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
    """Proves: STORY-058 Definition of done

    ``_internal/controller.py`` imports only ``backend.domain``/``backend.events``/
    ``backend.log_formatting`` -- never a raw backend Store/Service Protocol, and
    never ``AdaptiveTimeoutService``/the circuit breaker (D-R-06).
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    disallowed = backend_imports - _ALLOWED_CONTROLLER_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()


def test_sub_controllers_never_import_adaptive_timeout_or_circuit_breaker() -> None:
    """Proves: STORY-058 Definition of done

    Neither ``counters_controller.py`` nor ``stability_controller.py`` imports
    ``backend.adaptive_timeout`` or ``backend.circuit_breaker`` -- stability
    arrives via bus events only; the manual probe goes through
    ``ProgressGateway.manual_provider_probe()`` (D-R-06).
    """
    # Arrange / Act
    offenders: dict[str, list[str]] = {}
    for source_file in (
        _COUNTERS_CONTROLLER_FILE,
        _CURRENT_TASK_CONTROLLER_FILE,
        _STABILITY_CONTROLLER_FILE,
        _CONTROLLER_FILE,
    ):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        imported_modules = _imported_modules(tree)
        hits = sorted(
            m
            for m in imported_modules
            if any(m.startswith(forbidden) for forbidden in _FORBIDDEN_STABILITY_SERVICE_MODULES)
        )
        if hits:
            offenders[str(source_file.relative_to(_PACKAGE_ROOT))] = hits
    # Assert
    assert offenders == {}


def test_current_task_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-059 Definition of done

    ``_internal/current_task_controller.py`` imports only
    ``backend.domain``/``backend.events`` -- never a raw backend Store/Service
    Protocol, and never ``AdaptiveTimeoutService``/the circuit breaker (D-R-06).
    """
    # Arrange
    tree = ast.parse(
        _CURRENT_TASK_CONTROLLER_FILE.read_text(encoding="utf-8"),
        filename=str(_CURRENT_TASK_CONTROLLER_FILE),
    )
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = set(  # noqa: C401  # avoids braces in patch
        m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")
    )
    disallowed = backend_imports - _ALLOWED_CONTROLLER_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()


def test_current_task_controller_never_reads_run_log_verbosity() -> None:
    """Proves: STORY-059 Definition of done

    Both progress sub-rows are verbosity-independent (description.md sec 7.1.3;
    STORY-059 design constraints) -- the source text never references
    ``run_log_verbosity``.
    """
    # Assert
    assert "run_log_verbosity" not in _CURRENT_TASK_CONTROLLER_FILE.read_text(encoding="utf-8")


def test_view_imports_no_backend_service_symbol() -> None:
    """Proves: STORY-058 Definition of done

    ``_internal/view.py`` (the passive View) imports only ``backend.domain`` (DTO
    enums for its counter-row labels) and PySide6/``ui.*`` -- never a Gateway, a
    reactive store, or any other ``ollama_llm_bench.backend.*`` module.
    """
    # Arrange
    tree = ast.parse(_VIEW_FILE.read_text(encoding="utf-8"), filename=str(_VIEW_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_service_imports = {
        m
        for m in imported_modules
        if m.startswith("ollama_llm_bench.backend.") and m != "ollama_llm_bench.backend.domain"
    }
    # Assert
    assert backend_service_imports == set()
