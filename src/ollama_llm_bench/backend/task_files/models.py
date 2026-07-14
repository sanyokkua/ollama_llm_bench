"""Task-file validation DTOs: severities, levels, and result records.

Defines the three-severity model and three-level cascade vocabulary shared by
``TaskFileLoader`` and ``TaskFileValidator`` (`11_Services_and_Algorithms/
14_VALIDATION_CASCADE.md` §6.3, §6.4), plus the frozen result records the
validator returns.
"""

from enum import StrEnum

import msgspec


class ValidationSeverity(StrEnum):
    """The four-state severity ladder, ordered ``clean < info < warning < error`` (§6.3)."""

    CLEAN = "clean"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationLevel(StrEnum):
    """The cascade level a validation rule is scoped to (§6.1)."""

    FIELD = "field"
    TASK = "task"
    FILE = "file"


class ValidationIssue(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One fired validation rule.

    Attributes:
        level: The cascade level the rule belongs to.
        severity: The fixed severity this rule carries.
        rule: A short, stable rule identifier (e.g. ``"empty_question"``,
            ``"duplicate_task_id"``), suitable for tests and future badges to
            key off of.
        message: A human-readable description of the fired rule.
        task_index: The zero-based index of the task this issue is attached
            to within the file's ``tasks:`` sequence, or ``None`` for an
            issue that applies to the whole file with no single owning task.
        field_name: The task field this issue concerns, or ``None`` for a
            task- or file-level issue with no single owning field.
    """

    level: ValidationLevel
    severity: ValidationSeverity
    rule: str
    message: str
    task_index: int | None = None
    field_name: str | None = None


class TaskValidationResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The aggregated validation state of one task within a file (§6.4).

    Attributes:
        task_index: The zero-based index of the task within the file's
            ``tasks:`` sequence.
        task_id: The task's declared ``task_id``, or ``None`` when the task
            has no usable ``task_id`` value.
        severity: The maximum severity of every issue attached to this task.
        issues: Every field- and task-level issue fired for this task, plus
            any file-level issue (e.g. a duplicate ``task_id``) attached to
            this specific row.
    """

    task_index: int
    task_id: str | None
    severity: ValidationSeverity
    issues: tuple[ValidationIssue, ...] = ()


class FileValidationResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The aggregated validation state of one task file (§6.4, §6.5).

    Attributes:
        source_path: The path of the file that was validated.
        severity: The maximum severity across every file-level issue and
            every task's severity.
        save_enabled: ``True`` unless ``severity`` is ``ERROR`` — a file with
            any hard error anywhere has Save disabled (§6.5).
        file_issues: Issues that apply to the whole file with no single
            owning task (extension, empty file).
        task_results: One result per task in the file's ``tasks:`` sequence,
            in file order.
    """

    source_path: str
    severity: ValidationSeverity
    save_enabled: bool
    file_issues: tuple[ValidationIssue, ...] = ()
    task_results: tuple[TaskValidationResult, ...] = ()
