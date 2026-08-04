"""Unit test for `_compose_shims.py`'s `_NoActiveRunTaskPaths` stub (STORY-077-AC-11).

Cross-module: the stub under test lives in `_compose_shims.py`, a private sibling module
of `compose.py` (the composition root) housing its non-wiring shim/stub classes -- both are
explicitly exempted from the usual `_internal/` privacy boundary for testing purposes -- see
`tests/unit/test_export_filename_bridge.py`'s module docstring for the same reasoning.

Given/When/Then (Pattern A): the stub's implementation unconditionally ignores its
argument and returns `()`, so a couple of representative `run_id` values is enough to
demonstrate the always-empty behaviour the story's own wording claims -- a Hypothesis
property sweep would add no additional confidence here, since the code path taken is
identical regardless of the input value.
"""

from ollama_llm_bench._compose_shims import _NoActiveRunTaskPaths


def test_stub_always_returns_empty_tuple() -> None:
    """Proves: STORY-077-AC-11

    Given the `ActiveRunTaskPaths` stub `build_app` constructs for the Task Editor
    gateway, when `task_paths_for(run_id=...)` is called with any `run_id`, then it
    always returns an empty tuple, and the stub's docstring documents this as a
    deliberate, currently-unimplemented placeholder ("no tracker exists yet"; note:
    the docstring does not use the literal words "placeholder"/"future" the story's
    own AC-11 wording uses -- see this story's test-writing report).
    """
    # Arrange
    stub = _NoActiveRunTaskPaths()

    # Act
    first = stub.task_paths_for(1)
    second = stub.task_paths_for(999_999)
    third = stub.task_paths_for(0)

    # Assert
    assert first == ()
    assert second == ()
    assert third == ()
    docstring = (_NoActiveRunTaskPaths.__doc__ or "").lower()
    assert "stub" in docstring
    assert "no tracker exists yet" in docstring
