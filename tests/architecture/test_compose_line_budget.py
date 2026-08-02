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
ceiling.

This is a standing invariant, not a one-time snapshot: it runs against `compose.py`'s
*current* contents on every suite run, so it also constrains every later Phase-11 story
(STORY-076, STORY-080, STORY-083) that touches `compose.py` after this one.
"""

from pathlib import Path

_MIN_LINES = 50
_MAX_LINES = 500


def test_compose_py_within_50_to_500_lines() -> None:
    """Proves: STORY-077-AC-5

    Given the current, committed `compose.py`, when its source lines are counted, then
    the count falls within the owner-approved 50-500 composition-root budget (widened
    from 50-200, then from 50-400 -- see the module docstring).
    """
    # Arrange
    compose_path = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench" / "compose.py"

    # Act
    line_count = len(compose_path.read_text(encoding="utf-8").splitlines())

    # Assert
    assert _MIN_LINES <= line_count <= _MAX_LINES
