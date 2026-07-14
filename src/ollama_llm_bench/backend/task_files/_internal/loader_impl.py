"""``TaskFileLoader`` concrete implementation — loader-tolerant (§5, EC-TASK-*)."""

from typing import Any

import msgspec

from ollama_llm_bench.backend.domain import BenchmarkTask, Difficulty, TaskOrigin
from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.task_files._internal.cascade import check_extension, run_cascade
from ollama_llm_bench.backend.task_files._internal.parsing import parse_task_file
from ollama_llm_bench.backend.task_files.models import ValidationSeverity

_VALID_DIFFICULTY_VALUES = frozenset(member.value for member in Difficulty)


def _sanitize_fallback_fields(raw_task: dict[str, Any]) -> dict[str, Any]:
    """Drop ``difficulty``/``cosine_enabled`` when they cannot coerce, so the
    struct's own field default applies instead of failing the whole task.

    ``04_YAML_TASK_FORMAT.md`` §9.2 makes both of these soft-warning
    fallbacks, not hard errors: an out-of-enum ``difficulty`` falls back to
    ``Difficulty.MEDIUM`` and a non-bool ``cosine_enabled`` falls back to
    ``True``. Passing an invalid raw value straight to ``msgspec.convert``
    would instead raise and drop the *entire* task via the generic safety
    net below — dropping just the offending key here lets
    ``BenchmarkTask``'s own default take over, per the approved design.

    Returns:
        A shallow copy of ``raw_task`` with any uncoercible ``difficulty``/
        ``cosine_enabled`` key removed.
    """
    fields = dict(raw_task)
    difficulty = fields.get("difficulty")
    if "difficulty" in fields and difficulty not in _VALID_DIFFICULTY_VALUES:
        del fields["difficulty"]
    cosine_enabled = fields.get("cosine_enabled")
    if "cosine_enabled" in fields and not isinstance(cosine_enabled, bool):
        del fields["cosine_enabled"]
    return fields


def _build_benchmark_task(raw_task: dict[str, Any]) -> BenchmarkTask | None:
    """Attempt to build a frozen ``BenchmarkTask`` from a raw task dict.

    Uses ``msgspec.convert`` (not the bare constructor) so every ``msgspec.Meta``
    field constraint — an over-128-character ``task_id`` included — is actually
    enforced; the plain ``BenchmarkTask(**fields)`` constructor does not validate
    ``Annotated`` constraints on direct construction.

    Returns:
        The constructed task, or ``None`` when the raw fields fail any
        ``BenchmarkTask`` constraint not already covered by the named cascade
        rules (the general safety net for STORY-031-AC-5).
    """
    fields = _sanitize_fallback_fields(raw_task)
    fields["task_origin"] = TaskOrigin.FILE.value
    try:
        return msgspec.convert(fields, type=BenchmarkTask)
    except msgspec.ValidationError:
        return None


class _TaskFileLoaderImpl:
    """The single ``TaskFileLoader`` implementation; constructed by ``make_task_file_loader``."""

    def load(self, source_path: str, /) -> tuple[BenchmarkTask, ...]:
        extension_issue = check_extension(source_path)
        if extension_issue is not None:
            raise TaskFileError(message=extension_issue.message)

        raw_tasks = parse_task_file(source_path)
        cascade_result = run_cascade(source_path=source_path, raw_tasks=raw_tasks)

        seen_task_ids: set[str] = set()
        tasks: list[BenchmarkTask] = []
        for task_result, raw_task in zip(cascade_result.task_results, raw_tasks, strict=True):
            if task_result.severity == ValidationSeverity.ERROR:
                continue
            task_id = task_result.task_id
            if task_id is not None and task_id in seen_task_ids:
                continue  # duplicate task_id: keep the first occurrence only (§5.1)
            task = _build_benchmark_task(raw_task)
            if task is None:
                continue
            if task_id is not None:
                seen_task_ids.add(task_id)
            tasks.append(task)
        return tuple(tasks)
