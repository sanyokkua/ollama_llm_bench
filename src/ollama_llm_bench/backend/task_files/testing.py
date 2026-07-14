"""Configurable fakes for ``TaskFileLoader``/``TaskFileValidator`` for downstream tests."""

from ollama_llm_bench.backend.domain import BenchmarkTask
from ollama_llm_bench.backend.task_files.models import FileValidationResult

__all__: list[str] = ["FakeTaskFileLoader", "FakeTaskFileValidator"]


class FakeTaskFileLoader:
    """An in-memory fake with externally settable per-path return values.

    No real I/O and no real cascade logic behind it — set the tasks a test
    scenario needs directly with ``set_tasks``.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, tuple[BenchmarkTask, ...]] = {}
        self.recorded_loads: list[str] = []

    def load(self, source_path: str, /) -> tuple[BenchmarkTask, ...]:
        """Record the call and return whatever ``set_tasks`` configured, or ``()``."""
        self.recorded_loads.append(source_path)
        return self._tasks.get(source_path, ())

    def set_tasks(self, source_path: str, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Test helper: force ``load(source_path)``'s return value."""
        self._tasks[source_path] = tasks


class FakeTaskFileValidator:
    """An in-memory fake with externally settable per-path return values.

    No real I/O and no real cascade logic behind it — set the result a test
    scenario needs directly with ``set_validation_result``.
    """

    def __init__(self) -> None:
        self._results: dict[str, FileValidationResult] = {}
        self.recorded_validations: list[str] = []

    def validate(self, source_path: str, /) -> FileValidationResult:
        """Record the call and return whatever ``set_validation_result`` configured."""
        self.recorded_validations.append(source_path)
        result = self._results.get(source_path)
        if result is None:
            raise KeyError(
                f"FakeTaskFileValidator has no result configured for {source_path!r}; "
                "call set_validation_result first"
            )
        return result

    def set_validation_result(self, source_path: str, result: FileValidationResult) -> None:
        """Test helper: force ``validate(source_path)``'s return value."""
        self._results[source_path] = result
