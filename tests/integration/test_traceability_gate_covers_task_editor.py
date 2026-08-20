"""The traceability gate now sees the Task Editor edge cases (STORY-116-AC-2, STORY-116-AC-3).

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md``
Section 19.1 (the validator's three-step algorithm and its two set differences) and
``03_TRACEABILITY.md`` Section 5 ("Validating the Record") / Section 7 (partial coverage during
construction is reported, not failed).

These call the real `check_edge_cases_covered` against the real catalogs, mapping, and story
front-matter rather than re-deriving its logic -- a reimplementation would pass even if the
validator itself regressed.

Importing it is fiddlier than it looks. `scripts/validate_traceability.py` does
`from trace import build_record` at module scope, and `scripts/trace.py` shadows the standard
library's `trace` module. Appending `scripts/` to `sys.path` is not enough: a bare `import trace`
would still resolve to the stdlib and the import would fail. So `scripts/trace.py` is loaded
explicitly and bound to the name `trace` only for the duration of the validator's import, then
the previous binding is restored -- the shadow never outlives this module's import.
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TRACEABILITY_PATH = REPO_ROOT / "traceability.yaml"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

_lib = importlib.import_module("_traceability_lib")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_validator() -> ModuleType:
    """Import `validate_traceability.py`, standing in for the `trace` name it expects."""
    trace_script = _load_module("trace_script", SCRIPTS_DIR / "trace.py")
    sentinel = object()
    previous: object = sys.modules.get("trace", sentinel)
    sys.modules["trace"] = trace_script
    try:
        return _load_module(
            "validate_traceability_script", SCRIPTS_DIR / "validate_traceability.py"
        )
    finally:
        if previous is sentinel:
            del sys.modules["trace"]
        else:
            assert isinstance(previous, ModuleType)
            sys.modules["trace"] = previous


_validator = _load_validator()

_EXPECTED_ID_COUNT = 15
_UNMAPPED_MARKER = "has no row in the mapping"
_DANGLING_MARKER = "dangling row"

# The one identifier a story claims today: STORY-114 names EC-TE-11 in its `edge_cases:`
# front-matter. Every other Task Editor identifier is catalogued and mapped but unclaimed, which
# 03_TRACEABILITY.md Section 7 treats as partial coverage rather than a failure.
_CLAIMED_IDS = frozenset({"EC-TE-11"})

_TASK_EDITOR_IDS = sorted(
    ec_id for ec_id in _lib.load_all_catalog_ids() if ec_id.startswith("EC-TE-")
)

_AC3_CASES = [
    pytest.param(
        ec_id,
        (f"{ec_id} is named by a story but has no proving test",) if ec_id in _CLAIMED_IDS else (),
        id=ec_id,
    )
    for ec_id in _TASK_EDITOR_IDS
]

# An empty parametrize list makes pytest *skip* rather than fail, so unregistering the catalog
# would make this test evaporate silently -- the exact blindness STORY-116 exists to remove.
# Failing at collection time keeps that loud.
assert len(_AC3_CASES) == _EXPECTED_ID_COUNT, (
    f"expected {_EXPECTED_ID_COUNT} Task Editor identifiers in the catalog enumeration, "
    f"found {len(_AC3_CASES)} -- is 09_Task_Editor/description.md still registered in "
    f"EDGE_CASE_CATALOGS?"
)


def _real_record() -> dict[str, object]:
    loaded = YAML(typ="safe").load(TRACEABILITY_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _stories() -> list[object]:
    stories, errors = _lib.load_all_stories()
    assert not errors, f"story front-matter must be schema-valid: {errors}"
    return stories


def test_no_task_editor_id_is_unmapped_or_dangling() -> None:
    """Proves: STORY-116-AC-2

    With the catalog registered and the mapping extended, the validator's edge-case check
    reports neither an "uncovered" failure (`catalog_ids - mapped_ids`) nor a "dangling row"
    failure (`mapped_ids - catalog_ids`) for any `EC-TE-` identifier.
    """
    # Guard against a vacuous pass: if the catalog were ever unregistered, the enumeration would
    # simply contain no EC-TE identifier and every assertion below would hold for nothing.
    assert len(_TASK_EDITOR_IDS) == _EXPECTED_ID_COUNT
    mapped = _lib.load_mapped_edge_case_ids()
    assert {ec_id for ec_id in mapped if ec_id.startswith("EC-TE-")} == set(_TASK_EDITOR_IDS)

    failures = _validator.check_edge_cases_covered(_stories(), _real_record())

    offending = [
        failure
        for failure in failures
        if "EC-TE-" in failure and (_UNMAPPED_MARKER in failure or _DANGLING_MARKER in failure)
    ]
    assert offending == []


@pytest.mark.parametrize(("ec_id", "expected_failures_when_starved"), _AC3_CASES)
def test_proving_test_is_demanded_only_for_a_claimed_id(
    ec_id: str, expected_failures_when_starved: tuple[str, ...]
) -> None:
    """Proves: STORY-116-AC-3

    As the repository stands, no Task Editor identifier fails any edge-case check. Removing an
    identifier's proving tests then shows *which* demand is real: a story-claimed identifier
    (EC-TE-11, claimed by STORY-114) fails as untested, while an unclaimed one stays silent --
    partial coverage during construction, not a gap.
    """
    stories = _stories()
    record = _real_record()

    assert [
        failure
        for failure in _validator.check_edge_cases_covered(stories, record)
        if ec_id in failure
    ] == []

    starved = copy.deepcopy(record)
    edge_cases = starved["edge_cases"]
    assert isinstance(edge_cases, dict)
    if ec_id in edge_cases:
        edge_cases[ec_id]["tests"] = []

    assert [
        failure
        for failure in _validator.check_edge_cases_covered(stories, starved)
        if ec_id in failure
    ] == list(expected_failures_when_starved)
