"""Task-file loader + validator.

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/12_YAML_FORMATTER.md`
and `14_VALIDATION_CASCADE.md`, `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`.

``TaskFileLoader`` parses a YAML task file into frozen ``BenchmarkTask`` records,
silently skipping any individually malformed task. ``TaskFileValidator`` runs the
same three-level (field/task/file) validation cascade in editor-strict mode,
reporting every problem at its fixed severity instead of skipping anything, so
the Task Editor can always show a badge and gate Save. The comment-preserving
writer lives in ``backend/yaml_formatter/``.
"""

from ollama_llm_bench.backend.task_files.api import (
    make_task_file_loader,
    make_task_file_validator,
)
from ollama_llm_bench.backend.task_files.models import (
    FileValidationResult,
    TaskValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationSeverity,
)
from ollama_llm_bench.backend.task_files.protocols import TaskFileLoader, TaskFileValidator

__all__: list[str] = [
    "FileValidationResult",
    "TaskFileLoader",
    "TaskFileValidator",
    "TaskValidationResult",
    "ValidationIssue",
    "ValidationLevel",
    "ValidationSeverity",
    "make_task_file_loader",
    "make_task_file_validator",
]
