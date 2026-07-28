"""Architecture test: ``backend/benchmark_pipeline/`` imports no Qt, no ``asyncio``, no
concrete provider adapter, and blocks on ``Future.result()`` only from the dispatcher
(STORY-029).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§11 (concurrency stack: stdlib + Qt only — no ``asyncio``, no ``anyio``); the generic
"Backend layer is Qt-free" import-linter contract in ``pyproject.toml`` already forbids
``PySide6`` for every ``backend/*`` package including ``backend.benchmark_pipeline`` — this
test adds an explicit, module-scoped AST check plus the ``asyncio``/``async def`` prohibition
that import-linter alone cannot express, mirroring
``tests/architecture/test_concurrency_module.py`` (STORY-006),
``tests/architecture/test_settings_module.py`` (STORY-014), and
``tests/architecture/test_provider_registry_module.py`` (STORY-017). It additionally checks
that no concrete provider-adapter package is imported — the pipeline routes to providers only
through the ``LLMClient``/``TaskRunner`` Protocols wired by ``compose.py`` — and that
``Future.result()`` is called only from ``_internal/dispatcher.py``, the sole sanctioned
block-on-futures orchestrator per this story's DD-38/DD-40 constraint
(docs/stories/story-029-benchmark-pipeline-batching-and-lifecycle.md, "Design constraints").
"""

import ast
import inspect
from pathlib import Path

import pytest

from ollama_llm_bench.backend import benchmark_pipeline

_BENCHMARK_PIPELINE_PACKAGE_ROOT = Path(inspect.getfile(benchmark_pipeline)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")
_FORBIDDEN_CONCRETE_ADAPTER_MODULES = (
    "ollama_llm_bench.backend.provider_openai_compatible",
    "ollama_llm_bench.backend.provider_anthropic",
    "ollama_llm_bench.backend.provider_gemini",
)
_DISPATCHER_FILE_NAME = "dispatcher.py"
_STABILITY_DISPATCH_FILE_NAME = "stability_dispatch.py"
"""STORY-030: the stability-stack retry orchestrator also runs on the dispatcher
thread — its per-attempt `Future.result()` call is the same "dispatcher blocks,
worker never does" pattern as `dispatcher.py` itself, just factored into its own
module (see `_internal/stability_dispatch.py`'s module docstring)."""
_LIGHTWEIGHT_CALL_FILE_NAME = "lightweight_call.py"
"""STORY-100: the shared call shape behind both `warmup.py` and
`_internal/provider_probe.py` runs on the dispatcher thread (only its single
worker-submitted `chat` unit crosses onto a pool worker) and blocks on that
unit's `Future.result()` — the same sanctioned pattern as `dispatcher.py`,
`stability_dispatch.py`, and the (now-delegating) `warmup.py`."""


def _iter_source_files() -> list[Path]:
    return sorted(_BENCHMARK_PIPELINE_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_BENCHMARK_PIPELINE_PACKAGE_ROOT)) for path in files]
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
    """Proves: STORY-029-AC-1

    Sanity guard for the AST walker itself: ``backend/benchmark_pipeline/``
    has at least one discoverable ``.py`` source file, so the parametrized
    checks below are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_benchmark_pipeline_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-029-AC-1

    Every source file under ``backend/benchmark_pipeline/`` (including its
    colocated tests) imports no ``PySide6``, no ``asyncio``, no ``anyio``, and
    no ``qasync`` — the benchmark pipeline stays Qt-free and asyncio-free
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
def test_benchmark_pipeline_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-029-AC-1

    Every source file under ``backend/benchmark_pipeline/`` defines no
    ``async def`` function (DD-43) — the module is ordinary synchronous,
    blocking Python with no event-loop or coroutine scheduling of any kind.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_benchmark_pipeline_module_imports_no_concrete_provider_adapter(
    source_file: Path,
) -> None:
    """Proves: STORY-029-AC-1

    Every source file under ``backend/benchmark_pipeline/`` imports no
    concrete provider-adapter package
    (``backend.provider_openai_compatible``/``provider_anthropic``/
    ``provider_gemini``) — the pipeline routes to providers only through the
    ``LLMClient`` Protocol wired by ``compose.py`` from the concrete adapter
    factories, never by importing a concrete adapter itself
    (`01_MODULE_INVENTORY.md` §4.4).
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


def test_only_dispatcher_module_calls_future_result() -> None:
    """Proves: STORY-029-AC-2

    Every source file under ``backend/benchmark_pipeline/`` other than
    ``_internal/dispatcher.py`` and ``_internal/stability_dispatch.py``
    contains no attribute access named ``result`` — ``Future.result()`` (the
    block-on-a-unit's-outcome call) is invoked only from the dedicated
    dispatcher thread's own modules, per this story's DD-38/DD-40 "dispatcher
    thread is the only sanctioned block-on-futures orchestrator" constraint
    (STORY-030 extends this to the stability-stack retry orchestrator, which
    also runs on the dispatcher thread — see ``_internal/stability_dispatch.py``;
    STORY-100 extends it to the shared warmup/probe call shape in
    ``_internal/lightweight_call.py``, likewise dispatcher-thread-only —
    ``_internal/warmup.py`` itself no longer contains a ``Future.result()``
    call since that STORY-100 extraction, so it is deliberately *not*
    allowlisted here: a ``.result()`` call reappearing in ``warmup.py`` would
    be a real regression this test should catch, not a false positive to
    exempt away).
    """
    # Arrange
    other_source_files = [
        source_file
        for source_file in _SOURCE_FILES
        if source_file.name
        not in (
            _DISPATCHER_FILE_NAME,
            _STABILITY_DISPATCH_FILE_NAME,
            _LIGHTWEIGHT_CALL_FILE_NAME,
        )
    ]

    # Act
    offending_files = [
        source_file
        for source_file in other_source_files
        if any(
            isinstance(node, ast.Attribute) and node.attr == "result"
            for node in ast.walk(
                ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
            )
        )
    ]

    # Assert
    assert offending_files == []
