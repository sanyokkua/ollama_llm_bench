"""The Task Editor edge-case catalog is registered with the traceability library (STORY-116-AC-1).

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md``
Section 19 (the group/owner index of scopes and their owning catalogs) and
``docs/v3_specification/09_Task_Editor/description.md`` Section 9 (the catalog itself).

`scripts/` is not on pytest's `pythonpath` (which is `["src"]`), so it is *appended* here --
never prepended, because `scripts/trace.py` shadows the standard library's `trace` module and a
prepended path would leak that shadow into every other test in the session. `_traceability_lib`
has no such clash and imports by name once the directory is reachable.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TASK_EDITOR_CATALOG = REPO_ROOT / "docs" / "v3_specification" / "09_Task_Editor" / "description.md"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

_lib = importlib.import_module("_traceability_lib")

_EXPECTED_ID_COUNT = 15

# Deliberately not the library's own pattern: parsing Section 9 independently is what stops this
# test passing by hard-coding the same fifteen identifiers on both sides of the assertion.
_SECTION_9_ROW_RE = re.compile(r"^\|\s*(EC-TE-\d+)\s*\|")


def _ids_defined_in_section_9() -> set[str]:
    """Every `EC-TE-` identifier defined by the Section 9 table, read straight from the catalog."""
    lines = TASK_EDITOR_CATALOG.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 9. Edge cases"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))

    ids: set[str] = set()
    for line in lines[start:end]:
        match = _SECTION_9_ROW_RE.match(line)
        if match is not None:
            ids.add(match.group(1))
    return ids


def test_task_editor_catalog_contributes_its_fifteen_ids() -> None:
    """Proves: STORY-116-AC-1

    Scanning the registered edge-case catalogs yields exactly the fifteen `EC-TE-` identifiers
    Section 9 defines -- no more and no fewer. The expected set is parsed from the catalog
    document rather than written out here, so the two sides cannot drift into agreement.
    """
    defined_in_catalog = _ids_defined_in_section_9()
    assert len(defined_in_catalog) == _EXPECTED_ID_COUNT, (
        f"Section 9 should define {_EXPECTED_ID_COUNT} identifiers, found {len(defined_in_catalog)}"
    )

    scanned = _lib.load_all_catalog_ids()
    task_editor_ids = {ec_id for ec_id in scanned if ec_id.startswith("EC-TE-")}

    assert task_editor_ids == defined_in_catalog

    # The catalog must contribute *only* its own scope: a stray row elsewhere in the document
    # would silently enlarge the gate's enumeration.
    assert _lib.scan_catalog_ids(TASK_EDITOR_CATALOG) == defined_in_catalog
