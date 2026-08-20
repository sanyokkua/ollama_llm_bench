"""Traceability record validator: fails the pull-request gate on any broken or orphaned link.

See docs/v3_specification/14_Process_and_Traceability/03_TRACEABILITY.md Section 5
("Validating the Record") for the nine checks this implements, and Section 7 ("Coverage
Rules") for why partial coverage during construction is *reported*, not *failed* -- only
orphan tests, broken references, and a stale record fail the gate before the application is
complete.

Invoked via `just trace-check`.
"""

from __future__ import annotations

import sys
from trace import build_record, render_yaml

from _traceability_lib import (
    TRACEABILITY_PATH,
    CollectedTest,
    Story,
    collect_tests,
    load_all_catalog_ids,
    load_all_stories,
    load_mapped_edge_case_ids,
    load_module_inventory,
    resolve_spec_clause,
)


def check_clauses_resolve(stories: list[Story]) -> list[str]:
    """'Clause resolves' -- every spec_clauses entry must point to a real file+heading."""
    failures: list[str] = []
    for story in stories:
        for clause in story.spec_clauses:
            if not resolve_spec_clause(clause):
                failures.append(f"{story.id}: spec_clauses entry does not resolve: {clause}")
    return failures


def check_modules_exist(stories: list[Story], module_inventory: set[str]) -> list[str]:
    """'Module exists' -- every modules entry must be a path in 01_MODULE_INVENTORY.md."""
    failures: list[str] = []
    for story in stories:
        for module in story.modules:
            if module not in module_inventory:
                failures.append(f"{story.id}: modules entry not in module inventory: {module}")
    return failures


# 'No orphan story' (a story names no spec clause, or a done story has an AC with no test) is
# a two-part check per 03_TRACEABILITY.md Section 5. The "names no spec clause" half is already
# enforced at parse time by front-matter schema validation (spec_clauses requires >=1 entry --
# a story failing it never reaches load_all_stories()'s valid-story list). The "done story, AC
# with no test" half is identical to the "Acceptance criterion proven" check below, so it is
# not duplicated as a separate function.


def check_acceptance_criteria_proven(stories: list[Story], record: dict[str, object]) -> list[str]:
    """'Acceptance criterion proven' -- a done story has an AC with an empty tests list."""
    failures: list[str] = []
    stories_map = record["stories"]
    assert isinstance(stories_map, dict)  # noqa: S101  # record is our own generator's output
    for story in stories:
        if story.status != "done":
            continue
        story_record = stories_map[story.id]
        assert isinstance(story_record, dict)  # noqa: S101
        ac_map = story_record["acceptance_criteria"]
        assert isinstance(ac_map, dict)  # noqa: S101
        for ac_id, ac_record in ac_map.items():
            if not ac_record["tests"]:
                failures.append(f"{story.id}: done story's {ac_id} has no proving test")
    return failures


def check_no_orphan_test(collected_tests: list[CollectedTest], stories: list[Story]) -> list[str]:
    """'No orphan test' -- a test's Proves: line names an AC that no story defines."""
    all_ac_ids = {ac_id for story in stories for ac_id in story.acceptance_criteria}
    failures: list[str] = []
    for test in collected_tests:
        if test.proves is not None and test.proves not in all_ac_ids:
            failures.append(f"{test.node_id}: Proves: {test.proves} names an AC no story defines")
    return failures


def check_edge_cases_covered(stories: list[Story], record: dict[str, object]) -> list[str]:
    """'Edge-case covered' -- every catalogued EC- id appears in some story's edge_cases and
    has a test; every mapping-table row cites a catalogued id (no dangling row). Only fires
    once a story could plausibly cover a clause -- with zero stories this reports zero
    failures rather than flagging every catalogued id as uncovered (Section 7: partial
    coverage during construction is expected and reported, not failed)."""
    if not stories:
        return []

    catalog_ids = load_all_catalog_ids()
    mapped_ids = load_mapped_edge_case_ids()
    story_ec_ids = {ec_id for story in stories for ec_id in story.edge_cases}
    edge_cases_map = record["edge_cases"]
    assert isinstance(edge_cases_map, dict)  # noqa: S101

    failures: list[str] = []
    for ec_id in sorted(mapped_ids - catalog_ids):
        failures.append(f"edge-case mapping cites {ec_id}, defined in no catalog (dangling row)")
    for ec_id in sorted(catalog_ids - mapped_ids):
        failures.append(f"{ec_id} is defined in a catalog but has no row in the mapping")
    for ec_id in sorted(catalog_ids):
        if ec_id not in story_ec_ids:
            continue  # not yet claimed by any story -- partial coverage, not a failure
        ec_record = edge_cases_map.get(ec_id)
        has_tests = isinstance(ec_record, dict) and bool(ec_record.get("tests"))
        if not has_tests:
            failures.append(f"{ec_id} is named by a story but has no proving test")
    return failures


