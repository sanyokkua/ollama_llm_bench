"""Shared fixtures and fakes for ``ui/results/tests/`` (STORY-061).

Mirrors ``ui/progress/tests/conftest.py``'s in-process synchronous ``EventBus`` test
double pattern (immediate delivery) and ``ui/resume_benchmark/tests/test_controller.py``'s
locally-declared Protocol fakes.
"""

from collections.abc import Callable
import re

import pytest

from ollama_llm_bench.adapters.native_pickers import SavePickerOptions
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartKind,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.ui.results.models import ResultCollaborators

__all__: list[str] = [
    "FakeClipboard",
    "FakeEventBus",
    "FakeExportFilenameHelper",
    "FakeFileSystemActions",
    "FakeNativePickers",
    "FakeNotificationService",
    "FakeResultGateway",
    "make_run",
]

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")


class _FakeSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double (immediate delivery)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return _FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class FakeResultGateway:
    """In-memory ``ResultGateway`` fake: a run list, per-run results, and settings."""

    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...] = (),
        results_by_run_id: dict[RunId, tuple[BenchmarkResult, ...]] | None = None,
    ) -> None:
        self._runs = {run.run_id: run for run in runs}
        self._results_by_run_id = results_by_run_id or {}
        self._tasks_by_run_id: dict[RunId, tuple[BenchmarkTask, ...]] = {}
        self._chart_data_by_run_id: dict[RunId, dict[ChartKind, ChartData]] = {}
        self._settings: dict[str, str] = {}
        self.serialize_table_calls: list[tuple[RunId, str, str]] = []
        self.chart_data_calls: list[tuple[RunId, ChartKind]] = []

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return tuple(self._runs.values())

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[run_id]

    def persist_run_analysis(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results_by_run_id.get(run_id, ())

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return self._tasks_by_run_id.get(run_id, ())

    def get_setting(self, key: str) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._settings[key] = value

    def regenerate_run_analysis(self, run_id: RunId) -> None:
        raise NotImplementedError

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData:
        self.chart_data_calls.append((run_id, chart_kind))
        configured = self._chart_data_by_run_id.get(run_id, {}).get(chart_kind)
        if configured is not None:
            return configured
        return ChartData(
            chart_kind=chart_kind, categories=(), series=(), empty_state_message="No data yet."
        )

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        self.serialize_table_calls.append((run_id, table, fmt))
        return f"{table}-{fmt}-content"

    def add_run(self, run: BenchmarkRun) -> None:
        """Test-only helper: add a run and re-emit ``list_runs()`` immediately."""
        self._runs[run.run_id] = run

    def set_results(self, run_id: RunId, results: tuple[BenchmarkResult, ...]) -> None:
        """Test-only helper: set a run's results after construction."""
        self._results_by_run_id[run_id] = results

    def set_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Test-only helper: set a run's frozen tasks after construction."""
        self._tasks_by_run_id[run_id] = tasks

    def set_chart_data(self, run_id: RunId, chart_kind: ChartKind, data: ChartData) -> None:
        """Test-only helper: configure one chart kind's prepared data for a run."""
        self._chart_data_by_run_id.setdefault(run_id, {})[chart_kind] = data


class FakeExportFilenameHelper:
    """Real sanitisation + ``Run_<run_id>`` fallback (05_EXPORT_FORMATS.md §2, EC-RES-6)."""

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        sanitized = _sanitize(run.run_name or "")
        base = sanitized if sanitized else f"Run_{run.run_id}"
        return f"{base}_{kind}.{ext}"


def _sanitize(name: str) -> str:
    replaced = _SANITIZE_RE.sub("_", name)
    collapsed = re.sub(r"_+", "_", replaced)
    stripped = collapsed.strip("_").lstrip(".")
    return stripped[:80]


class FakeNativePickers:
    def __init__(self, *, chosen_path: str | None = "/desktop/chosen.csv") -> None:
        self._chosen_path = chosen_path
        self.save_file_calls: list[SavePickerOptions] = []

    def save_file(self, options: SavePickerOptions) -> str | None:
        self.save_file_calls.append(options)
        return self._chosen_path

    def open_file(self, options: object) -> tuple[str, ...]:
        raise NotImplementedError

    def open_folder(self, options: object) -> str | None:
        raise NotImplementedError


class FakeClipboard:
    def __init__(self) -> None:
        self.copied: list[str] = []

    def copy_text(self, text: str) -> None:
        self.copied.append(text)


class FakeFileSystemActions:
    def __init__(self, *, fail_write: bool = False) -> None:
        self._fail_write = fail_write
        self.written: dict[str, str] = {}
        self.written_bytes: dict[str, bytes] = {}
        self.revealed_paths: list[str] = []

    def open_in_file_manager(self, path: str) -> None:
        self.revealed_paths.append(path)

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return ""

    def write_export_file(self, *, filename: str, content: str) -> str:
        if self._fail_write:
            from ollama_llm_bench.backend.errors import OsAdapterError  # noqa: PLC0415

            raise OsAdapterError(message="disk full")
        path = f"/app-data/exports/{filename}"
        self.written[path] = content
        return path

    def write_text_file(self, *, path: str, content: str) -> None:
        if self._fail_write:
            from ollama_llm_bench.backend.errors import OsAdapterError  # noqa: PLC0415

            raise OsAdapterError(message="disk full")
        self.written[path] = content

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        if self._fail_write:
            from ollama_llm_bench.backend.errors import OsAdapterError  # noqa: PLC0415

            raise OsAdapterError(message="disk full")
        path = f"/app-data/exports/{filename}"
        self.written_bytes[path] = content
        return path

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        if self._fail_write:
            from ollama_llm_bench.backend.errors import OsAdapterError  # noqa: PLC0415

            raise OsAdapterError(message="disk full")
        self.written_bytes[path] = content

    def exports_folder_path(self) -> str:
        return "/app-data/exports"


class FakeNotificationService:
    def __init__(self) -> None:
        self.info: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[tuple[str, bool]] = []

    def show_info(self, text: str, duration_ms: int = 5000) -> None:
        self.info.append(text)

    def show_warning(self, text: str, duration_ms: int = 5000) -> None:
        self.warnings.append(text)

    def show_error(self, text: str, *, blocking: bool = False) -> None:
        self.errors.append((text, blocking))


def make_run(
    run_id: RunId,
    *,
    run_name: str | None = None,
    status: RunStatus = RunStatus.COMPLETED,
    run_mode: RunMode = RunMode.TASKS,
) -> BenchmarkRun:
    """Build a minimal ``BenchmarkRun`` for shell/footer tests."""
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=run_mode,
        status=status,
        total_tasks=1,
        completed_tasks=1 if status is RunStatus.COMPLETED else 0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def fake_gateway() -> FakeResultGateway:
    return FakeResultGateway()


@pytest.fixture
def result_collaborators(
    fake_event_bus: FakeEventBus, fake_gateway: FakeResultGateway
) -> ResultCollaborators:
    return ResultCollaborators(
        bus=fake_event_bus,
        gateway=fake_gateway,
        native_pickers=FakeNativePickers(),
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
        notifications=FakeNotificationService(),
        export_filenames=FakeExportFilenameHelper(),
    )
