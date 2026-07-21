"""Architecture tests scoped to STORY-066's own files (Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no
``asyncio``/``anyio``/``qasync`` import anywhere under ``ui/settings_dialog/``;
the controller and the Provider Edit sub-dialog depend only on
``SettingsGateway`` (via ``ui.settings_dialog.protocols``) plus the retained
UI-adapter Protocols and ``backend.domain``/``backend.events``/
``backend.model_helpers`` DTO-only imports -- never a raw backend Store/Service
Protocol (D-R-06); and that no literal secret value (an ``os.environ`` read)
is ever threaded into the working-copy ``ProviderConfig.api_key_raw`` field --
only the validated field-widget text reaches it. Mirrors
``test_story_065_run_analysis_and_generate_dialog.py``'s per-story scoped-file
pattern.
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "settings_dialog"
_SCAN_FILES = tuple(sorted(p for p in _MODULE_ROOT.rglob("*.py") if "__pycache__" not in p.parts))
_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"
_PROVIDERS_TAB_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "providers_tab" / "controller.py"
_PROVIDER_EDIT_VIEW_FILE = _MODULE_ROOT / "_internal" / "sub_dialogs" / "provider_edit_view.py"

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_ALLOWED_BACKEND_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    "ollama_llm_bench.backend.model_helpers",
}
_FORBIDDEN_STORE_MODULES = (
    "ollama_llm_bench.backend.persistence",
    "ollama_llm_bench.backend.provider_registry",
    "ollama_llm_bench.backend.settings",
    "ollama_llm_bench.backend.readiness",
)


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


def _contains_environ_read(node: ast.AST) -> bool:
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"get", "__getitem__"}
        and isinstance(call.func.value, ast.Attribute)
        and call.func.value.attr == "environ"
        for call in ast.walk(node)
    )


def test_at_least_one_source_file_discovered() -> None:
    assert len(_SCAN_FILES) > 0


def test_no_setstylesheet_or_forbidden_concurrency_import() -> None:
    """Proves: STORY-066 Definition of done

    No ``ui/settings_dialog/`` file calls ``setStyleSheet`` or imports
    ``asyncio``/``anyio``/``qasync``.
    """
    # Arrange / Act
    offenders: list[str] = []
    for source_file in _SCAN_FILES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        calls_setstylesheet, imports_forbidden = _imports_setstylesheet_or_forbidden_concurrency(
            tree
        )
        if calls_setstylesheet or imports_forbidden:
            offenders.append(str(source_file.relative_to(_PACKAGE_ROOT)))
    # Assert
    assert offenders == []


def test_settings_dialog_embeds_no_colour_literal() -> None:
    """Proves: STORY-066 Definition of done

    No ``ui/settings_dialog/`` file embeds a literal colour value; colours are
    resolved from ``ui/theme``'s role accessors only (08-D §2, §16).
    """
    # Arrange / Act
    offenders = [
        str(source_file.relative_to(_PACKAGE_ROOT))
        for source_file in _SCAN_FILES
        if _embeds_colour_literal(
            ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        )
    ]
    # Assert
    assert offenders == []


def test_controller_and_provider_edit_never_import_a_backend_store_module() -> None:
    """Proves: STORY-066 Definition of done

    Neither ``_internal/controller.py``, ``providers_tab/controller.py``, nor
    ``sub_dialogs/provider_edit_view.py`` imports a raw backend Store/Service
    module (persistence, provider registry, settings service, readiness
    service) -- every persistence/registry/probe interaction goes through
    ``SettingsGateway`` (D-R-06).
    """
    # Arrange / Act
    offenders: dict[str, list[str]] = {}
    for source_file in (
        _CONTROLLER_FILE,
        _PROVIDERS_TAB_CONTROLLER_FILE,
        _PROVIDER_EDIT_VIEW_FILE,
    ):
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


def test_controller_depends_only_on_allowed_backend_imports() -> None:
    """Proves: STORY-066 Definition of done

    ``_internal/controller.py`` and ``providers_tab/controller.py`` import
    only ``backend.domain``/``backend.events`` beyond their own
    ``ui.settings_dialog`` symbols -- never a wider backend surface.
    """
    # Arrange / Act
    offenders: dict[str, list[str]] = {}
    for source_file in (_CONTROLLER_FILE, _PROVIDERS_TAB_CONTROLLER_FILE):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        backend_imports = {
            m for m in _imported_modules(tree) if m.startswith("ollama_llm_bench.backend.")
        }
        disallowed = sorted(backend_imports - _ALLOWED_BACKEND_IMPORTS)
        if disallowed:
            offenders[str(source_file.relative_to(_PACKAGE_ROOT))] = disallowed
    # Assert
    assert offenders == {}


def test_no_environ_read_ever_reaches_api_key_raw() -> None:
    """Proves: STORY-066 Definition of done

    No literal secret value (an ``os.environ`` read) is ever threaded into a
    ``ProviderConfig``/``msgspec.structs.replace`` call's ``api_key_raw``
    keyword argument -- the only path into ``api_key_raw`` is the validated
    field-widget text (``self._api_key_edit.text()``), matching the D-R-18
    env-var-name-only rule.
    """
    # Arrange
    tree = ast.parse(
        _PROVIDER_EDIT_VIEW_FILE.read_text(encoding="utf-8"), filename=str(_PROVIDER_EDIT_VIEW_FILE)
    )
    # Act
    offending_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "api_key_raw" and _contains_environ_read(keyword.value)
    ]
    # Assert
    assert offending_calls == []
