"""``TaskFileValidator`` concrete implementation — editor-strict (§9)."""

from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.task_files._internal.cascade import run_cascade
from ollama_llm_bench.backend.task_files._internal.parsing import parse_task_file
from ollama_llm_bench.backend.task_files.models import (
    FileValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationSeverity,
)


def _rejection_result(*, source_path: str, message: str) -> FileValidationResult:
    """Build the file-level-error verdict for a whole-file content rejection."""
    issue = ValidationIssue(
        level=ValidationLevel.FILE,
        severity=ValidationSeverity.ERROR,
        rule="unparseable_file",
        message=message,
    )
    return FileValidationResult(
        source_path=source_path,
        severity=ValidationSeverity.ERROR,
        save_enabled=False,
        file_issues=(issue,),
        task_results=(),
    )


class _TaskFileValidatorImpl:
    """The single ``TaskFileValidator`` implementation; constructed by ``make_task_file_validator``."""

    def validate(self, source_path: str, /) -> FileValidationResult:
        try:
            raw_tasks = parse_task_file(source_path)
        except TaskFileError as exc:
            # A content problem (wrong extension, malformed YAML, a too-new
            # schema_version) — reported as a badge, never raised.
            return _rejection_result(source_path=source_path, message=exc.message)
        except OSError as exc:
            # A genuine OS-level read failure — the one case the validator
            # itself raises for, per the TaskFileValidator protocol.
            raise TaskFileError(message=f"{source_path}: could not read file") from exc

        return run_cascade(source_path=source_path, raw_tasks=raw_tasks)
