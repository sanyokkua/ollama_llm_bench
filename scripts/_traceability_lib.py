"""Shared parsing/scanning helpers for scripts/trace.py and scripts/validate_traceability.py.

Not a package public surface -- an internal helper module for the two traceability scripts
only. See docs/v3_specification/14_Process_and_Traceability/03_TRACEABILITY.md for the format
this module implements, and 02_STORY_FORMAT.md for the story front-matter schema it parses.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import sys

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

REPO_ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = REPO_ROOT / "docs" / "stories"
SPEC_ROOT = REPO_ROOT / "docs" / "v3_specification"
MODULE_INVENTORY_PATH = SPEC_ROOT / "14_Process_and_Traceability" / "01_MODULE_INVENTORY.md"
TRACEABILITY_PATH = REPO_ROOT / "traceability.yaml"

# Edge-case catalog documents -- the source of truth for every EC-<SCOPE>-<n>[a-f] identifier.
# See 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md Section 19 / 19.1.
EDGE_CASE_CATALOGS = [
    SPEC_ROOT / "08_Cross_Cutting" / "08-I_edge_cases.md",
    SPEC_ROOT / "08_Cross_Cutting" / "08-M_app_lifecycle.md",
    SPEC_ROOT / "10_Domain_and_Data" / "06_IMPORT_FORMATS.md",
    SPEC_ROOT / "10_Domain_and_Data" / "05_EXPORT_FORMATS.md",
    SPEC_ROOT / "10_Domain_and_Data" / "07_FILE_LAYOUT.md",
    SPEC_ROOT / "10_Domain_and_Data" / "08_REDACTION_PATTERNS.md",
]
EDGE_CASE_MAPPING_PATH = (
    SPEC_ROOT / "14_Process_and_Traceability" / "06_EDGE_CASE_TO_TEST_MAPPING.md"
)

_FRONT_MATTER_PART_COUNT = 3
_NODE_ID_FUNCTION_ONLY_SEGMENTS = 1
_NODE_ID_CLASS_AND_FUNCTION_SEGMENTS = 2

STORY_ID_RE = re.compile(r"^STORY-\d{3}$")
AC_ID_RE = re.compile(r"^STORY-(\d{3})-AC-(\d+)$")
EC_ID_RE = re.compile(r"^EC-[A-Z]+-\d+[a-f]?$")
ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
STATUS_VALUES = {"draft", "ready", "in-progress", "done", "superseded"}
OWNER_VALUES = {"arch", "coder", "tester"}
ESTIMATE_VALUES = {"S", "M", "L"}
REQUIRED_STORY_FIELDS = {
    "id",
    "title",
    "status",
    "spec_clauses",
    "modules",
    "acceptance_criteria",
    "owner",
    "estimate",
}
OPTIONAL_STORY_FIELDS = {"edge_cases", "depends_on", "adrs"}
ALLOWED_STORY_FIELDS = REQUIRED_STORY_FIELDS | OPTIONAL_STORY_FIELDS

PROVES_RE = re.compile(r"^\s*Proves:\s*(STORY-\d{3}-AC-\d+)\s*$")


@dataclass(frozen=True)
class StoryError:
    """One front-matter validation failure attributed to a story file."""

    story_path: Path
    message: str


@dataclass(frozen=True)
class Story:
    """A parsed, schema-valid story front-matter record."""

    id: str
    title: str
    status: str
    spec_clauses: tuple[str, ...]
    modules: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    edge_cases: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    adrs: tuple[str, ...] = ()
    owner: str = ""
    estimate: str = ""
    source_path: Path = field(default=Path())


def _yaml() -> YAML:
    return YAML(typ="safe")


def split_front_matter(text: str) -> str | None:
    """Return the YAML front-matter block of a story file, or None if not delimited by `---`."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < _FRONT_MATTER_PART_COUNT:
        return None
    return parts[1]


def load_story_files() -> list[Path]:
    """Every story Markdown file under docs/stories/, sorted for determinism."""
    if not STORIES_DIR.is_dir():
        return []
    return sorted(p for p in STORIES_DIR.glob("*.md") if p.is_file())


