"""Architecture test: `compose.py` stays within its composition-root line budget
(STORY-077-AC-5).

Source of truth: `14_Process_and_Traceability/01_MODULE_INVENTORY.md`#7 (the composition
root is "roughly 50-200 lines of manual factory calls"), widened by the owner-approved
exception recorded in `docs/stories/story-077-composition-root-and-app-handle.md`'s Design
constraints section to 50-400 lines -- the seven real `adapters/ui_gateways/` gateway
factories STORY-104's children delivered declare 61 keyword arguments between them, which
measurably raised the floor past the original 50-200 prediction. Widened a second time,
by owner-approved exception, to 50-500 lines for STORY-078: its launch-glue prelude adds
four abort-with-modal paths (app-data-directory creation, the single-instance lock,
opening the write connection, the schema check), each needing its own `try`/`except` and
`_abort_launch(...)` call -- already condensed to one `# fmt: skip` line each, the same
technique the first widening's docstring describes, and still 80 lines past the 400
ceiling. Widened a third time, by owner-approved exception, to 50-520 lines for
STORY-080: `AppHandle` grows a `flow: QtBenchmarkFlow` field and its `shutdown()` method
grows from 2 lines (steps 3-4 only) to the full 5-step ordered shutdown, plus the one
`res.recover_in_flight_results()` launch-time sweep call -- landing at 508 lines against
the prior 500 ceiling, with `compose.py` already at its prior widening's own ceiling
(499/500) before this story touched it, per `docs/stories/story-078-...md`'s own session
record; there was no further import-collapsing headroom left to absorb this story's
minimal, spec-mandated addition.

**Lowered for the first time, to 50-450 lines, by a targeted extraction (not a fourth
widening).** At 519/520 lines, `compose.py` measured out to header+imports (179 lines),
`AppHandle` (24 lines), ten private shim/stub classes and helpers that are not wiring at
all (101 lines), `_abort_launch`/`_quit_nested_event_loop` (33 lines), `_resolve_app_version`
(6 lines) -- and `build_app`, the actual composition-root wiring, at 177 lines: already
inside the spec's original 50-200 figure. The ten shims (`_sanitise_run_name`,
`_ExportFilenameBridge`, `_EmbeddingSelection`, `_ReadinessEmbeddingSelector`,
`_NullEmbeddingClient`, `_NoActiveRunTaskPaths`, `_NoRunValidator`,
`_NoOpManualProviderProbeCommand`, `_AlwaysOkRunLogWriteStatus`, `_NoModelFetcher`) moved
verbatim (docstrings and comments intact) to the private sibling module
`ollama_llm_bench._compose_shims`, together with the imports only they needed; `build_app`
itself was not touched. That brought `compose.py` to 405 lines, so 450 restores roughly the
same proportion of headroom the 50-400 budget originally gave the 177-line `build_app` --
room to grow without inviting a fourth widening at the first opportunity.

This is a standing invariant, not a one-time snapshot: it runs against `compose.py`'s
*current* contents on every suite run, so it also constrains every later story that
touches `compose.py` after this one.
"""

from pathlib import Path

_MIN_LINES = 50
_MAX_LINES = 450


def test_compose_py_within_50_to_520_lines() -> None:
    """Proves: STORY-077-AC-5

    Given the current, committed `compose.py`, when its source lines are counted, then
    the count falls within the owner-approved 50-450 composition-root budget (widened
    from 50-200, then 50-400, then 50-500, then 50-520, then **lowered** to 50-450 by
    extracting non-wiring shims into `_compose_shims.py` -- see the module docstring).
    """
    # Arrange
    compose_path = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench" / "compose.py"

    # Act
    line_count = len(compose_path.read_text(encoding="utf-8").splitlines())

    # Assert
    assert _MIN_LINES <= line_count <= _MAX_LINES
