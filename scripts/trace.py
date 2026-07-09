"""Traceability record generator: regenerates traceability.yaml from docs/stories/ and the
collected test suite.

See docs/v3_specification/14_Process_and_Traceability/03_TRACEABILITY.md Section 4
("Generating the Record") for the three-pass algorithm this implements:

1. Parse every story's front-matter.
2. Collect tests via `pytest --collect-only`, reading each test's `Proves:` docstring line.
3. Assemble the four index maps (`stories`, `clauses`, `edge_cases`, `modules`) and write
   traceability.yaml at the repository root, deterministically (sorted keys, sorted lists) so
   re-running produces a byte-identical file.

Invoked via `just trace`.
"""

from __future__ import annotations

import datetime as dt
from io import StringIO
import sys

from ruamel.yaml import YAML

from _traceability_lib import (
    TRACEABILITY_PATH,
    Story,
    collect_tests,
    load_all_stories,
)

GENERATOR_VERSION = 1


def _acceptance_criteria_tests(
    story: Story, proves_index: dict[str, list[str]]
) -> dict[str, dict[str, list[str]]]:
    return {
        ac_id: {"tests": sorted(proves_index.get(ac_id, []))}
        for ac_id in sorted(story.acceptance_criteria)
    }


def _build_stories_map(
    stories: list[Story], proves_index: dict[str, list[str]]
) -> dict[str, object]:
    return {
        story.id: {
            "title": story.title,
            "status": story.status,
            "spec_clauses": sorted(story.spec_clauses),
            "modules": sorted(story.modules),
            "edge_cases": sorted(story.edge_cases),
            "acceptance_criteria": _acceptance_criteria_tests(story, proves_index),
        }
        for story in sorted(stories, key=lambda s: s.id)
    }


def _build_clauses_map(stories: list[Story]) -> dict[str, object]:
    clause_to_stories: dict[str, set[str]] = {}
    for story in stories:
        for clause in story.spec_clauses:
            clause_to_stories.setdefault(clause, set()).add(story.id)
    return {
        clause: {"stories": sorted(story_ids)}
        for clause, story_ids in sorted(clause_to_stories.items())
    }


def _build_edge_cases_map(
    stories: list[Story], proves_index: dict[str, list[str]]
) -> dict[str, object]:
    ec_to_stories: dict[str, set[str]] = {}
    ec_to_tests: dict[str, set[str]] = {}
    for story in stories:
        for ec_id in story.edge_cases:
            ec_to_stories.setdefault(ec_id, set()).add(story.id)
            for ac_id in story.acceptance_criteria:
                ec_to_tests.setdefault(ec_id, set()).update(proves_index.get(ac_id, []))
    return {
        ec_id: {
            "stories": sorted(ec_to_stories[ec_id]),
            "tests": sorted(ec_to_tests.get(ec_id, set())),
        }
        for ec_id in sorted(ec_to_stories)
    }


def _build_modules_map(stories: list[Story]) -> dict[str, object]:
    module_to_stories: dict[str, set[str]] = {}
    for story in stories:
        for module in story.modules:
            module_to_stories.setdefault(module, set()).add(story.id)
    return {
        module: {"stories": sorted(story_ids)}
        for module, story_ids in sorted(module_to_stories.items())
    }


def build_record(
    stories: list[Story], proves_index: dict[str, list[str]], *, generated_at: str
) -> dict[str, object]:
    """Assemble the four-index traceability record from parsed stories and the test-proves
    index. Pure function of its inputs (aside from the caller-supplied timestamp) so the
    generator is deterministic given the same stories, tests, and timestamp."""
    return {
        "generated_at": generated_at,
        "generator_version": GENERATOR_VERSION,
        "stories": _build_stories_map(stories, proves_index),
        "clauses": _build_clauses_map(stories),
        "edge_cases": _build_edge_cases_map(stories, proves_index),
        "modules": _build_modules_map(stories),
    }


def render_yaml(record: dict[str, object]) -> str:
    """Render the record to YAML text with the generator's header comment."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 4096
    buffer = StringIO()
    yaml.dump(record, buffer)
    header = "# traceability.yaml — GENERATED. Do not edit by hand. Regenerate with `just trace`.\n"
    return header + buffer.getvalue()


def main() -> int:
    stories, schema_errors = load_all_stories()
    if schema_errors:
        sys.stderr.write("trace.py: story front-matter schema errors:\n")
        for error in schema_errors:
            sys.stderr.write(f"  - {error.story_path}: {error.message}\n")
        return 1

    collected_tests, collection_ok = collect_tests()
    if not collection_ok:
        sys.stderr.write("trace.py: pytest --collect-only produced no usable test output.\n")
        return 1

    proves_index: dict[str, list[str]] = {}
    for test in collected_tests:
        if test.proves is not None:
            proves_index.setdefault(test.proves, []).append(test.node_id)

    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = build_record(stories, proves_index, generated_at=generated_at)
    TRACEABILITY_PATH.write_text(render_yaml(record), encoding="utf-8")

    sys.stdout.write(
        f"trace.py: wrote {TRACEABILITY_PATH.name} "
        f"({len(stories)} stor{'y' if len(stories) == 1 else 'ies'}, "
        f"{len(collected_tests)} test(s) collected).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