def _as_str_list(value: object, field_name: str, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors.append(f"'{field_name}' must be a list of strings")
        return ()
    return tuple(value)


def _validate_id(data: dict[str, object], errors: list[str]) -> str | None:
    story_id = data.get("id")
    if not isinstance(story_id, str) or not STORY_ID_RE.match(story_id):
        errors.append(f"'id' must match STORY-\\d{{3}}, got {story_id!r}")
        return None
    return story_id


def _validate_title(data: dict[str, object], errors: list[str]) -> str | None:
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("'title' must be a non-empty string")
        return None
    if title.endswith("."):
        errors.append("'title' must not end with a trailing period")
    return title


def _validate_status(data: dict[str, object], errors: list[str]) -> str | None:
    status = data.get("status")
    if not isinstance(status, str) or status not in STATUS_VALUES:
        errors.append(f"'status' must be one of {sorted(STATUS_VALUES)}, got {status!r}")
        return None
    return status


def _validate_non_empty_list(
    data: dict[str, object], field_name: str, errors: list[str]
) -> tuple[str, ...]:
    values = _as_str_list(data.get(field_name), field_name, errors)
    if data.get(field_name) == []:
        errors.append(f"'{field_name}' must have at least one entry")
    return values


def _validate_acceptance_criteria(
    data: dict[str, object], story_id: str | None, errors: list[str]
) -> tuple[str, ...]:
    acceptance_criteria = _validate_non_empty_list(data, "acceptance_criteria", errors)
    for ac_id in acceptance_criteria:
        match = AC_ID_RE.match(ac_id)
        if match is None:
            errors.append(f"acceptance criterion id {ac_id!r} must match STORY-NNN-AC-N")
        elif story_id is not None and match.group(1) != story_id.removeprefix("STORY-"):
            errors.append(f"acceptance criterion id {ac_id!r} does not belong to {story_id}")
    return acceptance_criteria


def _validate_edge_cases(data: dict[str, object], errors: list[str]) -> tuple[str, ...]:
    edge_cases = _as_str_list(data.get("edge_cases"), "edge_cases", errors)
    for ec_id in edge_cases:
        if not EC_ID_RE.match(ec_id):
            errors.append(f"edge case id {ec_id!r} does not match EC-[A-Z]+-\\d+[a-f]?")
    return edge_cases


def _validate_depends_on(data: dict[str, object], errors: list[str]) -> tuple[str, ...]:
    depends_on = _as_str_list(data.get("depends_on"), "depends_on", errors)
    for dep_id in depends_on:
        if not STORY_ID_RE.match(dep_id):
            errors.append(f"'depends_on' entry {dep_id!r} must match STORY-\\d{{3}}")
    return depends_on


def _validate_adrs(data: dict[str, object], errors: list[str]) -> tuple[str, ...]:
    adrs = _as_str_list(data.get("adrs"), "adrs", errors)
    for adr_id in adrs:
        if not ADR_ID_RE.match(adr_id):
            errors.append(f"'adrs' entry {adr_id!r} must match ADR-\\d{{4}}")
    return adrs


def _validate_owner(data: dict[str, object], errors: list[str]) -> str:
    owner = data.get("owner")
    if not isinstance(owner, str) or owner not in OWNER_VALUES:
        errors.append(f"'owner' must be one of {sorted(OWNER_VALUES)}, got {owner!r}")
        return ""
    return owner


def _validate_estimate(data: dict[str, object], errors: list[str]) -> str:
    estimate = data.get("estimate")
    if not isinstance(estimate, str) or estimate not in ESTIMATE_VALUES:
        errors.append(f"'estimate' must be one of {sorted(ESTIMATE_VALUES)}, got {estimate!r}")
        return ""
    return estimate


def _parse_front_matter_yaml(text: str) -> tuple[dict[str, object] | None, str | None]:
    raw_block = split_front_matter(text)
    if raw_block is None:
        return None, "missing '---' delimited YAML front-matter block"
    try:
        data = _yaml().load(raw_block)
    except YAMLError as exc:
        return None, f"front-matter is not valid YAML: {exc}"
    if not isinstance(data, dict):
        return None, "front-matter must be a YAML mapping"
    return data, None


def parse_story_front_matter(path: Path) -> tuple[Story | None, list[StoryError]]:
    """Parse and schema-validate one story file's YAML front-matter.

    Returns (Story, []) on success, or (None, [StoryError, ...]) on any schema violation.
    Mirrors 02_STORY_FORMAT.md Section 5's field rules.
    """
    text = path.read_text(encoding="utf-8")
    data, top_level_error = _parse_front_matter_yaml(text)
    if data is None:
        assert top_level_error is not None  # noqa: S101  # narrowed by _parse_front_matter_yaml
        return None, [StoryError(path, top_level_error)]

    errors: list[str] = []
    unknown_fields = set(data.keys()) - ALLOWED_STORY_FIELDS
    if unknown_fields:
        errors.append(f"unknown front-matter field(s): {sorted(unknown_fields)}")
    missing_fields = REQUIRED_STORY_FIELDS - set(data.keys())
    if missing_fields:
        errors.append(f"missing required front-matter field(s): {sorted(missing_fields)}")

    story_id = _validate_id(data, errors)
    title = _validate_title(data, errors)
    status = _validate_status(data, errors)
    spec_clauses = _validate_non_empty_list(data, "spec_clauses", errors)
    modules = _validate_non_empty_list(data, "modules", errors)
    acceptance_criteria = _validate_acceptance_criteria(data, story_id, errors)
    edge_cases = _validate_edge_cases(data, errors)
    depends_on = _validate_depends_on(data, errors)
    adrs = _validate_adrs(data, errors)
    owner = _validate_owner(data, errors)
    estimate = _validate_estimate(data, errors)

    if errors:
        return None, [StoryError(path, message) for message in errors]

    assert story_id is not None  # noqa: S101  # narrowed above; errors would have short-circuited
    assert title is not None  # noqa: S101
    assert status is not None  # noqa: S101

    story = Story(
        id=story_id,
        title=title,
        status=status,
        spec_clauses=spec_clauses,
        modules=modules,
        acceptance_criteria=acceptance_criteria,
        edge_cases=edge_cases,
        depends_on=depends_on,
        adrs=adrs,
        owner=owner,
        estimate=estimate,
        source_path=path,
    )
    return story, []


def load_all_stories() -> tuple[list[Story], list[StoryError]]:
    """Parse every story file. Returns (valid stories, all schema errors across all files)."""
    stories: list[Story] = []
    errors: list[StoryError] = []
    for path in load_story_files():
        story, story_errors = parse_story_front_matter(path)
        if story is not None:
            stories.append(story)
        errors.extend(story_errors)
    return stories, errors


# --- Module inventory -------------------------------------------------------------------

MODULE_PATH_RE = re.compile(r"`((?:backend|adapters|ui)/[A-Za-z0-9_./]+/)`")


def load_module_inventory() -> set[str]:
    """Every module path listed in 01_MODULE_INVENTORY.md, taken from backtick-quoted cells
    matching `backend/...`, `adapters/...`, or `ui/...` in the module-path table column."""
    text = MODULE_INVENTORY_PATH.read_text(encoding="utf-8")
    return set(MODULE_PATH_RE.findall(text))


# --- Spec clause resolution --------------------------------------------------------------

_SLUG_STRIP_RE = re.compile(r"[^\w\- ]+")


def _github_slug(heading: str) -> str:
    """Approximate GitHub-Flavored-Markdown heading-to-anchor slugification."""
    text = heading.strip().lower()
    text = re.sub(r"`([^`]*)`", r"\1", text)  # strip backticks, keep inner text
    text = _SLUG_STRIP_RE.sub("", text)
    return text.replace(" ", "-")


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_TABLE_ROW_EC_RE = re.compile(r"^\|\s*(EC-[A-Z]+-\d+[a-f]?)\s*\|")


def _resolve_ec_anchor(anchor: str, text: str) -> bool:
    return anchor in text


def _resolve_heading_anchor(anchor: str, text: str) -> bool:
    return any(
        _github_slug(match.group(2)) == anchor.lower() for match in _HEADING_RE.finditer(text)
    )


def resolve_spec_clause(clause_ref: str) -> bool:
    """True if `<spec-file-path>#<anchor>` resolves to a real file and heading/row anchor
    under docs/v3_specification/, per 02_STORY_FORMAT.md Section 5 and 03_TRACEABILITY.md
    Section 5's "Clause resolves" check."""
    if "#" not in clause_ref:
        return False
    file_part, _, anchor = clause_ref.partition("#")
    if not anchor:
        return False
    spec_path = SPEC_ROOT / file_part
    if not spec_path.is_file():
        return False
    text = spec_path.read_text(encoding="utf-8")

    if EC_ID_RE.match(anchor):
        return _resolve_ec_anchor(anchor, text)
    return _resolve_heading_anchor(anchor, text)


# --- Edge-case catalog scanning ----------------------------------------------------------

_HEADING_EC_RE = re.compile(r"^#{1,6}\s+(EC-[A-Z]+-\d+[a-f]?)\b")


def scan_catalog_ids(path: Path) -> set[str]:
    """Every EC-<SCOPE>-<n>[a-f] id defined in one catalog document, via heading form
    (`### EC-RUN-1 — ...`) or leading pipe-table-row form (`| EC-IMP-1 | ... |`)."""
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        heading_match = _HEADING_EC_RE.match(line)
        if heading_match:
            ids.add(heading_match.group(1))
            continue
        row_match = _TABLE_ROW_EC_RE.match(line)
        if row_match:
            ids.add(row_match.group(1))
    return ids


def load_all_catalog_ids() -> set[str]:
    """Every EC- id defined across all catalogs in EDGE_CASE_CATALOGS."""
    ids: set[str] = set()
    for catalog_path in EDGE_CASE_CATALOGS:
        ids |= scan_catalog_ids(catalog_path)
    return ids


def load_mapped_edge_case_ids() -> set[str]:
    """Every EC- id that has a row in 06_EDGE_CASE_TO_TEST_MAPPING.md."""
    return scan_catalog_ids(EDGE_CASE_MAPPING_PATH)


# --- Test collection -----------------------------------------------------------------------


@dataclass(frozen=True)
class CollectedTest:
    node_id: str
    proves: str | None


def _iter_function_defs(
    body: list[ast.stmt],
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]


def _find_class_body(tree: ast.Module, class_name: str) -> list[ast.stmt] | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node.body
    return None


def _extract_first_docstring_line(
    source: str, function_name: str, class_name: str | None
) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    target_body = tree.body
    if class_name is not None:
        found_body = _find_class_body(tree, class_name)
        if found_body is None:
            return None
        target_body = found_body

    for func in _iter_function_defs(target_body):
        if func.name != function_name:
            continue
        docstring = ast.get_docstring(func)
        if docstring is None:
            return None
        lines = docstring.splitlines()
        return lines[0] if lines else ""
    return None


def _parse_node_id(node_id: str) -> tuple[Path, str, str | None] | None:
    """Split a pytest node id into (file path, function name, class name or None).

    Handles `path/to/test_x.py::test_fn` and `path/to/test_x.py::TestClass::test_fn`.
    Parametrized ids (`...::test_fn[param]`) have their bracket suffix stripped for docstring
    lookup, since the docstring belongs to the function, not the parametrized case.
    """
    if "::" not in node_id:
        return None
    file_part, _, rest = node_id.partition("::")
    segments = [seg.split("[", 1)[0] for seg in rest.split("::")]
    file_path = REPO_ROOT / file_part
    if len(segments) == _NODE_ID_FUNCTION_ONLY_SEGMENTS:
        return file_path, segments[0], None
    if len(segments) == _NODE_ID_CLASS_AND_FUNCTION_SEGMENTS:
        return file_path, segments[1], segments[0]
    return None


def _run_pytest_collect_only() -> subprocess.CompletedProcess[str]:
    """Collect every test, including tiers `addopts` deselects by default.

    `pyproject.toml`'s `addopts` carries `-m "not live_local"` so a bare `pytest` never
    runs ADR-0011's opt-in live tier. Traceability is a different question from selection:
    a live test still proves an acceptance criterion, and a `done` story whose AC has an
    empty `tests` list fails `validate_traceability.py`. pytest honours only the last `-m`
    it is given and treats an empty expression as "no filtering", so the trailing `-m ""`
    below overrides `addopts` and restores full discovery. Collection imports test modules;
    it contacts no server (STORY-086).
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", ""],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _proves_id_for_node(node_id: str) -> str | None:
    parsed = _parse_node_id(node_id)
    if parsed is None:
        return None
    file_path, function_name, class_name = parsed
    if not file_path.is_file():
        return None
    source = file_path.read_text(encoding="utf-8")
    first_line = _extract_first_docstring_line(source, function_name, class_name)
    if first_line is None:
        return None
    match = PROVES_RE.match(first_line)
    return match.group(1) if match else None


def collect_tests() -> tuple[list[CollectedTest], bool]:
    """Run `pytest --collect-only -q` and read each collected test's `Proves:` docstring line.

    Returns (collected tests, collection_ok). `collection_ok` is False only when pytest
    produced no usable node-id output at all (a genuine collection failure) -- a non-zero
    pytest exit code alone does not imply collection failure, since an unrelated plugin can
    crash during session teardown after collection has already succeeded and been printed.
    """
    result = _run_pytest_collect_only()
    node_ids = [
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith(" ")
    ]
    if not node_ids and result.returncode != 0:
        return [], False

    tests = [
        CollectedTest(node_id=node_id, proves=_proves_id_for_node(node_id))
        for node_id in sorted(node_ids)
    ]
    return tests, True
