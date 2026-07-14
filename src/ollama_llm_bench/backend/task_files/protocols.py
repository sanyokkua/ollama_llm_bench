"""TaskFileLoader and TaskFileValidator — this module's swap points."""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkTask
from ollama_llm_bench.backend.task_files.models import FileValidationResult


class TaskFileLoader(Protocol):
    """Loader-tolerant reader: parses a task file into frozen ``BenchmarkTask`` rows."""

    def load(self, source_path: str, /) -> tuple[BenchmarkTask, ...]:
        """Parse ``source_path`` into ``BenchmarkTask`` records, skipping bad tasks.

        blocking; runs on a worker thread when invoked from a run-configuration
        flow. Never raises for a per-task problem — a malformed individual task
        (an empty ``question``, an over-long ``task_id``, an unparseable field)
        is silently skipped, not surfaced.

        Args:
            source_path: The absolute path of the ``.yaml``/``.yml`` file to load.

        Returns:
            The valid tasks in file order, each tagged ``TaskOrigin.FILE``. A
            duplicate ``task_id`` keeps only its first occurrence.

        Raises:
            TaskFileError: The whole file is rejected — a non-``.yaml``/``.yml``
                extension, YAML that does not parse at all, or a
                ``schema_version`` newer than this build supports.
        """
        ...


class TaskFileValidator(Protocol):
    """Editor-strict validator: reports every field/task/file problem at its severity."""

    def validate(self, source_path: str, /) -> FileValidationResult:
        """Validate ``source_path`` and report every problem found.

        fast-synchronous; runs on the Qt UI thread (`14_VALIDATION_CASCADE.md`
        §9). Never raises for a content problem — a wrong extension, malformed
        YAML, a duplicate ``task_id``, and so on each become a file-level
        ``ValidationIssue`` instead, so the editor can always show a badge
        rather than refuse to open the tab.

        Args:
            source_path: The absolute path of the file to validate.

        Returns:
            The full validation verdict for the file, aggregated per §6.4.

        Raises:
            TaskFileError: A genuine OS-level read failure occurred (the file
                could not be opened/read) — never raised for a content problem.
        """
        ...
