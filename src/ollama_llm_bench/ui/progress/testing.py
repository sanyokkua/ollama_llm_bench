"""``FakeProgressGateway`` -- an in-memory test double for ``ui/progress/``'s
``ProgressGateway`` (STORY-058).

Mirrors ``ui/new_benchmark/testing.py``'s ``FakeNewBenchmarkGateway`` shape: no real
I/O, state held in plain dicts, every call recorded so a test can assert on it
without a real store.
"""

from ollama_llm_bench.backend.domain import BenchmarkResult, BenchmarkRun, RunId, SettingKey

__all__: list[str] = ["FakeProgressGateway"]


class FakeProgressGateway:
    """An in-memory ``ProgressGateway`` with externally settable state.

    Attributes:
        recorded_pause_run_calls: Count of ``pause_run()`` invocations.
        recorded_resume_run_calls: Count of ``resume_run()`` invocations.
        recorded_stop_run_reasons: Every ``reason`` passed to ``stop_run``, in
            call order.
        recorded_rename_run_calls: Every ``(run_id, name)`` pair passed to
            ``rename_run``, in call order.
        recorded_manual_provider_probe_calls: Count of
            ``manual_provider_probe()`` invocations.
    """

    def __init__(self) -> None:
        self._settings: dict[str, str] = {}
        self._runs: dict[RunId, BenchmarkRun] = {}
        self._headers: dict[RunId, BenchmarkRun] = {}
        self._task_counters: dict[RunId, tuple[BenchmarkResult, ...]] = {}
        self._past_logs: dict[RunId, str] = {}
        self._is_run_active = False
        self.recorded_pause_run_calls = 0
        self.recorded_resume_run_calls = 0
        self.recorded_stop_run_reasons: list[str | None] = []
        self.recorded_rename_run_calls: list[tuple[RunId, str | None]] = []
        self.recorded_manual_provider_probe_calls = 0

    def pause_run(self) -> None:
        self.recorded_pause_run_calls += 1

    def resume_run(self) -> None:
        self.recorded_resume_run_calls += 1

    def stop_run(self, reason: str | None = None) -> None:
        self.recorded_stop_run_reasons.append(reason)

    def run_metadata(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[run_id]

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        self.recorded_rename_run_calls.append((run_id, name))

    def run_header(self, run_id: RunId) -> BenchmarkRun:
        return self._headers[run_id]

    def task_counters(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._task_counters.get(run_id, ())

    def load_past_log(self, run_id: RunId) -> str:
        return self._past_logs.get(run_id, "")

    def get_setting(self, key: SettingKey) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        self._settings[key] = value

    def manual_provider_probe(self) -> None:
        self.recorded_manual_provider_probe_calls += 1

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return tuple(self._runs.values())

    def is_run_active(self) -> bool:
        return self._is_run_active

    def set_run(self, run: BenchmarkRun) -> None:
        """Test helper: seed ``run_metadata``/``list_runs`` for ``run.run_id``."""
        self._runs[run.run_id] = run

    def set_run_header(self, run: BenchmarkRun) -> None:
        """Test helper: seed ``run_header`` for ``run.run_id``."""
        self._headers[run.run_id] = run

    def set_task_counters(self, run_id: RunId, results: tuple[BenchmarkResult, ...]) -> None:
        """Test helper: seed ``task_counters`` for ``run_id``."""
        self._task_counters[run_id] = results

    def set_past_log(self, run_id: RunId, content: str) -> None:
        """Test helper: seed ``load_past_log`` for ``run_id``."""
        self._past_logs[run_id] = content

    def set_is_run_active(self, *, active: bool) -> None:
        """Test helper: force ``is_run_active()``'s return value."""
        self._is_run_active = active