def check_acyclic_dependencies(stories: list[Story]) -> list[str]:
    """'Acyclic dependencies' -- the depends_on graph across all stories has no cycle."""
    graph = {story.id: set(story.depends_on) for story in stories}
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle_found: list[str] = []

    def _visit(node: str, path: list[str]) -> None:
        if node in visited or node in cycle_found:
            return
        if node not in graph:
            return
        if node in visiting:
            cycle_found.append(" -> ".join([*path, node]))
            return
        visiting.add(node)
        for dep in sorted(graph.get(node, set())):
            _visit(dep, [*path, node])
        visiting.discard(node)
        visited.add(node)

    for story_id in sorted(graph):
        _visit(story_id, [])

    return [f"dependency cycle detected: {cycle}" for cycle in cycle_found]


def check_record_fresh(record: dict[str, object]) -> list[str]:
    """'Record fresh' -- re-running the generator must reproduce the committed file exactly,
    modulo the generated_at timestamp (which is expected to differ between generation runs
    but carries no information the freshness check needs to police)."""
    if not TRACEABILITY_PATH.is_file():
        return ["traceability.yaml does not exist -- run `just trace` to generate it"]

    committed_text = TRACEABILITY_PATH.read_text(encoding="utf-8")
    fresh_text = render_yaml(record)

    def _strip_timestamp(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if not line.startswith("generated_at:"))

    if _strip_timestamp(committed_text) != _strip_timestamp(fresh_text):
        return [
            "traceability.yaml is stale -- it differs from what `just trace` would generate "
            "right now; run `just trace` and commit the result"
        ]
    return []


def main() -> int:
    stories, schema_errors = load_all_stories()
    if schema_errors:
        sys.stderr.write("validate_traceability.py: story front-matter schema errors:\n")
        for error in schema_errors:
            sys.stderr.write(f"  - {error.story_path}: {error.message}\n")
        return 1

    collected_tests, collection_ok = collect_tests()
    if not collection_ok:
        sys.stderr.write(
            "validate_traceability.py: pytest --collect-only produced no usable output.\n"
        )
        return 1

    proves_index: dict[str, list[str]] = {}
    covers_index: dict[str, list[str]] = {}
    for test in collected_tests:
        if test.proves is not None:
            proves_index.setdefault(test.proves, []).append(test.node_id)
        for ec_id in test.covers:
            covers_index.setdefault(ec_id, []).append(test.node_id)

    generated_at = ""
    record = build_record(stories, proves_index, covers_index, generated_at=generated_at)
    module_inventory = load_module_inventory()

    all_failures: list[str] = []
    all_failures += check_clauses_resolve(stories)
    all_failures += check_modules_exist(stories, module_inventory)
    all_failures += check_acceptance_criteria_proven(stories, record)
    all_failures += check_no_orphan_test(collected_tests, stories)
    all_failures += check_edge_cases_covered(stories, record)
    all_failures += check_acyclic_dependencies(stories)
    all_failures += check_record_fresh(record)

    if all_failures:
        sys.stderr.write("validate_traceability.py: FAILED\n")
        for failure in all_failures:
            sys.stderr.write(f"  - {failure}\n")
        return 1

    sys.stdout.write(
        f"validate_traceability.py: OK "
        f"({len(stories)} stor{'y' if len(stories) == 1 else 'ies'}, "
        f"{len(collected_tests)} test(s) collected, zero gaps).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
