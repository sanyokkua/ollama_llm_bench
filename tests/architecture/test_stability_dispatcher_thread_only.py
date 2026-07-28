"""Architecture test: `AdaptiveTimeoutService`/`ProviderCircuitBreaker` are touched only
on the dispatcher thread, never inside a worker-submitted attempt callable (STORY-030).

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`
§6.6 (the before-submit breaker/adaptive-timeout consultation is dispatcher-thread-only)
and `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` ("do not add locking to them;
instead, make sure any new call site that touches them is on the dispatcher thread").

Three complementary checks: (1) `_internal/units.py`'s attempt-builder functions
(`build_inference_attempt`, `build_judge_attempt`) never import either stability
service — a worker-submitted attempt callable has no way to reach them; (2) every
stability-service method call anywhere under `backend/benchmark_pipeline/` (excluding
tests) resolves to a source line inside `_internal/stability_dispatch.py`,
`_internal/stability_phase.py`, `_internal/warmup.py` (STORY-075),
`_internal/provider_probe.py`, or `_internal/lightweight_call.py` (STORY-100) — all
dispatcher-thread-only modules, invoked between row submissions in
`run_phase_with_stability`, never from inside a unit passed to `TaskRunner.submit()`.
`_internal/lightweight_call.py` is allowlisted because it calls
`AdaptiveTimeoutService.next_budget` from the same dispatcher-thread call chain
`warmup.py`'s inlined version used before STORY-100's extraction — only its single
blocking `chat` call actually crosses onto a worker. (`next_budget` itself is not a
pure read — it also materializes/updates the target's adaptive-timeout bucket; the
dispatcher-thread-only rule applies regardless of whether a stability-service call
happens to read or write.)
(3) (STORY-100 review-fix wave) check (2)'s allowlist only proves *which* modules may
call a stability-service method at all — it does not, by itself, prove that within an
allowlisted module the call happens on the correct side of the dispatcher/worker
boundary. `test_probe_touches_stability_services_only_from_dispatcher_thread` closes
that gap for the two modules STORY-100 added: it AST-walks `lightweight_call.py` and
`provider_probe.py` specifically, and asserts no stability-service method call appears
inside the lambda/callable argument passed to a `.submit(...)` call — the exact point
work crosses from the dispatcher thread onto a `TaskRunner` worker thread. Checks (2)
and (3) are deliberately complementary, not redundant: (2) would not catch a stability
call moved onto the worker side of an already-allowlisted module, and (3) alone would
not catch a brand-new module quietly gaining stability-service access outside the
allowlist.
"""

import ast
import inspect
from pathlib import Path

import pytest

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

_DISPATCHER_THREAD_ONLY_FILE_NAMES = frozenset(
    {
        "stability_dispatch.py",
        "stability_phase.py",
        "warmup.py",
        "provider_probe.py",
        "lightweight_call.py",
    }
)


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
    to a source line inside `_internal/stability_dispatch.py`,
    `_internal/stability_phase.py`, `_internal/warmup.py` (STORY-075),
    `_internal/provider_probe.py`, or `_internal/lightweight_call.py` (STORY-100) — all
    dispatcher-thread-only modules. Every other module (in particular the
    worker-submitted attempt builders in `_internal/units.py`) contains no such call.
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


_PROBE_STABILITY_METHOD_NAMES = frozenset(
    {"next_budget", "state", "record_success", "record_failure", "is_excluded"}
)
"""The stability-service method names this file's positive check (below) watches
for inside a submitted callable. Unlike `_STABILITY_SERVICE_METHOD_NAMES` above,
`state` is included here — the two files this check scans
(`lightweight_call.py`, `provider_probe.py`) have no unrelated `.state` attribute
access to collide with, so the exclusion that check needs does not apply here."""

_PROBE_MODULE_FILE_NAMES: tuple[str, ...] = ("lightweight_call.py", "provider_probe.py")


def _probe_module_paths() -> list[Path]:
    return [
        _BENCHMARK_PIPELINE_PACKAGE_ROOT / "_internal" / file_name
        for file_name in _PROBE_MODULE_FILE_NAMES
    ]


def _submitted_callables(tree: ast.Module) -> list[ast.AST]:
    """Return every first-positional-argument node passed to a `.submit(...)`
    call anywhere in `tree` — the boundary where work crosses from the
    dispatcher thread onto a `TaskRunner` worker thread."""
    return [
        node.args[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "submit"
        and node.args
    ]


def _stability_method_names_within(node: ast.AST) -> list[str]:
    """Return every stability-service method name referenced anywhere inside `node`."""
    return [
        sub.attr
        for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute) and sub.attr in _PROBE_STABILITY_METHOD_NAMES
    ]


@pytest.mark.parametrize("source_file", _probe_module_paths(), ids=_PROBE_MODULE_FILE_NAMES)
def test_probe_touches_stability_services_only_from_dispatcher_thread(source_file: Path) -> None:
    """Proves: STORY-100 architecture constraint

    Within `_internal/lightweight_call.py` and `_internal/provider_probe.py`
    (STORY-100), no stability-service method call
    (`next_budget`/`state`/`record_success`/`record_failure`/`is_excluded`)
    appears inside the lambda/callable argument passed to a `.submit(...)`
    call. `_STABILITY_SERVICE_METHOD_NAMES`'s allowlist above only proves
    these two modules are permitted to call a stability-service method at
    all; it does not, on its own, prove the call stays on the dispatcher
    side of the `TaskRunner` boundary within them — this check closes that
    gap. Verified load-bearing by temporarily moving a
    `next_budget`/`record_failure` call into `lightweight_call.py`'s
    submitted `lambda: client.chat(...)` and observing this test fail before
    reverting (see the story's Notes).
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    submitted_callables = _submitted_callables(tree)

    # Act
    offending_calls = [
        method_name
        for callable_node in submitted_callables
        for method_name in _stability_method_names_within(callable_node)
    ]

    # Assert
    assert offending_calls == []
