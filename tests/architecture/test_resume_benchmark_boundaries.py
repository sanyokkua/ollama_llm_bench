"""Architecture tests for ``ui/resume_benchmark/`` and the STORY-056 additions to
``ui/common_dialogs/`` (STORY-056 Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio`` import
anywhere in either module's STORY-056 files; ``_internal/controller.py``
imports only its own ``ResumeGateway`` plus ``EventBus``/``NativePickers``/
``FileSystemActions`` and its own ``models``/``protocols`` -- never a raw
``RunsStore``/``ResultsStore``/``TasksStore`` (D-R-06), plus ``backend.run_drift``
for the ``DriftWarning`` DTO STORY-057's ``detect_drift`` wiring needs
(DTO-only use, mirroring the existing ``backend.domain``/``backend.events``
precedent); ``_internal/actions.py`` (the export path) imports no redaction
function; ``_internal/view.py`` imports no Gateway/EventBus/backend symbol
(the passive-View rule).
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "resume_benchmark"
_COMMON_DIALOGS_ROOT = _PACKAGE_ROOT / "ui" / "common_dialogs"
_RENAME_RUN_FILES = (
    _COMMON_DIALOGS_ROOT / "_internal" / "rename_run_view.py",
    _COMMON_DIALOGS_ROOT / "_internal" / "rename_run_select.py",
)
_SCAN_ROOTS = (_MODULE_ROOT,)
_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"
_ACTIONS_FILE = _MODULE_ROOT / "_internal" / "actions.py"
_VIEW_FILE = _MODULE_ROOT / "_internal" / "view.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_ALLOWED_CONTROLLER_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    "ollama_llm_bench.backend.run_drift",
}
_FORBIDDEN_STORE_MODULES = (
    "ollama_llm_bench.backend.persistence.runs",
    "ollama_llm_bench.backend.persistence.results",
    "ollama_llm_bench.backend.persistence.tasks",
)
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    files.extend(_RENAME_RUN_FILES)
    return files


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
    """Proves: STORY-056 Definition of done

    No file in ``ui/resume_benchmark/`` or this story's rename_run files
    calls ``setStyleSheet`` or imports ``asyncio``/``anyio``/``qasync``.
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


def test_resume_benchmark_embeds_no_colour_literal() -> None:
    """Proves: STORY-056 Definition of done

    No file in ``ui/resume_benchmark/`` or this story's rename_run files
    embeds a literal colour value; colours are resolved from ``ui/theme``'s
    role accessors only (08-D §2, §16).
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


def test_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-056 Definition of done

    ``_internal/controller.py`` imports only ``backend.domain``/``backend.events``/
    ``backend.run_drift`` (which carry the ``ResumeGateway``-adjacent DTOs/signals
    it needs, ``backend.run_drift`` DTO-only for ``DriftWarning``) -- never a raw
    backend persistence Store Protocol beyond those (D-R-06).
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    disallowed = backend_imports - _ALLOWED_CONTROLLER_BACKEND_IMPORTS
    # Assert
    assert disallowed == set()


def test_controller_never_imports_a_persistence_store_module() -> None:
    """Proves: STORY-056 Definition of done

    No file in ``ui/resume_benchmark/`` imports ``RunsStore``/``ResultsStore``/
    ``TasksStore`` (or their owning persistence packages) directly.
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


def test_actions_module_imports_no_redaction_function() -> None:
    """Proves: STORY-056 Definition of done

    ``_internal/actions.py`` (the export path) imports no ``redact``/
    ``redact_for_log`` function -- exports are written verbatim (own-machine
    data), per the story's design constraint and 10_Domain_and_Data
    /08_REDACTION_PATTERNS.md §1.
    """
    # Arrange
    tree = ast.parse(_ACTIONS_FILE.read_text(encoding="utf-8"), filename=str(_ACTIONS_FILE))
    # Act
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    # Assert
    assert "redact" not in imported_names
    assert "redact_for_log" not in imported_names


def test_controller_module_imports_no_redaction_function() -> None:
    """Proves: STORY-072 Definition of done

    ``_internal/controller.py`` -- which wires the four Summary/Details
    export menu actions to ``export_table`` -- imports no ``redact``/
    ``redact_for_log`` function either; the export path stays verbatim
    end-to-end (05_EXPORT_FORMATS.md section 3).
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    # Act
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    # Assert
    assert "redact" not in imported_names
    assert "redact_for_log" not in imported_names


def test_view_imports_no_backend_service_symbol() -> None:
    """Proves: STORY-056 Definition of done

    ``_internal/view.py`` (the passive View) imports only its own
    ``controller`` module and PySide6 -- never a Gateway, a reactive store,
    or any ``ollama_llm_bench.backend.*`` module.
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
