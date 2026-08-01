"""Architecture test: `compose.py` stays within its composition-root line budget
(STORY-077-AC-5).

Source of truth: `14_Process_and_Traceability/01_MODULE_INVENTORY.md`#7 (the composition
root is "roughly 50-200 lines of manual factory calls"), widened by the owner-approved
exception recorded in `docs/stories/story-077-composition-root-and-app-handle.md`'s Design
constraints section to 50-400 lines -- the seven real `adapters/ui_gateways/` gateway
factories STORY-104's children delivered declare 61 keyword arguments between them, which
measurably raised the floor past the original 50-200 prediction.

This is a standing invariant, not a one-time snapshot: it runs against `compose.py`'s
*current* contents on every suite run, so it also constrains every later Phase-11 story
(STORY-076, STORY-078, STORY-080, STORY-083) that touches `compose.py` after this one.
"""

from pathlib import Path

_MIN_LINES = 50
_MAX_LINES = 400


def test_compose_py_within_50_to_200_lines() -> None:
    """Proves: STORY-077-AC-5

    Given the current, committed `compose.py`, when its source lines are counted, then
    the count falls within the owner-approved 50-400 composition-root budget (widened
    from the original 50-200 -- see the module docstring).
    """
    # Arrange
    compose_path = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench" / "compose.py"

    # Act
    line_count = len(compose_path.read_text(encoding="utf-8").splitlines())

    # Assert
    assert _MIN_LINES <= line_count <= _MAX_LINES
