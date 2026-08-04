"""Unit test for `_compose_shims.py`'s `_NoRunValidator` stub (STORY-077-AC-12).

Cross-module: the stub under test lives in `_compose_shims.py`, a private sibling module
of `compose.py` (the composition root) housing its non-wiring shim/stub classes -- both are
explicitly exempted from the usual `_internal/` privacy boundary for testing purposes -- see
`tests/unit/test_export_filename_bridge.py`'s module docstring for the same reasoning.

Given/When/Then (Pattern A): the stub's implementation unconditionally ignores its
argument and returns `()`, so a couple of representative `RunStartRequest` values is
enough to demonstrate the always-empty behaviour -- a Hypothesis property sweep would add
no additional confidence, since the code path taken is identical regardless of the input.
"""

from ollama_llm_bench._compose_shims import _NoRunValidator
from ollama_llm_bench.backend.domain import RunMode, RunStartRequest


def _make_request(*, run_mode: RunMode = RunMode.TASKS) -> RunStartRequest:
    return RunStartRequest(run_mode=run_mode, test_models=())


def test_stub_always_returns_no_validation_entries() -> None:
    """Proves: STORY-077-AC-12

    Given the `RunValidator` stub `build_app` constructs for the New Benchmark
    gateway, when `validate(request=...)` is called with any `RunStartRequest`, then
    it always returns an empty tuple of validation entries, and the stub's docstring
    documents New Benchmark's field-validation messages as inert until a future
    implementation lands.
    """
    # Arrange
    stub = _NoRunValidator()

    # Act
    tasks_result = stub.validate(_make_request(run_mode=RunMode.TASKS))
    synthetic_result = stub.validate(_make_request(run_mode=RunMode.SYNTHETIC))

    # Assert
    assert tasks_result == ()
    assert synthetic_result == ()
    docstring = (_NoRunValidator.__doc__ or "").lower()
    assert "stub" in docstring
    assert "until a real backend implementation lands" in docstring
