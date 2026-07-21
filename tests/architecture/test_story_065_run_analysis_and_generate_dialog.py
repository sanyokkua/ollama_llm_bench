"""Architecture tests scoped to STORY-065's own new files (Definition of done).

Asserts: no ``setStyleSheet`` call, no colour literal, no ``asyncio``/``anyio``/
``qasync`` import anywhere in the Run Analysis tab package or the Generate
Analysis dialog; the tab's sub-controller depends only on ``ResultGateway``
(via ``ui.results.protocols``), the ``EventBus``, and ``Clipboard``; the dialog
depends only on ``RunAnalysisDispatcher``, ``ProviderListSource``,
``ModelFetcher``, and the ``EventBus``. Mirrors
``test_story_057_resume_retry_dialogs.py``'s per-story scoped-file pattern.
"""

import ast
import inspect
from pathlib import Path
import re

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_RUN_ANALYSIS_TAB_ROOT = _PACKAGE_ROOT / "ui" / "results" / "_internal" / "run_analysis_tab"
_RUN_ANALYSIS_CONTROLLER_FILE = _RUN_ANALYSIS_TAB_ROOT / "controller.py"
_GENERATE_ANALYSIS_VIEW_FILE = (
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "generate_analysis_view.py"
)
_GENERATE_ANALYSIS_SELECT_FILE = (
    _PACKAGE_ROOT / "ui" / "common_dialogs" / "_internal" / "generate_analysis_select.py"
)
_SCAN_FILES = (
    *sorted(_RUN_ANALYSIS_TAB_ROOT.rglob("*.py")),
    _GENERATE_ANALYSIS_VIEW_FILE,
    _GENERATE_ANALYSIS_SELECT_FILE,
)

_FORBIDDEN_CONCURRENCY_ROOTS = ("asyncio", "anyio", "qasync")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_CONTROLLER_ALLOWED_IMPORTS = {
    "ollama_llm_bench.adapters.clipboard",
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    "ollama_llm_bench.ui.results._internal.run_analysis_tab",
    "ollama_llm_bench.ui.results._internal.run_analysis_tab.select",
    "ollama_llm_bench.ui.results._internal.run_analysis_tab.view",
    "ollama_llm_bench.ui.results.models",
    "ollama_llm_bench.ui.results.protocols",
}

_DIALOG_ALLOWED_IMPORTS = {
    "ollama_llm_bench.backend.domain",
    "ollama_llm_bench.backend.events",
    # Pure, Qt-free model-name classification -- the same established precedent
    # ``ui.new_benchmark``'s judge/test-models sections already rely on; not a
    # backend Store/Service Protocol.
    "ollama_llm_bench.backend.model_helpers",
    "ollama_llm_bench.ui.common_dialogs._internal.generate_analysis_select",
    "ollama_llm_bench.ui.common_dialogs.models",
    "ollama_llm_bench.ui.shared.model_dropdown",
    "ollama_llm_bench.ui.shared.provider_dropdown",
}


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
    assert len(_SCAN_FILES) > 0


def test_no_setstylesheet_or_forbidden_concurrency_import() -> None:
    """Proves: STORY-065 Definition of done

    No STORY-065 file calls ``setStyleSheet`` or imports
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


def test_story_065_files_embed_no_colour_literal() -> None:
    """Proves: STORY-065 Definition of done

    No STORY-065 file embeds a literal colour value; colours are resolved
    from ``ui/theme``'s role accessors only (08-D §2, §16).
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


def test_run_analysis_tab_controller_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-065 Definition of done

    ``run_analysis_tab/controller.py`` depends only on ``ResultGateway`` (via
    ``ui.results.protocols``), the ``EventBus``, and ``Clipboard`` -- it holds
    no ``RunAnalysisService`` directly (D-R-06).
    """
    # Arrange
    tree = ast.parse(
        _RUN_ANALYSIS_CONTROLLER_FILE.read_text(encoding="utf-8"),
        filename=str(_RUN_ANALYSIS_CONTROLLER_FILE),
    )
    imported_modules = _imported_modules(tree)
    # Act
    first_party_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.")}
    disallowed = first_party_imports - _CONTROLLER_ALLOWED_IMPORTS
    # Assert
    assert disallowed == set()


def test_generate_analysis_dialog_depends_only_on_declared_collaborators() -> None:
    """Proves: STORY-065 Definition of done

    ``common_dialogs/_internal/generate_analysis_view.py`` depends only on the
    locally-declared ``RunAnalysisDispatcher`` (via ``ui.common_dialogs.models``'s
    ``GenerateAnalysisCollaborators`` bundle), the shared ``ProviderListSource``/
    ``ModelFetcher`` dropdown Protocols, and the ``EventBus`` -- it holds no
    ``ResultGateway`` and never imports a backend Store/Service Protocol
    directly (D-R-06).
    """
    # Arrange
    tree = ast.parse(
        _GENERATE_ANALYSIS_VIEW_FILE.read_text(encoding="utf-8"),
        filename=str(_GENERATE_ANALYSIS_VIEW_FILE),
    )
    imported_modules = _imported_modules(tree)
    # Act
    first_party_imports = {m for m in imported_modules if m.startswith("ollama_llm_bench.")}
    disallowed = first_party_imports - _DIALOG_ALLOWED_IMPORTS
    # Assert
    assert disallowed == set()
