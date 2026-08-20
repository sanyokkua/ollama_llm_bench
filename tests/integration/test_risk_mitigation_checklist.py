"""The risk-mitigation checklist is complete and evidence-backed (STORY-093-AC-3).

Source of truth: ``docs/v3_specification/15_Risks_and_Open_Questions/01_RISK_REGISTER.md`` §3
(the sixteen-row risk summary matrix).

This asserts the checklist's *shape*, which is what makes it auditable: one row per registered
risk, and no row standing on prose alone. It cannot assert that a cited artifact proves what the
row claims -- that is the reviewer's job -- but it does fail the moment a row is dropped, added,
or quietly downgraded to a narrative sentence.
"""

from pathlib import Path
import re

CHECKLIST_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "development" / ("risk_mitigation_checklist.md")
)

EXPECTED_RISK_IDS = tuple(f"R-{n:03d}" for n in range(1, 17))

_ROW_RE = re.compile(r"^\|\s*(R-\d{3})\s*\|(.*)\|\s*$")

# The three admissible forms of evidence, per STORY-093-AC-3.
_FILE_LINE_RE = re.compile(r"[\w./-]+\.(?:py|yml|yaml|toml|md|cfg|json):\d+")
_TEST_FUNCTION_RE = re.compile(r"\btest_[A-Za-z0-9_]+\b")
_WAIVER_MARKER_RE = re.compile(r"\*\*(?:WAIVED|RETIRED)\*\*")

_EVIDENCE_COLUMN_INDEX = -1
_VERDICT_COLUMN_INDEX = -2
_ADMISSIBLE_VERDICTS = frozenset({"`verified`", "`waived`", "`retired`"})


def _checklist_rows() -> dict[str, list[str]]:
    """Every `| R-0nn |` row of the checklist table, keyed by risk id, split into cells.

    Rows are matched by their leading risk id rather than by table position, so the section
    sub-tables further down the document cannot be mistaken for checklist rows.
    """
    rows: dict[str, list[str]] = {}
    for line in CHECKLIST_PATH.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line)
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group(2).split("|")]
        rows[match.group(1)] = cells
    return rows


def test_every_risk_row_names_a_concrete_artifact_or_a_waiver() -> None:
    """Proves: STORY-093-AC-3

    Every risk R-001 through R-016 has exactly one checklist row, and every row's evidence cell
    names a `file:LINE` reference, a `test_*` function, or carries an explicit waiver marker.
    No row is verified by prose alone. R-001 is recorded as retired.
    """
    rows = _checklist_rows()

    assert tuple(sorted(rows)) == EXPECTED_RISK_IDS, (
        "the checklist must carry exactly one row per registered risk R-001..R-016"
    )

    prose_only: list[str] = []
    for risk_id, cells in sorted(rows.items()):
        verdict = cells[_VERDICT_COLUMN_INDEX]
        assert verdict in _ADMISSIBLE_VERDICTS, f"{risk_id}: unrecognised verdict {verdict!r}"

        evidence = cells[_EVIDENCE_COLUMN_INDEX]
        backed = (
            _FILE_LINE_RE.search(evidence) is not None
            or _TEST_FUNCTION_RE.search(evidence) is not None
            or _WAIVER_MARKER_RE.search(evidence) is not None
        )
        if not backed:
            prose_only.append(f"{risk_id}: {evidence}")

    assert not prose_only, (
        "these rows are backed by prose alone -- each needs a file:LINE reference, a test_* "
        f"function name, or an explicit waiver marker: {prose_only}"
    )

    assert rows["R-001"][_VERDICT_COLUMN_INDEX] == "`retired`"
    assert "R-016" in rows["R-001"][_EVIDENCE_COLUMN_INDEX]


def test_every_waived_row_has_its_own_justification_section() -> None:
    """A waiver is a disclosure, not a checkbox: each `waived` row must be backed by a `##`
    section in the same document stating why no artifact exists and what would close it."""
    text = CHECKLIST_PATH.read_text(encoding="utf-8")
    headings = {line.split("—")[0].strip() for line in text.splitlines() if line.startswith("## ")}

    waived = [
        risk_id
        for risk_id, cells in _checklist_rows().items()
        if cells[_VERDICT_COLUMN_INDEX] in {"`waived`", "`retired`"}
    ]
    assert waived, "expected at least one waived row while the register still has open gaps"

    missing = [risk_id for risk_id in waived if f"## {risk_id}" not in headings]
    assert not missing, f"waived rows with no justification section: {sorted(missing)}"
