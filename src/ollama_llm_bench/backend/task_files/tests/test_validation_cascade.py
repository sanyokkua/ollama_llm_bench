"""Colocated tests for the validation cascade — see STORY-031-AC-6."""

from pathlib import Path
from typing import NamedTuple

import pytest

from ollama_llm_bench.backend.task_files import make_task_file_validator
from ollama_llm_bench.backend.task_files.models import ValidationLevel, ValidationSeverity

_MINIMAL_VALID_TASK = """\
schema_version: 1
tasks:
  - task_id: valid_task
    question: What is the capital of France?
"""

_EMPTY_QUESTION = 'schema_version: 1\ntasks:\n  - task_id: t1\n    question: "   "\n'

_DUPLICATE_TASK_ID = """\
schema_version: 1
tasks:
  - task_id: dup_id
    question: First question.
  - task_id: dup_id
    question: Second question.
"""

_EMPTY_CATEGORY = """\
schema_version: 1
tasks:
  - task_id: valid_task
    question: What is the capital of France?
    category: ""
"""

_EMPTY_FILE = """\
schema_version: 1
tasks: []
"""

_RETIRED_TASK_TYPE = """\
schema_version: 1
tasks:
  - task_id: valid_task
    question: What is the capital of France?
    task_type: factual
"""

_LONG_PROMPT = (
    'schema_version: 1\ntasks:\n  - task_id: valid_task\n    category: General\n    question: "'
    + ("x" * 8001 + '"\n')
)


class _Case(NamedTuple):
    """One row of STORY-031-AC-6's condition table."""

    case_id: str
    filename: str
    content: str
    expected_rule: str
    expected_level: ValidationLevel
    expected_severity: ValidationSeverity
    expected_aggregate: ValidationSeverity


_CASES: tuple[_Case, ...] = (
    _Case(
        "empty_question",
        "tasks.yaml",
        _EMPTY_QUESTION,
        "empty_question",
        ValidationLevel.FIELD,
        ValidationSeverity.ERROR,
        ValidationSeverity.ERROR,
    ),
    _Case(
        "duplicate_task_id",
        "tasks.yaml",
        _DUPLICATE_TASK_ID,
        "duplicate_task_id",
        ValidationLevel.FILE,
        ValidationSeverity.ERROR,
        ValidationSeverity.ERROR,
    ),
    _Case(
        "invalid_extension",
        "tasks.txt",
        _MINIMAL_VALID_TASK,
        "invalid_extension",
        ValidationLevel.FILE,
        ValidationSeverity.ERROR,
        ValidationSeverity.ERROR,
    ),
    _Case(
        "empty_category",
        "tasks.yaml",
        _EMPTY_CATEGORY,
        "empty_category",
        ValidationLevel.FIELD,
        ValidationSeverity.WARNING,
        ValidationSeverity.WARNING,
    ),
    _Case(
        "empty_file",
        "tasks.yaml",
        _EMPTY_FILE,
        "empty_file",
        ValidationLevel.FILE,
        ValidationSeverity.WARNING,
        ValidationSeverity.WARNING,
    ),
    _Case(
        "long_prompt",
        "tasks.yaml",
        _LONG_PROMPT,
        "long_prompt",
        ValidationLevel.FIELD,
        ValidationSeverity.INFO,
        ValidationSeverity.INFO,
    ),
    _Case(
        "retired_task_type",
        "tasks.yaml",
        _RETIRED_TASK_TYPE,
        "retired_task_type_key",
        ValidationLevel.TASK,
        ValidationSeverity.WARNING,
        ValidationSeverity.WARNING,
    ),
)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.case_id)
def test_validator_assigns_severity_and_aggregates(tmp_path: Path, case: _Case) -> None:
    """Proves: STORY-031-AC-6

    Each of the seven cascade conditions fires its issue at the fixed
    level/severity and aggregates to the expected file-level state.
    """
    source_path = tmp_path / case.filename
    source_path.write_text(case.content, encoding="utf-8")

    validator = make_task_file_validator()
    result = validator.validate(str(source_path))

    all_issues = list(result.file_issues) + [
        issue for task_result in result.task_results for issue in task_result.issues
    ]
    matching = [issue for issue in all_issues if issue.rule == case.expected_rule]

    assert matching, f"no issue with rule {case.expected_rule!r} found in {all_issues!r}"
    assert matching[0].level == case.expected_level
    assert matching[0].severity == case.expected_severity
    assert result.severity == case.expected_aggregate
    assert result.save_enabled == (case.expected_aggregate != ValidationSeverity.ERROR)
