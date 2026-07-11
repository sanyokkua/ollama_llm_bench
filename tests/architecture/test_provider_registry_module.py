"""Architecture test: ``backend/provider_registry/`` imports no Qt, no ``asyncio``, and no
concrete provider adapter (STORY-017).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§11 (concurrency stack: stdlib + Qt only — no ``asyncio``, no ``anyio``); the generic
"Backend layer is Qt-free" import-linter contract in ``pyproject.toml`` already forbids
``PySide6`` for every ``backend/*`` package including ``backend.provider_registry`` — this
test adds an explicit, module-scoped AST check plus the ``asyncio``/``async def`` prohibition
that import-linter alone cannot express, mirroring
``tests/architecture/test_concurrency_module.py`` (STORY-006) and
``tests/architecture/test_settings_module.py`` (STORY-014). It additionally checks that no
concrete provider-adapter package is imported — the registry routes to adapters only through
injected ``ClientBuilder`` callables wired by ``compose.py`` (docs/stories/story-017-provider-
registry-and-llm-client-protocol.md, "Design constraints").
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import provider_registry

_PROVIDER_REGISTRY_PACKAGE_ROOT = Path(inspect.getfile(provider_registry)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")
_FORBIDDEN_CONCRETE_ADAPTER_MODULES = (
    "ollama_llm_bench.backend.provider_openai_compatible",
    "ollama_llm_bench.backend.provider_anthropic",
    "ollama_llm_bench.backend.provider_gemini",
)


def _iter_source_files() -> list[Path]:
    return sorted(_PROVIDER_REGISTRY_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_PROVIDER_REGISTRY_PACKAGE_ROOT)) for path in files]
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_at_least_one_source_file_discovered() -> None:
    """Proves: STORY-017-AC-1

    Sanity guard for the AST walker itself: ``backend/provider_registry/``
    has at least one discoverable ``.py`` source file, so the parametrized
    checks below are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_provider_registry_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-017-AC-1

    Every source file under ``backend/provider_registry/`` (including its
    colocated tests) imports no ``PySide6``, no ``asyncio``, no ``anyio``, and
    no ``qasync`` — the provider registry stays Qt-free and asyncio-free
    (D-R-01).
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    # Assert
    assert imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_provider_registry_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-017-AC-1

    Every source file under ``backend/provider_registry/`` defines no
    ``async def`` function (DD-43) — the module is ordinary synchronous,
    blocking Python with no event-loop or coroutine scheduling of any kind.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_provider_registry_module_imports_no_concrete_provider_adapter(source_file: Path) -> None:
    """Proves: STORY-017-AC-1

    Every source file under ``backend/provider_registry/`` imports no
    concrete provider-adapter package
    (``backend.provider_openai_compatible``/``provider_anthropic``/
    ``provider_gemini``) — the registry routes to adapters only through
    injected ``ClientBuilder`` callables wired by ``compose.py`` from the
    concrete adapter factories, never by importing a concrete adapter
    itself. This test passes vacuously today (STORY-018/019/020 do not yet
    exist) but guards against a future regression.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_modules = _imported_module_names(tree)

    # Assert
    assert not any(
        imported.startswith(forbidden)
        for imported in imported_modules
        for forbidden in _FORBIDDEN_CONCRETE_ADAPTER_MODULES
    )
