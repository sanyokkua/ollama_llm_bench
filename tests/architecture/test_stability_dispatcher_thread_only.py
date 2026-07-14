"""Architecture test: `AdaptiveTimeoutService`/`ProviderCircuitBreaker` are touched only
on the dispatcher thread, never inside a worker-submitted attempt callable (STORY-030).

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`
§6.6 (the before-submit breaker/adaptive-timeout consultation is dispatcher-thread-only)
and `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` ("do not add locking to them;
instead, make sure any new call site that touches them is on the dispatcher thread").

Two complementary checks: (1) `_internal/units.py`'s attempt-builder functions
(`build_inference_attempt`, `build_judge_attempt`) never import either stability
service — a worker-submitted attempt callable has no way to reach them; (2) every
stability-service method call anywhere under `backend/benchmark_pipeline/` (excluding
tests) resolves to a source line inside `_internal/stability_dispatch.py` or
`_internal/stability_phase.py` — both dispatcher-thread-only modules, invoked between
row submissions in `run_phase_with_stability`, never from inside a unit passed to
`TaskRunner.submit()`.
"""

import ast
import inspect
from pathlib import Path

from ollama_llm_bench.backend import benchmark_pipeline

_BENCHMARK_PIPELINE_PACKAGE_ROOT = Path(inspect.getfile(benchmark_pipeline)).parent

_STABILITY_SERVICE_METHOD_NAMES = frozenset(
    {
        "next_budget",
        "record_success",
        "record_timeout",
        "is_excluded",
        "model_state",
        "should_skip",
        "record_failure",
        "cooldown_remaining_seconds",
    }
)
"""Every method name on either `AdaptiveTimeoutService` or `ProviderCircuitBreaker`.

`state` is deliberately excluded: it collides with unrelated attribute names
elsewhere in this module tree (e.g. a plain `.state` field), which would make the
walker over-broad; `ProviderCircuitBreaker.state(...)` calls are still covered
because every one of this module's actual call sites also calls at least one of the
other breaker/service methods above in the same function.
"""

_DISPATCHER_THREAD_ONLY_FILE_NAMES = frozenset({"stability_dispatch.py", "stability_phase.py"})


def _iter_source_files() -> list[Path]:
    return sorted(
        path
        for path in _BENCHMARK_PIPELINE_PACKAGE_ROOT.rglob("*.py")
        if "tests" not in path.relative_to(_BENCHMARK_PIPELINE_PACKAGE_ROOT).parts
    )


def test_units_module_never_imports_either_stability_service() -> None:
    """Proves: STORY-030 architecture constraint

    `_internal/units.py`'s attempt-builder functions (`build_inference_attempt`,
    `build_judge_attempt`) must never import or receive `AdaptiveTimeoutService`/
    `ProviderCircuitBreaker` — those services are consulted only in
    `stability_dispatch.py`/`stability_phase.py`, which run on the dispatcher
    thread; a worker-submitted attempt callable must have no way to reach either
    service.
    """
    # Arrange
    units_file = _BENCHMARK_PIPELINE_PACKAGE_ROOT / "_internal" / "units.py"
    tree = ast.parse(units_file.read_text(encoding="utf-8"), filename=str(units_file))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    # Assert
    assert "AdaptiveTimeoutService" not in imported_names
    assert "ProviderCircuitBreaker" not in imported_names


def test_stability_service_methods_called_only_from_dispatcher_thread_modules() -> None:
    """Proves: STORY-030 architecture constraint

    Every call to a `next_budget`/`record_success`/`record_timeout`/`is_excluded`/
    `model_state`/`should_skip`/`record_failure`/`cooldown_remaining_seconds` method,
    anywhere under `backend/benchmark_pipeline/` (excluding colocated tests), resolves
    to a source line inside `_internal/stability_dispatch.py` or
    `_internal/stability_phase.py` — both dispatcher-thread-only modules. Every other
    module (in particular the worker-submitted attempt builders in `_internal/units.py`)
    contains no such call.
    """
    # Arrange
    offending_calls: list[tuple[str, str]] = []
    for source_file in _iter_source_files():
        if source_file.name in _DISPATCHER_THREAD_ONLY_FILE_NAMES:
            continue
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _STABILITY_SERVICE_METHOD_NAMES:
                offending_calls.append((source_file.name, node.attr))

    # Assert
    assert offending_calls == []
