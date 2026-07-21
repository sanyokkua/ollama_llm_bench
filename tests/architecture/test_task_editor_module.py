"""Architecture tests for ``ui/task_editor/`` (STORY-068, STORY-069 Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio``/``anyio``/
``qasync`` import anywhere in the module; ``_internal/controller.py`` imports
only its own ``TaskEditorGateway`` plus the declared non-store helpers
(``EventBus``, ``TaskFileLoader``, ``TaskFileValidator``, ``YamlFormatter``,
``FileChangeWatcher``, ``NativePickers``, ``FileSystemActions``) and its own
``models``/``protocols`` -- never a raw ``SettingsService``/``WorkspaceStore``/
``RunRegistryStore`` Protocol (D-R-06); ``_internal/view.py`` imports no
Gateway/EventBus/backend symbol (the passive-View rule); no file in the module
imports the real YAML parse/dump engine (``ruamel.yaml``'s ``YAML`` class) --
every load/save is delegated to ``YamlFormatter``/``TaskFileValidator``
(STORY-069's own controller docstring claim). ``ruamel.yaml.comments`` is the
one allowed exception: ``_internal/buffer.py`` imports only its
``CommentedMap``/``CommentedSeq`` data-container types to mutate an
already-parsed document in place -- never to parse or serialize YAML text
itself.
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "task_editor"
_SCAN_ROOTS = (_MODULE_ROOT,)
_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"
_VIEW_FILE = _MODULE_ROOT / "_internal" / "view.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_ALLOWED_CONTROLLER_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.events",
}
_ALLOWED_CONTROLLER_ADAPTER_IMPORTS = {
    "ollama_llm_bench.adapters.native_pickers",
}
_FORBIDDEN_STORE_MODULES = (
    "ollama_llm_bench.backend.persistence.runs",
    "ollama_llm_bench.backend.persistence.results",
    "ollama_llm_bench.backend.persistence.tasks",
    "ollama_llm_bench.backend.stores",
    "ollama_llm_bench.backend.settings",
)
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ALLOWED_RUAMEL_IMPORT = "ruamel.yaml.comments"


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    return [source_file for source_file in files if "tests" not in source_file.parts]


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
    """Proves: STORY-068 Definition of done

    No file in ``ui/task_editor/`` calls ``setStyleSheet`` or imports
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


def test_task_editor_embeds_no_colour_literal() -> None:
    """Proves: STORY-068 Definition of done

    No file in ``ui/task_editor/`` embeds a literal colour value (hex triplet,
    6-digit, or 8-digit-with-alpha); the module renders badges as plain text
    glyphs (no ``ThemeManager`` collaborator this story -- see the story's
    Notes) and colours are otherwise resolved from ``ui/theme``'s role
    accessors only (08-D §2, §16).
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
    """Proves: STORY-068 Definition of done

    ``_internal/controller.py`` imports only ``backend.events`` (the
    ``EventBus`` Protocol, signal-name constants, and event payload types) plus
    ``adapters.native_pickers`` (the picker-options structs) as its
    project-internal, non-``ui.task_editor`` dependencies -- never a raw
    ``SettingsService``/``WorkspaceStore``/``RunRegistryStore`` Protocol or any
    other backend Store/Service beyond the declared ``TaskEditorGateway`` and
    non-store helpers (D-R-06).
    """
    # Arrange
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    imported_modules = _imported_modules(tree)
    # Act
    backend_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.backend.")}
    adapter_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.adapters.")}
    disallowed_backend = backend_imports - _ALLOWED_CONTROLLER_BACKEND_IMPORTS
    disallowed_adapters = adapter_imports - _ALLOWED_CONTROLLER_ADAPTER_IMPORTS
    # Assert
    assert disallowed_backend == set()
    assert disallowed_adapters == set()


def test_controller_never_imports_a_persistence_or_reactive_store_module() -> None:
    """Proves: STORY-068 Definition of done

    No file in ``ui/task_editor/`` imports ``RunsStore``/``ResultsStore``/
    ``TasksStore``, the reactive ``backend.stores`` package (``WorkspaceStore``/
    ``RunRegistryStore``), or ``backend.settings`` (``SettingsService``)
    directly -- the controller reaches all of them only through its own
    ``TaskEditorGateway`` (D-R-06).
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
    """Proves: STORY-068 Definition of done

    ``_internal/view.py`` (the passive root View) imports only its own
    sub-widgets (toolbar/files_pane/tasks_pane), ``models.py``, and PySide6 --
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


def test_no_file_imports_the_real_yaml_parse_or_dump_engine() -> None:
    """Proves: STORY-069 Definition of done

    No file in ``ui/task_editor/`` imports ``ruamel.yaml``'s ``YAML``
    parser/dumper (or any other ``ruamel.yaml`` submodule) directly -- every
    YAML load/save is delegated to the ``YamlFormatter``/``TaskFileValidator``
    Protocols. ``ruamel.yaml.comments`` (``CommentedMap``/``CommentedSeq``,
    used only to mutate an already-parsed document in place) is the sole
    permitted import, matching ``_internal/buffer.py``'s own docstring claim.
    """
    # Arrange / Act
    offenders: dict[str, list[str]] = {}
    for source_file in _iter_source_files():
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        imported_modules = _imported_modules(tree)
        hits = sorted(
            module
            for module in imported_modules
            if (module == "ruamel.yaml" or module.startswith("ruamel.yaml."))
            and module != _ALLOWED_RUAMEL_IMPORT
        )
        if hits:
            offenders[str(source_file.relative_to(_PACKAGE_ROOT))] = hits
    # Assert
    assert offenders == {}
