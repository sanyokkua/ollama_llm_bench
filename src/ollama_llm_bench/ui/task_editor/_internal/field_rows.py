"""Pure task-mapping + validation -> ``FieldRowViewModel`` selection (STORY-069-AC-1,
AC-2).

Source of truth: ``09_Task_Editor/field_reference.md`` §4-§20 for every field's label,
format hint, help text, requirement, and control kind; §23 for the canonical field
order this module's row order matches. No Qt import here -- directly unit-testable,
matching ``_internal/view_model_select.py``'s precedent.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ollama_llm_bench.backend.domain import Difficulty
from ollama_llm_bench.backend.task_files import (
    TaskValidationResult,
    ValidationIssue,
    ValidationSeverity,
)
from ollama_llm_bench.ui.task_editor.models import (
    FieldControlKind,
    FieldRowViewModel,
    ValidationState,
)

__all__: list[str] = ["FIELD_GROUPS", "select_field_rows"]

_SEVERITY_TO_STATE: dict[ValidationSeverity, ValidationState] = {
    ValidationSeverity.CLEAN: ValidationState.CLEAN,
    ValidationSeverity.INFO: ValidationState.INFO,
    ValidationSeverity.WARNING: ValidationState.WARNING,
    ValidationSeverity.ERROR: ValidationState.ERROR,
}
_TRUE_STR = "true"
_FALSE_STR = "false"


@dataclass(frozen=True)
class _FieldSpec:
    """One field's static rendering metadata (field_reference.md), strictly
    module-private -- never crosses the module boundary."""

    field_name: str
    label: str
    is_required: bool
    format_hint: str
    help_text: str
    control_kind: FieldControlKind
    default_value: str = ""


_FIELD_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec(
        field_name="task_id",
        label="Task ID",
        is_required=True,
        format_hint="snake_case, ASCII, max 80 characters, unique in file",
        help_text=(
            "The unique identifier of the task within its file. It is the stable join "
            "key against every benchmark result row, so changing it after a run "
            "separates the task from its historical results. Use lowercase snake_case. "
            "A common convention is <category>_<sub_category>_<short_summary>. "
            "Example: translation_uk_en_greeting"
        ),
        control_kind=FieldControlKind.IDENTIFIER,
    ),
    _FieldSpec(
        field_name="category",
        label="Category",
        is_required=False,
        format_hint="recommended, free text, Sentence Case",
        help_text=(
            "The high-level grouping the task belongs to, shown in charts and reports "
            '(for example "Coding", "Text Operations"). Leaving it empty does not '
            "block a run but removes the task from per-category aggregation."
        ),
        control_kind=FieldControlKind.SHORT_TEXT,
    ),
    _FieldSpec(
        field_name="sub_category",
        label="Sub-category",
        is_required=False,
        format_hint="recommended, free text, Sentence Case",
        help_text=(
            'The second-level grouping within a category (for example "Java", '
            '"Translation"). It refines category and gives finer-grained breakdowns '
            "in reports."
        ),
        control_kind=FieldControlKind.SHORT_TEXT,
    ),
    _FieldSpec(
        field_name="difficulty",
        label="Difficulty",
        is_required=False,
        format_hint="optional, default medium",
        help_text=(
            "The declared difficulty band of the task, used for the per-difficulty "
            "breakdown in charts and reports. It does not change how the task is "
            "graded. Allowed values: easy, medium, hard."
        ),
        control_kind=FieldControlKind.ENUM,
        default_value=Difficulty.MEDIUM.value,
    ),
    _FieldSpec(
        field_name="cosine_enabled",
        label="Cosine grading enabled",
        is_required=False,
        format_hint="optional, default true",
        help_text=(
            "Task-level cosine opt-out (DD-46). When checked (the default), the "
            "cosine phase compares the model's response to the golden answer. "
            "Uncheck it for tasks where whole-text similarity is not a meaningful "
            "signal -- for example code tasks."
        ),
        control_kind=FieldControlKind.BOOLEAN,
        default_value=_TRUE_STR,
    ),
    _FieldSpec(
        field_name="question",
        label="Question",
        is_required=True,
        format_hint="required, plain text or markdown",
        help_text=(
            "The exact prompt sent to the model. The model sees this verbatim -- "
            "there is no template wrapping beyond the globally configured system "
            "prompt. Multi-line content and code fences are allowed."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
    _FieldSpec(
        field_name="golden_answer",
        label="Golden answer",
        is_required=True,
        format_hint="required, supports literal block",
        help_text=(
            "The reference answer used by the keyword and cosine evaluation layers "
            "and shown to the judge in GRADED. It can be plain text, code, JSON, "
            "CSV -- anything a comparison makes sense over."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
    _FieldSpec(
        field_name="pass_criteria",
        label="Pass criteria",
        is_required=False,
        format_hint="recommended, plain prose, 1-3 sentences",
        help_text=(
            "A natural-language description of what the model must do to receive a "
            "passing verdict. The judge weighs it heavily in GRADED."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
    _FieldSpec(
        field_name="fail_criteria",
        label="Fail criteria",
        is_required=False,
        format_hint="recommended, plain prose, often the inverse of pass_criteria",
        help_text=(
            "A natural-language description of what makes an answer fail. The judge "
            "uses it to detect anti-patterns that look correct on the surface but "
            "break the spirit of the task."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
    _FieldSpec(
        field_name="required_terms.exact",
        label="Required terms -- exact",
        is_required=False,
        format_hint="substrings that MUST appear verbatim",
        help_text=(
            "Substrings that must appear verbatim in the model's response. The "
            "keyword evaluation phase fails the task if any of these is missing. "
            "Matching is case-sensitive."
        ),
        control_kind=FieldControlKind.CHIP_LIST,
    ),
    _FieldSpec(
        field_name="required_terms.semantic",
        label="Required terms -- semantic",
        is_required=False,
        format_hint="concepts the response should convey",
        help_text=(
            "Concepts the response should convey, matched semantically by embedding "
            "similarity rather than literally -- synonyms count."
        ),
        control_kind=FieldControlKind.CHIP_LIST,
    ),
    _FieldSpec(
        field_name="required_terms.forbidden",
        label="Required terms -- forbidden",
        is_required=False,
        format_hint="substrings that MUST NOT appear",
        help_text=(
            "Substrings that must not appear in the model's response. Useful for "
            '"rewrite without these words" tasks and "avoid this pattern" coding tasks.'
        ),
        control_kind=FieldControlKind.CHIP_LIST,
    ),
    _FieldSpec(
        field_name="source_language",
        label="Source language",
        is_required=False,
        format_hint="ISO 639-1 code, lowercase, two letters",
        help_text=(
            "The language code of the input prompt, used by the judge prompt "
            "template for translation tasks. Use the lowercase two-letter ISO 639-1 "
            "code."
        ),
        control_kind=FieldControlKind.SHORT_TEXT,
    ),
    _FieldSpec(
        field_name="target_language",
        label="Target language",
        is_required=False,
        format_hint="ISO 639-1 code, lowercase, two letters",
        help_text="The language code of the expected output. Same rules as source_language.",
        control_kind=FieldControlKind.SHORT_TEXT,
    ),
    _FieldSpec(
        field_name="source_material",
        label="Source material",
        is_required=False,
        format_hint="optional, plain text / markdown / code",
        help_text=(
            "Background material the prompt operates on -- an article to summarise, "
            "a file to convert, code to review."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
    _FieldSpec(
        field_name="fail_example",
        label="Fail example",
        is_required=False,
        format_hint="optional, a concrete known-bad answer",
        help_text=(
            "A concrete example of an answer that should fail. The judge uses it as "
            "a contrasting reference when a response is ambiguous."
        ),
        control_kind=FieldControlKind.LONG_TEXT,
    ),
)

FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Required terms",
        ("required_terms.exact", "required_terms.semantic", "required_terms.forbidden"),
    ),
    ("Translation extras", ("source_language", "target_language")),
    ("Input material", ("source_material",)),
    ("Optional context", ("fail_example",)),
)
"""Section name -> the field names it holds (§3.5.2). Every field not named by any
group is rendered ungrouped, above the groups, in ``_FIELD_SPECS`` order. Every group
is always available (DD-46 -- no conditional driver)."""


def _read_value(task: Mapping[str, Any], spec: _FieldSpec) -> tuple[str, tuple[str, ...]]:
    if spec.control_kind is FieldControlKind.CHIP_LIST:
        group_key, _, leaf_key = spec.field_name.partition(".")
        nested = task.get(group_key)
        values = nested.get(leaf_key, ()) if isinstance(nested, Mapping) else ()
        return "", tuple(str(value) for value in values)
    if spec.control_kind is FieldControlKind.BOOLEAN:
        raw = task.get(spec.field_name, True)
        return (_TRUE_STR if bool(raw) else _FALSE_STR), ()
    raw_value = task.get(spec.field_name, spec.default_value)
    return str(raw_value), ()


def _issue_for_field(
    issues: tuple[ValidationIssue, ...], field_name: str
) -> tuple[ValidationState, str]:
    matching = tuple(issue for issue in issues if issue.field_name == field_name)
    if not matching:
        return ValidationState.CLEAN, ""
    worst = max(matching, key=lambda issue: tuple(ValidationSeverity).index(issue.severity))
    return _SEVERITY_TO_STATE[worst.severity], worst.message


def select_field_rows(
    *, task: Mapping[str, Any], task_validation: TaskValidationResult | None
) -> tuple[FieldRowViewModel, ...]:
    """Derive every Field Row for the selected task, in canonical field order (§23).

    Args:
        task: The selected task's raw mapping (``buffer.document["tasks"][index]``).
        task_validation: The task's cascade result, or ``None`` before the first
            validation pass has run.

    Returns:
        One ``FieldRowViewModel`` per field in ``09_Task_Editor/field_reference.md``
        order; every group is always visible (DD-46).
    """
    issues = task_validation.issues if task_validation is not None else ()
    rows: list[FieldRowViewModel] = []
    for spec in _FIELD_SPECS:
        value, chip_values = _read_value(task, spec)
        state, message = _issue_for_field(issues, spec.field_name)
        rows.append(
            FieldRowViewModel(
                field_name=spec.field_name,
                label=spec.label,
                is_required=spec.is_required,
                format_hint=spec.format_hint,
                help_text=spec.help_text,
                control_kind=spec.control_kind,
                value=value,
                chip_values=chip_values,
                is_visible=True,
                validation_state=state,
                validation_message=message,
            )
        )
    return tuple(rows)
