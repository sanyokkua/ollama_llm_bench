"""The seven-rule validation cascade shared by the loader and the validator.

Source of truth: STORY-031-AC-6's condition table. This is a deliberately small
subset of the full per-field rule catalogue in `09_Task_Editor/field_reference.md`
— only the seven conditions named by the acceptance criterion are implemented
here; the remaining catalogue is out of this story's scope.

Running this cascade against the same raw per-task ``dict`` list is what keeps
``TaskFileLoader`` and ``TaskFileValidator`` from ever disagreeing about which
tasks are usable.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ollama_llm_bench.backend.task_files._internal.severity import max_severity
from ollama_llm_bench.backend.task_files.models import (
    FileValidationResult,
    TaskValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationSeverity,
)

_VALID_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml"})
_LONG_PROMPT_THRESHOLD = 8000
_MIN_DUPLICATE_COUNT = 2


def _extract_task_id(raw_task: Mapping[str, Any]) -> str | None:
    task_id = raw_task.get("task_id")
    return task_id if isinstance(task_id, str) else None


def _text_field(raw_task: Mapping[str, Any], field_name: str) -> str:
    value = raw_task.get(field_name)
    return value if isinstance(value, str) else ""


def check_extension(source_path: str) -> ValidationIssue | None:
    """Flag a non-``.yaml``/``.yml`` extension as a file-level hard error."""
    suffix = Path(source_path).suffix.lower()
    if suffix in _VALID_EXTENSIONS:
        return None
    return ValidationIssue(
        level=ValidationLevel.FILE,
        severity=ValidationSeverity.ERROR,
        rule="invalid_extension",
        message=f"File extension {suffix or '(none)'} is not .yaml or .yml.",
    )


def check_empty_file(raw_tasks: Sequence[Mapping[str, Any]]) -> ValidationIssue | None:
    """Flag a file with zero tasks as a file-level soft warning."""
    if raw_tasks:
        return None
    return ValidationIssue(
        level=ValidationLevel.FILE,
        severity=ValidationSeverity.WARNING,
        rule="empty_file",
        message="File has zero tasks.",
    )


def check_duplicate_task_ids(
    raw_tasks: Sequence[Mapping[str, Any]],
) -> tuple[ValidationIssue, ...]:
    """Flag every row sharing a ``task_id`` with another row as a hard error."""
    indices_by_task_id: dict[str, list[int]] = {}
    for task_index, raw_task in enumerate(raw_tasks):
        task_id = _extract_task_id(raw_task)
        if task_id:
            indices_by_task_id.setdefault(task_id, []).append(task_index)

    issues: list[ValidationIssue] = []
    for task_id, indices in indices_by_task_id.items():
        if len(indices) < _MIN_DUPLICATE_COUNT:
            continue
        for task_index in indices:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.FILE,
                    severity=ValidationSeverity.ERROR,
                    rule="duplicate_task_id",
                    message=f"task_id {task_id!r} is shared by {len(indices)} tasks.",
                    task_index=task_index,
                    field_name="task_id",
                )
            )
    return tuple(issues)


def check_empty_question(task_index: int, raw_task: Mapping[str, Any]) -> ValidationIssue | None:
    """Flag an empty-after-trim ``question`` as a field-level hard error."""
    if _text_field(raw_task, "question").strip():
        return None
    return ValidationIssue(
        level=ValidationLevel.FIELD,
        severity=ValidationSeverity.ERROR,
        rule="empty_question",
        message="question is empty after whitespace trimming.",
        task_index=task_index,
        field_name="question",
    )


def check_empty_category(task_index: int, raw_task: Mapping[str, Any]) -> ValidationIssue | None:
    """Flag an empty ``category`` as a field-level soft warning."""
    if _text_field(raw_task, "category").strip():
        return None
    return ValidationIssue(
        level=ValidationLevel.FIELD,
        severity=ValidationSeverity.WARNING,
        rule="empty_category",
        message="category is empty.",
        task_index=task_index,
        field_name="category",
    )


def check_long_prompt(task_index: int, raw_task: Mapping[str, Any]) -> ValidationIssue | None:
    """Flag a ``question`` over the long-prompt threshold as a field-level soft info."""
    if len(_text_field(raw_task, "question")) <= _LONG_PROMPT_THRESHOLD:
        return None
    return ValidationIssue(
        level=ValidationLevel.FIELD,
        severity=ValidationSeverity.INFO,
        rule="long_prompt",
        message=(
            f"question is longer than {_LONG_PROMPT_THRESHOLD} characters — "
            "may push the model's context window."
        ),
        task_index=task_index,
        field_name="question",
    )


def check_retired_task_type(task_index: int, raw_task: Mapping[str, Any]) -> ValidationIssue | None:
    """Flag a retired ``task_type`` key (DD-46) as a task-level soft warning."""
    if "task_type" not in raw_task:
        return None
    return ValidationIssue(
        level=ValidationLevel.TASK,
        severity=ValidationSeverity.WARNING,
        rule="retired_task_type_key",
        message="task_type is a retired key (DD-46) and is ignored.",
        task_index=task_index,
    )


_PER_TASK_CHECKS = (
    check_empty_question,
    check_empty_category,
    check_long_prompt,
    check_retired_task_type,
)


def run_cascade(
    *, source_path: str, raw_tasks: Sequence[Mapping[str, Any]]
) -> FileValidationResult:
    """Run the seven-rule cascade and aggregate severities per §6.4.

    Args:
        source_path: The path being validated; drives the extension rule.
        raw_tasks: The raw per-task dicts produced by ``parse_task_file``.

    Returns:
        The full file validation verdict: one ``TaskValidationResult`` per
        task, plus the aggregated file-level state.
    """
    file_issues: list[ValidationIssue] = []
    extension_issue = check_extension(source_path)
    if extension_issue is not None:
        file_issues.append(extension_issue)
    empty_file_issue = check_empty_file(raw_tasks)
    if empty_file_issue is not None:
        file_issues.append(empty_file_issue)

    per_task_issues: list[list[ValidationIssue]] = [[] for _ in raw_tasks]
    for duplicate_issue in check_duplicate_task_ids(raw_tasks):
        if duplicate_issue.task_index is not None:
            per_task_issues[duplicate_issue.task_index].append(duplicate_issue)

    for task_index, raw_task in enumerate(raw_tasks):
        for check in _PER_TASK_CHECKS:
            issue = check(task_index, raw_task)
            if issue is not None:
                per_task_issues[task_index].append(issue)

    task_results = tuple(
        TaskValidationResult(
            task_index=task_index,
            task_id=_extract_task_id(raw_tasks[task_index]),
            severity=max_severity(*(issue.severity for issue in issues)),
            issues=tuple(issues),
        )
        for task_index, issues in enumerate(per_task_issues)
    )
    file_severity = max_severity(
        *(issue.severity for issue in file_issues),
        *(task_result.severity for task_result in task_results),
    )
    return FileValidationResult(
        source_path=source_path,
        severity=file_severity,
        save_enabled=file_severity != ValidationSeverity.ERROR,
        file_issues=tuple(file_issues),
        task_results=task_results,
    )
