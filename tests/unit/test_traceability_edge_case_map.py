"""Unit tests for the traceability generator's edge-case attribution.

`scripts/trace.py` imports `_traceability_lib` as a bare top-level module, so `scripts/` has to
be importable. It is *appended* to `sys.path` rather than prepended, and `trace.py` itself is
loaded under the alias `trace_script`, because `scripts/trace.py` shadows the standard library's
`trace` module -- putting `scripts/` on the path ahead of the stdlib would leak that shadow into
every other test in the session.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_trace_script() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.append(str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("trace_script", SCRIPTS_DIR / "trace.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_trace = _load_trace_script()
_lib = importlib.import_module("_traceability_lib")


def _story(
    story_id: str,
    *,
    acceptance_criteria: tuple[str, ...],
    edge_cases: tuple[str, ...],
) -> object:
    """A minimal schema-valid `Story` carrying only the fields the edge-case map reads."""
    return _lib.Story(
        id=story_id,
        title=f"Synthetic {story_id}",
        status="done",
        spec_clauses=(),
        modules=(),
        acceptance_criteria=acceptance_criteria,
        edge_cases=edge_cases,
    )


def test_edge_case_lists_only_the_test_that_declares_it() -> None:
    """Proves: STORY-093-AC-1

    A story naming two edge cases and carrying three acceptance-criteria tests, where exactly
    one test declares `Covers:` for exactly one of the two edge cases. The declared edge case
    must list that one test alone -- not the story's other two acceptance-criteria tests.
    """
    story = _story(
        "STORY-900",
        acceptance_criteria=("STORY-900-AC-1", "STORY-900-AC-2", "STORY-900-AC-3"),
        edge_cases=("EC-SYN-1", "EC-SYN-2"),
    )
    proves_index = {
        "STORY-900-AC-1": ["tests/unit/test_syn.py::test_one"],
        "STORY-900-AC-2": ["tests/unit/test_syn.py::test_two"],
        "STORY-900-AC-3": ["tests/unit/test_syn.py::test_three"],
    }
    covers_index = {"EC-SYN-1": ["tests/unit/test_syn.py::test_two"]}

    record = _trace.build_record([story], proves_index, covers_index, generated_at="")
    edge_cases = record["edge_cases"]

    assert edge_cases["EC-SYN-1"]["tests"] == ["tests/unit/test_syn.py::test_two"]
    assert edge_cases["EC-SYN-1"]["stories"] == ["STORY-900"]


def test_edge_case_without_a_covers_declaration_keeps_the_legacy_attribution() -> None:
    """Proves: STORY-093-AC-2

    The undeclared sibling of the edge case above keeps the pre-change attribution: the union of
    every acceptance-criteria test of every story claiming it. This fallback is what makes the
    migration incremental -- no edge case that carries coverage today regresses to empty.
    """
    first = _story(
        "STORY-900",
        acceptance_criteria=("STORY-900-AC-1", "STORY-900-AC-2", "STORY-900-AC-3"),
        edge_cases=("EC-SYN-1", "EC-SYN-2"),
    )
    second = _story(
        "STORY-901",
        acceptance_criteria=("STORY-901-AC-1",),
        edge_cases=("EC-SYN-2",),
    )
    proves_index = {
        "STORY-900-AC-1": ["tests/unit/test_syn.py::test_one"],
        "STORY-900-AC-2": ["tests/unit/test_syn.py::test_two"],
        "STORY-900-AC-3": ["tests/unit/test_syn.py::test_three"],
        "STORY-901-AC-1": ["tests/unit/test_syn.py::test_four"],
    }
    covers_index = {"EC-SYN-1": ["tests/unit/test_syn.py::test_two"]}

    record = _trace.build_record([first, second], proves_index, covers_index, generated_at="")
    edge_cases = record["edge_cases"]

    assert edge_cases["EC-SYN-2"]["tests"] == [
        "tests/unit/test_syn.py::test_four",
        "tests/unit/test_syn.py::test_one",
        "tests/unit/test_syn.py::test_three",
        "tests/unit/test_syn.py::test_two",
    ]
    assert edge_cases["EC-SYN-2"]["stories"] == ["STORY-900", "STORY-901"]


def test_a_covers_declaration_for_an_unclaimed_edge_case_adds_no_key() -> None:
    """The record's edge-case key set is derived from `stories` alone, per 03_TRACEABILITY.md
    Section 3. A `Covers:` line naming an edge case no story claims changes attribution for
    nothing and must not invent a key."""
    story = _story(
        "STORY-900",
        acceptance_criteria=("STORY-900-AC-1",),
        edge_cases=("EC-SYN-1",),
    )
    proves_index = {"STORY-900-AC-1": ["tests/unit/test_syn.py::test_one"]}
    covers_index = {
        "EC-SYN-1": ["tests/unit/test_syn.py::test_one"],
        "EC-SYN-99": ["tests/unit/test_syn.py::test_one"],
    }

    record = _trace.build_record([story], proves_index, covers_index, generated_at="")

    assert sorted(record["edge_cases"]) == ["EC-SYN-1"]
