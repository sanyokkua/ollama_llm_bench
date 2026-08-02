# STORY-080 — Ordered Shutdown, WAL Checkpoint, and Crash-Recovery Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the application's quit and crash-recovery behavior: `AppHandle.shutdown()` grows
from performing 2 of the spec's 6 ordered shutdown steps to all 6 (via `__main__.py` calling it after
`app.exec()` returns); a crash-recovery sweep is wired at launch and at run-resume (today it exists but
is never called); the quit-confirmation dialog's "Save all" choice actually invokes a save hook instead
of silently discarding buffers; and the confirmed-quit path persists the active workspace, which today
is never written anywhere.

**Architecture:** No new modules, no new widgets. This is wiring work across five existing modules
(`ui/main_window/`, `backend/benchmark_pipeline/`, `backend/persistence/results/`,
`backend/infra/`, `adapters/qt_runnables/`) plus the two non-module files
`src/ollama_llm_bench/compose.py` and `src/ollama_llm_bench/__main__.py`. Every piece of logic this
story calls already exists and is already tested in isolation (`CloseHandler`'s confirmation sequence,
`ResultsStore.recover_in_flight_results()`, `BenchmarkFlowApi.shutdown()`, `QtTaskRunner.shutdown()`,
`InstanceLockHandle.release()`, `MainWindowGateway.set_active_workspace()`); this story's entire job is
calling them in the right place, in the right order, with the right test coverage. Three genuinely new
lines of code exist: `AppHandle` gains one field (`flow`), `AppHandle.shutdown()` grows five more lines,
and `CloseHandler` gains one constructor parameter.

**Tech Stack:** Python 3.13, PySide6 6.8, `msgspec`, `pytest`/`pytest-qt`, SQLite (stdlib `sqlite3`).

## Global Constraints

- `msgspec.Struct(frozen=True, kw_only=True, gc=False)` for `AppHandle` — already the case; do not
  change the struct's other flags when adding the new field.
- No `asyncio`/`anyio`/`qasync` anywhere (D-R-01) — nothing in this plan needs any of them.
- The `TaskRunner` backend Protocol (`backend/concurrency/protocols.py`) is **not** touched — do not add
  `shutdown()` to it. `QtTaskRunner.shutdown()` stays adapter-only by design (see its own docstring);
  Task 3 exports the concrete type instead of widening the shared Protocol.
- `compose.py`'s architecture test (STORY-077-AC-5) asserts a 50–500 line bound on the file — this
  story's compose.py-side diff is small (one new field, ~6 new lines in `shutdown()`, one new line
  calling the sweep); if `just arch-test` reports the file over budget after Task 4, that is a stop-and-report
  condition, not something to silently work around.
- Every `ruff`/`mypy --strict` issue in a file this story touches must be fixed before the story is done
  — "pre-existing" is not a valid excuse for a file this plan edits (per `CLAUDE.md`).
- A confirmed quit cancels with `CancelReason.USER_STOP`, never `APP_SHUTDOWN` — do not change this in
  `BenchmarkFlowApi.shutdown()`; `USER_STOP` is what makes the affected run persist `STOPPED` per
  `08-M_app_lifecycle.md` §7 step 2, which is required behavior.
- Every test function is fully annotated, returns `-> None`, follows Arrange-Act-Assert, and contains no
  `if`/`for` — use `@pytest.mark.parametrize` for tables of cases (`testing-standard-pyqt` skill,
  `testing.md` rule).
- Every mock is constructed with `spec=`; a `msgspec.Struct` DTO is never mocked, only constructed
  directly.
- Run `uv run ruff check --fix <file>` then `uv run ruff format <file>` (in that order) and
  `uv run mypy --strict <file>` after every task, before committing.

______________________________________________________________________

## File Structure

| File                                                                                           | Responsibility                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/ollama_llm_bench/adapters/qt_runnables/__init__.py` (modify)                              | Export `QtTaskRunner` from the package root alongside `make_qt_task_runner`                                                                                                                     |
| `src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py` (modify)              | `resume()` calls the full crash-recovery sweep instead of its own ad-hoc partial reset                                                                                                          |
| `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py` (create) | Proves STORY-080-AC-8                                                                                                                                                                           |
| `src/ollama_llm_bench/ui/main_window/_internal/close_handler.py` (modify)                      | `CloseHandler` gains a `save_all_buffers` hook, invoked on the "Save all" choice                                                                                                                |
| `src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py` (modify)           | Extends the existing STORY-053 tests to prove STORY-080-AC-1/AC-2                                                                                                                               |
| `src/ollama_llm_bench/compose.py` (modify)                                                     | `AppHandle` gains a `flow` field and a concretely-typed `task_runner`; `shutdown()` grows to all 5 steps it owns; `build_app` calls the crash-recovery sweep once, right after the schema check |
| `tests/integration/test_compose_build_app.py` (modify)                                         | Updates the existing STORY-077 `AppHandle` field-set assertion and the shared `_shutdown()` test helper for the new field                                                                       |
| `src/ollama_llm_bench/__main__.py` (modify)                                                    | `main()` captures the `app.exec()` exit code, calls `handle.shutdown(timeout_ms=...)`, then exits with that code; the crash hook's `_quit()` passes the same timeout                            |
| `src/ollama_llm_bench/ui/main_window/api.py` (modify)                                          | `_on_confirmed_quit` also persists `ui.active_workspace`                                                                                                                                        |
| `tests/integration/test_launch_crash_recovery.py` (create)                                     | Proves STORY-080-AC-5                                                                                                                                                                           |
| `tests/integration/test_quit_sequence.py` (create)                                             | Proves STORY-080-AC-3, AC-4, AC-6, AC-7                                                                                                                                                         |

______________________________________________________________________

## Task 1: Replace `resume()`'s ad-hoc partial reset with the full crash-recovery sweep

**Files:**

- Modify: `src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py:441-477`
- Test: `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py`

**Interfaces:**

- Consumes: `ResultsStore.recover_in_flight_results(self) -> int` (already exists,
  `backend/persistence/results/protocols.py:81`, already implemented and unit-tested by STORY-011).

- Produces: nothing new — `resume(self, run_id: RunId) -> None`'s signature is unchanged.

- [ ] **Step 1: Write the failing test**

Create `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py`:

```python
"""Proves: STORY-080-AC-8"""

import time

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    STABILITY_SETTING_ENTRIES,
    make_task,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkResultTerm,
    BenchmarkRun,
    BenchmarkRunSettingEntry,
    ResultStatus,
    ResultTermKind,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_RUN_ID = 1
_WAIT_TIMEOUT_S = 2.0
_POLL_INTERVAL_S = 0.01
_IN_FLIGHT_STATUSES = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)


def _wait_until_idle(pipeline: BenchmarkFlowApi, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` until the dispatcher settles (mirrors `test_resume.py`'s helper)."""
    deadline = time.monotonic() + timeout_s
    while pipeline.is_running() and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
    assert not pipeline.is_running(), "pipeline did not settle within the timeout"


def _make_in_flight_result(*, result_id: int, task_id: str, status: ResultStatus) -> BenchmarkResult:
    """A minimal in-flight `BenchmarkResult` carrying one child term row, so the
    sweep's child-row-deletion is observable (mirrors
    `tests/integration/persistence/test_crash_recovery_sweep.py`'s `_make_result`)."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=_RUN_ID,
        task_id=task_id,
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Local Ollama",
        model_name="llama3",
        status=status,
        sanitized_response="in-flight response",
        created_at="2026-01-01T00:00:00+00:00",
        terms=(
            BenchmarkResultTerm(term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="x"),
        ),
    )


def _make_stopped_run() -> BenchmarkRun:
    """A minimal `STOPPED` run carrying every required settings-snapshot key
    (mirrors `test_resume.py`'s own `_make_stopped_run` — duplicated here since
    colocated test files are self-contained per `testing-standard-pyqt`)."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.STOPPED,
        total_tasks=len(_IN_FLIGHT_STATUSES),
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        settings_snapshot=(
            BenchmarkRunSettingEntry(setting_key="eval.sanity_min_chars", setting_value="1"),
            BenchmarkRunSettingEntry(setting_key="eval.sanity_error_markers", setting_value=""),
            BenchmarkRunSettingEntry(
                setting_key="eval.keyword_semantic_pass_threshold", setting_value="0.8"
            ),
            BenchmarkRunSettingEntry(
                setting_key="eval.judge_max_completion_tokens", setting_value="512"
            ),
            BenchmarkRunSettingEntry(setting_key="eval.judge_max_parse_retries", setting_value="2"),
            BenchmarkRunSettingEntry(
                setting_key="eval.force_judge_on_prior_failure", setting_value="false"
            ),
            *STABILITY_SETTING_ENTRIES,
        ),
    )


def _make_pipeline(  # noqa: PLR0913  # every fixture is a distinct required collaborator
    *,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> BenchmarkFlowApi:
    return make_benchmark_pipeline(
        results_store=fake_results_store,
        runs_store=fake_runs_store,
        tasks_store=fake_tasks_store,
        inference_activity_store=fake_inference_activity_store,
        task_runner=inline_task_runner,  # type: ignore[arg-type]  # fixture is TaskRunner[ResultPatch]
        run_dispatcher=inline_run_dispatcher,  # type: ignore[arg-type]  # fixture is RunDispatcher
        bus=fake_event_bus,  # type: ignore[arg-type]  # fixture satisfies EventBus structurally
        clock=fake_clock,
        embedding_service=fake_embedding_service,
        provider_registry=fake_provider_registry,
        settings_service=fake_settings_service,
        run_snapshot_builder=fake_run_snapshot_builder,
    )


def test_resume_sweeps_in_flight_rows_before_dispatch(  # noqa: PLR0913  # every fixture is a
    # distinct required collaborator
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-080-AC-8

    Given result rows in each of the four non-terminal in-flight statuses, each
    carrying a child term row, when `resume(run_id)` is called, then the
    crash-recovery sweep has reset every one of the four rows to `PENDING` and
    deleted their child rows before `list_results` is read to compute the
    resumable set — replacing the old behaviour that only reset
    `RUNNING_INFERENCE` rows and never deleted any child row.
    """
    # Arrange
    rows = tuple(
        _make_in_flight_result(result_id=i + 1, task_id=f"task-{i + 1}", status=status)
        for i, status in enumerate(_IN_FLIGHT_STATUSES)
    )
    fake_results_store.create_results(rows)
    fake_runs_store.get_run.return_value = _make_stopped_run()  # type: ignore[attr-defined]
    fake_tasks_store.list_tasks.return_value = tuple(  # type: ignore[attr-defined]
        make_task(task_id=f"task-{i + 1}") for i in range(len(_IN_FLIGHT_STATUSES))
    )
    fake_provider_registry.get_client.side_effect = ConfigurationError(  # type: ignore[attr-defined]
        message="no client configured for this test"
    )
    list_results_spy = mocker.spy(fake_results_store, "list_results")
    recover_spy = mocker.spy(fake_results_store, "recover_in_flight_results")
    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    # Act
    pipeline.resume(_RUN_ID)

    # Assert — the sweep ran, and by the time `list_results` was read
    # (synchronously, before `submit()` hands off to the dispatcher thread),
    # every one of the four originally in-flight rows was already PENDING with
    # its child rows cleared.
    recover_spy.assert_called_once()
    swept_snapshot = list_results_spy.spy_return
    assert {row.result_id: row.status for row in swept_snapshot} == dict.fromkeys(
        range(1, len(_IN_FLIGHT_STATUSES) + 1), ResultStatus.PENDING
    )
    assert all(row.terms == () for row in swept_snapshot)

    # Cleanup — let the dispatcher settle (each row fails fast with no client).
    _wait_until_idle(pipeline)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py -v`
Expected: FAIL — the assertion on `swept_snapshot` statuses fails because today only
`RUNNING_INFERENCE` (result 1) is reset to `PENDING`; results 2–4 (the three
`AWAITING_*_CHECK` statuses) are still in their original status, and `recover_in_flight_results`
was never called (`recover_spy.assert_called_once()` fails first).

- [ ] **Step 3: Replace the ad-hoc reset with the full sweep**

In `src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py`, replace the `resume`
method (current lines 441–477):

```python
    def resume(self, run_id: RunId) -> None:
        """Resume a `STOPPED`/`FAILED` run's unfinished rows (STORY-029-AC-6, STORY-080-AC-8).

        Admits under the single-inference gate first, exactly like `start`
        (SPEC-036, DD-50); a held gate makes this call a silent no-op. Runs the
        crash-recovery sweep (`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §9)
        before reading any result row, so a row left mid-flight by a previous
        crash — in any of the four non-terminal in-flight statuses, not only
        `RUNNING_INFERENCE` — is reset to `PENDING` with its child rows deleted
        before the resumable set is computed. The run's already-persisted
        `settings_snapshot`/model/provider entries are reused verbatim — this
        method never re-resolves live settings.
        """
        context = InferenceActivityContext(
            activity=InferenceActivity.BENCHMARK_RUN, started_at=self._clock.monotonic_ms()
        )
        lease = self._inference_activity_store.try_acquire(InferenceActivity.BENCHMARK_RUN, context)
        if lease is None:
            return
        run = self._runs_store.get_run(run_id)
        self._results_store.recover_in_flight_results()
        # `list_resumable_results` selects PENDING + retryable-failure rows
        # (its own docstring) — this call confirms that set per AC-6; the
        # actual re-run selection is `run_all_phases`' own per-phase
        # eligibility filter over `list_results`, which is why the return
        # value itself is not threaded further here.
        self._results_store.list_resumable_results(run_id)
        current_rows = self._results_store.list_results(run_id)
        token = make_cancellation_token(clock=self._clock)
        with self._lock:
            self._token = token
            self._current_run = run
            self._is_running = True
        self._run_dispatcher.submit(lambda: self._dispatch_run(run=run, lease=lease, token=token))
        self._emit_run_resumed(run, current_rows=current_rows)
```

This removes the `stuck_ids = tuple(...)`/`if stuck_ids: self._results_store.reset_results(stuck_ids)`
block entirely — `recover_in_flight_results()` supersedes it. If `ResultStatus` becomes an unused
import in this file after this edit, `ruff` (F401) will flag it; remove the import only if flagged —
do not remove it speculatively, since the file may use `ResultStatus` elsewhere (e.g. in
`_halt_outcome`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing STORY-029 resume suite to confirm no regression**

Run: `uv run pytest src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume.py -v`
Expected: PASS — `test_resume_selects_resumable_rows_and_reuses_snapshot` and
`test_resume_with_gate_already_held_is_a_no_op` both still pass; the first test's
`RUNNING_INFERENCE` row is still swept (now via the fuller sweep instead of the old targeted reset),
and its `COMPLETED` row is still untouched (the sweep only ever touches the four in-flight statuses).

- [ ] **Step 6: Lint and typecheck**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py
uv run ruff format src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py
uv run mypy --strict src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/backend/benchmark_pipeline/_internal/lifecycle.py src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py
git commit -m "fix(benchmark-pipeline): resume() runs the full crash-recovery sweep (STORY-080-AC-8)"
```

______________________________________________________________________

## Task 2: `CloseHandler` gains a `save_all_buffers` hook

**Files:**

- Modify: `src/ollama_llm_bench/ui/main_window/_internal/close_handler.py:44-165`
- Modify: `src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py`

**Interfaces:**

- Consumes: nothing new.

- Produces: `CloseHandler.__init__(..., save_all_buffers: Callable[[], None] = lambda: None, ...)` —
  later tasks (Task 6, `ui/main_window/api.py`) may pass a real callable here; until STORY-114 lands,
  no production caller does, mirroring how `dirty_buffer_count`'s real hook is also undelivered yet.

- [ ] **Step 1: Write the failing test**

In `src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py`, replace the existing
`test_quit_with_running_run_and_dirty_buffers_confirms_in_order` parametrize table and body with a
version that also asserts the save-all hook (this both extends STORY-053-AC-6 coverage and proves
STORY-080-AC-1/AC-2):

```python
@pytest.mark.parametrize(
    (
        "running_confirm_result",
        "buffers_confirm_result",
        "expected_call_order",
        "expected_quit_calls",
        "expected_save_all_calls",
    ),
    [
        (False, "save_all", ["confirm_running_benchmark_quit"], 0, 0),
        (True, "cancel", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 0, 0),
        (True, "discard_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 0),
        (True, "save_all", ["confirm_running_benchmark_quit", "confirm_unsaved_buffers"], 1, 1),
    ],
    ids=[
        "cancel_at_running_prompt",
        "cancel_at_buffers_prompt",
        "confirm_discard_all_quits_without_saving",
        "confirm_save_all_saves_then_quits",
    ],
)
def test_quit_with_running_run_and_dirty_buffers_confirms_in_order(  # noqa: PLR0913  # five
    # parametrize axes plus four independently-overridable fixtures
    running_confirm_result: bool,  # noqa: FBT001  # parametrize tuple element
    buffers_confirm_result: str,
    expected_call_order: list[str],
    expected_quit_calls: int,
    expected_save_all_calls: int,
    gateway: FakeMainWindowGateway,
    event_bus: FakeEventBus,
    notifications: FakeNotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-053-AC-6, STORY-080-AC-1, STORY-080-AC-2 (EC-M-6, EC-M-7)

    Given both a non-terminal run and one or more dirty task buffers,
    when the user requests a quit,
    then the running-benchmark confirmation is shown before the unsaved-buffer confirmation,
    a cancel at either step aborts the entire quit (EC-WS-2, EC-M-7),
    and choosing "Save all" invokes the save-all hook exactly once before the quit proceeds,
    while "Discard all" never invokes it.
    """
    # Arrange
    gateway.set_run_active(True)
    call_order: list[str] = []

    def _confirm_running() -> bool:
        call_order.append("confirm_running_benchmark_quit")
        return running_confirm_result

    def _confirm_buffers(_self: CloseHandler) -> str:
        call_order.append("confirm_unsaved_buffers")
        return buffers_confirm_result

    monkeypatch.setattr(
        CloseHandler, "_confirm_running_benchmark_quit", staticmethod(_confirm_running)
    )
    monkeypatch.setattr(CloseHandler, "_confirm_unsaved_buffers", _confirm_buffers)
    confirmed_quit_calls: list[None] = []
    save_all_calls: list[None] = []
    close_handler = CloseHandler(
        gateway=gateway,
        event_bus=event_bus,
        notifications=notifications,
        dirty_buffer_count=lambda: 3,
        save_all_buffers=lambda: save_all_calls.append(None),
        on_confirmed_quit=lambda: confirmed_quit_calls.append(None),
        shutdown_timeout_ms=80,
    )

    # Act
    close_handler.request_close()
    event_bus.emit(SIGNAL_RUN_STOPPED, _make_run_stopped_event())

    # Assert
    assert call_order == expected_call_order
    assert len(confirmed_quit_calls) == expected_quit_calls
    assert len(save_all_calls) == expected_save_all_calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py -v`
Expected: FAIL — `CloseHandler.__init__()` raises `TypeError: unexpected keyword argument 'save_all_buffers'`.

- [ ] **Step 3: Add the `save_all_buffers` hook**

In `src/ollama_llm_bench/ui/main_window/_internal/close_handler.py`, modify `__init__` (lines 47–82) to
add the new parameter, defaulted like `dirty_buffer_count`:

```python
    def __init__(  # noqa: PLR0913  # seven distinct required collaborators per the
        # approved STORY-053/STORY-080 design (docs/stories/story-053-main-window-shell.md,
        # docs/stories/story-080-quit-sequence-and-crash-recovery.md); each is an
        # independently-faked test seam, not groupable into one struct without losing that
        self,
        *,
        gateway: MainWindowGateway,
        event_bus: EventBus,
        notifications: NotificationService,
        dirty_buffer_count: Callable[[], int] = lambda: 0,
        save_all_buffers: Callable[[], None] = lambda: None,
        on_confirmed_quit: Callable[[], None],
        shutdown_timeout_ms: int = _DEFAULT_SHUTDOWN_TIMEOUT_MS,
    ) -> None:
        """Store the collaborators the quit sequence coordinates.

        Args:
            gateway: Supplies ``is_run_active()`` (the quit decision) and
                ``shutdown(timeout_ms)`` (the graceful pipeline stop).
            event_bus: The bus the bounded shutdown wait subscribes
                ``_run_stopped`` on.
            notifications: Retained for parity with the controller's collaborator set;
                this handler itself raises no notification.
            dirty_buffer_count: Returns the Task Editor's current dirty-buffer count.
                Defaults to always-zero because the Task Editor does not exist yet
                (STORY-114 wires the real hook) -- additive, not a signature change a
                caller must adapt to.
            save_all_buffers: Invoked exactly once, before the quit proceeds, when the
                user chooses "Save all" at the unsaved-buffers prompt. Defaults to a
                no-op for the same reason ``dirty_buffer_count`` defaults to zero --
                STORY-114 wires the real per-file save behind this hook.
            on_confirmed_quit: Invoked once every confirmation has resolved toward
                quitting.
            shutdown_timeout_ms: The bound on the wait for ``_run_stopped`` after a
                confirmed running-benchmark quit.
        """
        self._gateway = gateway
        self._event_bus = event_bus
        self._notifications = notifications
        self._dirty_buffer_count = dirty_buffer_count
        self._save_all_buffers = save_all_buffers
        self._on_confirmed_quit = on_confirmed_quit
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._quit_settled = False
        self._subscription: Subscription | None = None
        self._timer: QTimer | None = None
```

Then modify `_proceed_to_buffer_check` (current lines 129–137) to distinguish `"save_all"` from
`"discard_all"` instead of falling through identically:

```python
    def _proceed_to_buffer_check(self) -> None:
        if self._dirty_buffer_count() > 0:
            logger.debug("quit_requested_with_dirty_buffers")
            outcome = self._confirm_unsaved_buffers()
            if outcome == "cancel":
                logger.debug("quit_cancelled_at_unsaved_buffers_prompt")
                return
            if outcome == "save_all":
                logger.debug("quit_saving_all_buffers")
                self._save_all_buffers()
        logger.debug("quit_confirmed")
        self._on_confirmed_quit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py -v`
Expected: PASS — all 4 parametrized cases plus `test_quit_with_running_run_confirms_and_shuts_down`'s
2 cases.

- [ ] **Step 5: Lint and typecheck**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/ui/main_window/_internal/close_handler.py src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py
uv run ruff format src/ollama_llm_bench/ui/main_window/_internal/close_handler.py src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py
uv run mypy --strict src/ollama_llm_bench/ui/main_window/_internal/close_handler.py src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py
```

Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/ui/main_window/_internal/close_handler.py src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py
git commit -m "fix(main-window): CloseHandler invokes save_all_buffers on the Save-all quit choice (STORY-080-AC-1, AC-2)"
```

______________________________________________________________________

## Task 3: Export `QtTaskRunner` from `adapters/qt_runnables`'s public surface

**Files:**

- Modify: `src/ollama_llm_bench/adapters/qt_runnables/__init__.py`

**Interfaces:**

- Consumes: nothing new.

- Produces: `from ollama_llm_bench.adapters.qt_runnables import QtTaskRunner` — Task 4 imports this to
  type `AppHandle.task_runner` concretely, so `AppHandle.shutdown()` can call
  `self.task_runner.shutdown()` (a method `QtTaskRunner` has and the backend `TaskRunner` Protocol
  deliberately does not — see that method's own docstring: "Not part of the `TaskRunner` Protocol...
  Called once by the composition root during application shutdown").

- [ ] **Step 1: Write the failing test**

Add to `tests/architecture/` — check first whether a test file already asserts
`adapters/qt_runnables/`'s public surface (search: `grep -rl "qt_runnables" tests/architecture/`); if
one exists, add a case there. Otherwise create
`tests/integration/test_qt_runnables.py`'s existing suite is the closest fit — add this case to that
existing file instead of creating a new one (check its current content first: `cat tests/integration/test_qt_runnables.py`). Add:

```python
def test_qt_task_runner_is_importable_from_the_package_root() -> None:
    """Proves: STORY-080 (foundation for AC-6)

    `QtTaskRunner` is re-exported from `adapters.qt_runnables`'s public surface
    (not only its `.api`), so `compose.py` can import it via the package root
    per the module public-surface convention, and it exposes `shutdown()` for
    the composition root's ordered-shutdown pool drain.
    """
    from ollama_llm_bench.adapters.qt_runnables import QtTaskRunner  # noqa: PLC0415  # proving root import

    runner: QtTaskRunner[object] = QtTaskRunner()
    assert hasattr(runner, "shutdown")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qt_runnables.py -k qt_task_runner_is_importable -v`
Expected: FAIL — `ImportError: cannot import name 'QtTaskRunner' from 'ollama_llm_bench.adapters.qt_runnables'`.

- [ ] **Step 3: Export `QtTaskRunner`**

Modify `src/ollama_llm_bench/adapters/qt_runnables/__init__.py`:

```python
"""Qt-backed ``TaskRunner`` adapter — schedules backend work on a ``QThreadPool``."""

from ollama_llm_bench.adapters.qt_runnables.api import QtTaskRunner, make_qt_task_runner

__all__: list[str] = ["QtTaskRunner", "make_qt_task_runner"]
```

`api.py` already imports `QtTaskRunner` from `_internal/task_runner.py` (confirmed:
`src/ollama_llm_bench/adapters/qt_runnables/api.py:11`) but does not currently list it in its own
`__all__` (confirmed: `api.py:14` is `__all__: list[str] = ["make_qt_task_runner"]`). Add it there too:

```python
__all__: list[str] = ["QtTaskRunner", "make_qt_task_runner"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_qt_runnables.py -k qt_task_runner_is_importable -v`
Expected: PASS

- [ ] **Step 5: Lint, typecheck, and import-linter**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/adapters/qt_runnables/__init__.py src/ollama_llm_bench/adapters/qt_runnables/api.py
uv run ruff format src/ollama_llm_bench/adapters/qt_runnables/__init__.py src/ollama_llm_bench/adapters/qt_runnables/api.py
uv run mypy --strict src/ollama_llm_bench/adapters/qt_runnables/
uv run lint-imports
```

Expected: no findings — exporting a class that already exists on `api.py`'s own surface does not cross
any import-linter boundary.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/adapters/qt_runnables/__init__.py tests/integration/test_qt_runnables.py
git commit -m "feat(qt-runnables): export QtTaskRunner from the package root (STORY-080)"
```

______________________________________________________________________

## Task 4: Extend `AppHandle` to the full 5-step shutdown and wire the launch-time crash-recovery sweep

**Files:**

- Modify: `src/ollama_llm_bench/compose.py:172-189` (the `AppHandle` class) and around line 358–381
  (`build_app`, right after the schema check)
- Modify: `tests/integration/test_compose_build_app.py` (update the existing STORY-077 field-set
  assertion and shared `_shutdown()` helper)
- Test (new file): `tests/integration/test_launch_crash_recovery.py`

**Interfaces:**

- Consumes: `QtTaskRunner[object].shutdown(self) -> None` (Task 3); `InstanceLockHandle.release(self) -> None` (already exists, `backend/infra/protocols.py:62`); `QtBenchmarkFlow.shutdown(self, timeout_ms: int) -> None` (already exists, `adapters/qt_benchmark_flow/_internal/facade.py:61`);
  `ResultsStore.recover_in_flight_results(self) -> int` (already exists, used by Task 1 too).
- Produces: `AppHandle.shutdown(self, *, timeout_ms: int) -> None` (signature changes from no-arg to
  keyword-only `timeout_ms`) — Task 5 (`__main__.py`) is the only other caller and is updated in this
  same plan.

### Part A — the crash-recovery sweep at launch

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_launch_crash_recovery.py`:

```python
"""Integration test for the launch-time crash-recovery sweep (STORY-080-AC-5)."""

from pathlib import Path
import functools

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkResultTerm,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    ResultStatus,
    ResultTermKind,
    RunMode,
    RunStatus,
    TaskOrigin,
)
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_IN_FLIGHT_STATUSES = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _shutdown(handle: AppHandle) -> None:
    handle.window.close()
    handle.shutdown(timeout_ms=2000)


def test_incomplete_run_left_for_resume_and_in_flight_rows_reset_to_pending(
    isolated_home: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-5 (EC-M-4)

    Given a database holding a run persisted `INCOMPLETE` whose result rows
    include one row in each of the four non-terminal in-flight statuses, each
    with child term rows, when the application launches, then the run's
    persisted status is still `INCOMPLETE`, every one of those four rows is
    `PENDING` with its child rows deleted, and the one terminal row is
    byte-for-byte unchanged.
    """
    # Arrange — seed the database directly, at the exact path build_app will open.
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    read_conn_factory = functools.partial(open_read_connection, db_path)
    runs_store = create_runs_store(write_conn, lock, read_conn_factory)
    run_id = runs_store.create_run(
        BenchmarkRun(
            run_id=-1,
            run_name="crashed-run",
            timestamp="2026-01-01T00:00:00+00:00",
            run_mode=RunMode.TASKS,
            status=RunStatus.INCOMPLETE,
            total_tasks=5,
            completed_tasks=1,
            total_elapsed_ms=0,
            schema_version=1,
            created_at="2026-01-01T00:00:00+00:00",
            models=(
                BenchmarkRunModelEntry(
                    role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name="llama3"
                ),
            ),
        )
    )
    tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
    task_ids = [f"task-{i}" for i in range(len(_IN_FLIGHT_STATUSES) + 1)]
    tasks_store.create_tasks(
        run_id,
        tuple(
            BenchmarkTask(task_id=t, task_origin=TaskOrigin.FILE, question="q") for t in task_ids
        ),
    )
    results_store = create_results_store(write_conn, lock, read_conn_factory)
    in_flight_rows = tuple(
        BenchmarkResult(
            result_id=-1,
            run_id=run_id,
            task_id=task_ids[i],
            provider_id=_TEST_PROVIDER_ID,
            provider_name="Local Ollama",
            model_name="llama3",
            status=status,
            sanitized_response="in-flight response",
            created_at="2026-01-01T00:00:00+00:00",
            terms=(
                BenchmarkResultTerm(term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="x"),
            ),
        )
        for i, status in enumerate(_IN_FLIGHT_STATUSES)
    )
    terminal_row = BenchmarkResult(
        result_id=-1,
        run_id=run_id,
        task_id=task_ids[-1],
        provider_id=_TEST_PROVIDER_ID,
        provider_name="Local Ollama",
        model_name="llama3",
        status=ResultStatus.COMPLETED,
        sanitized_response="a completed answer",
        created_at="2026-01-01T00:00:00+00:00",
    )
    results_store.create_results((*in_flight_rows, terminal_row))
    before_by_task = {r.task_id: r for r in results_store.list_results(run_id)}
    terminal_before = before_by_task[task_ids[-1]]
    write_conn.close()

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())
    try:
        after_write_conn, after_lock = open_write_connection(db_path)
        after_read_conn = functools.partial(open_read_connection, db_path)
        after_runs_store = create_runs_store(after_write_conn, after_lock, after_read_conn)
        after_results_store = create_results_store(after_write_conn, after_lock, after_read_conn)

        # Assert
        assert after_runs_store.get_run(run_id).status is RunStatus.INCOMPLETE
        after_by_task = {r.task_id: r for r in after_results_store.list_results(run_id)}
        for task_id in task_ids[: len(_IN_FLIGHT_STATUSES)]:
            swept = after_by_task[task_id]
            assert swept.status is ResultStatus.PENDING
            assert swept.terms == ()
            assert swept.sanitized_response is None
        terminal_after = after_by_task[task_ids[-1]]
        assert terminal_after == terminal_before
        after_write_conn.close()
    finally:
        _shutdown(handle)
```

Note: this test does **not** use the `seeded_app_data_root`/`isolated_home` fixtures already defined in
`tests/integration/test_compose_build_app.py` because those are module-private fixtures in that file;
this new file defines its own minimal `isolated_home`, matching the pattern already used identically in
`tests/integration/test_launch_instance_lock.py` and `tests/integration/test_launch_seeding.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_launch_crash_recovery.py -v`
Expected: FAIL — the four in-flight rows are still in their original (non-`PENDING`) status with their
term rows intact, because nothing in `build_app` calls `recover_in_flight_results()` yet.

- [ ] **Step 3: Wire the sweep into `build_app`**

In `src/ollama_llm_bench/compose.py`, immediately after the schema check (current lines 364–370) and
before store construction, insert the sweep call. The results store must exist first, so move the
sweep call to immediately after `res = create_results_store(write_conn, lock, read_conn)` (current
line ~375), which is still well before default seeding (`if not provs.list_providers(): seed_builtin_providers(...)`, current line ~380) — this preserves ADR-0010 settlement 1's ordering
("crash-recovery sweep... between [schema check] and [default seeding]"):

```python
    read_conn = functools.partial(open_read_connection, app_data_root / DB_FILENAME)
    runs = create_runs_store(write_conn, lock, read_conn)
    tasks = create_tasks_store(write_conn, lock, read_conn)
    res = create_results_store(write_conn, lock, read_conn)
    res.recover_in_flight_results()
    provs = create_providers_store(write_conn, lock, read_conn)
    caps = create_model_capabilities_store(write_conn, lock, read_conn)
    appset = create_app_settings_store(write_conn, lock, read_conn, clock)

    if not provs.list_providers():
        seed_builtin_providers(write_conn, lock)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_launch_crash_recovery.py -v`
Expected: PASS

### Part B — `AppHandle`'s ordered shutdown, steps 1–5

- [ ] **Step 5: Update the existing STORY-077 `AppHandle` field-set test (expected to fail first)**

In `tests/integration/test_compose_build_app.py`, update
`test_build_app_returns_frozen_app_handle_with_window_and_shutdown` (lines 175–213): change the
expected field set (lines 193–202) to include the new `flow` field:

```python
    handle_fields = set(AppHandle.__struct_fields__)
    assert handle_fields == {
        "window",
        "write_conn",
        "write_lock",
        "task_runner",
        "run_dispatcher",
        "http_client",
        "instance_lock",
        "loop",
        "flow",
    }
```

Also update the module-level `_shutdown()` helper (lines 139–153) — it currently manually replicates
steps 2–4 before this story existed; now that `AppHandle.shutdown()` performs the full ordered
sequence (and takes `timeout_ms`), replace the whole body:

```python
def _shutdown(handle: AppHandle) -> None:
    """Release the real dispatcher thread, HTTP client, write connection, and instance
    lock a test's `build_app` call constructed, so no test leaks a live thread or a
    held lock into the next one.

    Closes the window *first* — the shell's real close sequence (`CloseHandler` ->
    `_on_confirmed_quit` -> a pending-geometry flush) needs a live database. Closing
    it here, once, up front makes `pytestqt`'s own automatic end-of-test
    `_close_widgets()` call a harmless no-op afterwards (the shell is already
    `_quitting`, so a second `closeEvent` short-circuits before touching the database
    again). `AppHandle.shutdown()` now performs the full 5-step ordered shutdown
    (STORY-080) in one call.
    """
    handle.window.close()
    handle.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)
```

This same `_shutdown()` helper is called from every other test in this file (lines 172, 243, 321, 360,
397, 458, 506) — no other call site needs to change since they all just call `_shutdown(handle)`.

`tests/integration/test_launch_seeding.py` and `tests/integration/test_launch_instance_lock.py` each
define their **own** private, near-identical `_shutdown`/inline teardown — check whether either needs
the same update:

- `test_launch_seeding.py`'s `_shutdown` (lines 28–31) manually does
  `window.close()`/`run_dispatcher.shutdown(2000)`/`http_client.close()`/`write_conn.close()` — this
  still works today (each step is still individually valid), but leaves the instance lock unreleased
  across that file's tests. Leave it as-is for this story (out of scope — `test_launch_seeding.py` is a
  STORY-078 file, and its tests don't depend on the lock being released); do not touch this file unless
  `just test` reports a cross-test lock contention failure after this story's changes, in which case
  update it the same way as `test_compose_build_app.py`'s `_shutdown` above and note the change in the
  story's implementation notes.
- `test_launch_instance_lock.py` never calls `build_app` successfully (both its tests assert
  `SystemExit`), so it has no `AppHandle` to tear down — no change needed.

Run: `uv run pytest tests/integration/test_compose_build_app.py -v`
Expected: FAIL at this point — `AppHandle.__struct_fields__` does not yet include `"flow"`, and
`handle.shutdown(timeout_ms=...)` does not yet accept that keyword argument.

- [ ] **Step 6: Write the new ordered-shutdown integration test (AC-4, AC-6, AC-7)**

Create `tests/integration/test_quit_sequence.py` (this task writes AC-4/AC-6/AC-7 into it now; Task 6
adds the AC-3 test to this same file):

```python
"""Integration tests for the ordered shutdown sequence (STORY-080-AC-4, AC-6, AC-7)."""

from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.infra import (
    InstanceLockOutcome,
    acquire_instance_lock,
    make_system_clock,
)
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

_SHUTDOWN_TIMEOUT_MS = 2000


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def seeded_app_data_root(isolated_home: Path) -> Path:
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    seed_builtin_providers(write_conn, lock)
    write_conn.close()
    return app_data_root


def test_quit_closes_db_with_wal_checkpoint_truncate(
    seeded_app_data_root: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-4

    Given the application is quitting, when `AppHandle.shutdown()` runs, then
    `PRAGMA wal_checkpoint(TRUNCATE)` runs on the write connection before it
    is closed, and the database's `-wal` file is reclaimed (zero-length or
    absent) once shutdown returns.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    wal_path = seeded_app_data_root / f"{DB_FILENAME}-wal"

    # Act
    handle.window.close()
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    assert not wal_path.exists() or wal_path.stat().st_size == 0


def test_ordered_shutdown_runs_all_six_steps_in_order(
    seeded_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-080-AC-6

    Given the application is quitting, when the ordered shutdown runs, then
    these six actions are each performed exactly once, in exactly this order:
    hard-cancel, dispatcher-join-then-pool-drain, HTTP-client close,
    checkpoint-then-close the write connection, instance-lock release, process
    exit (the sixth step, process exit, is `__main__.py`'s responsibility per
    the story's design constraints — not exercised here, since this test calls
    `AppHandle.shutdown()` directly, not `main()`).
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.close()
    call_order: list[str] = []
    mocker.patch.object(
        handle.flow, "shutdown", side_effect=lambda timeout_ms: call_order.append("flow_shutdown")  # noqa: ARG005
    )
    mocker.patch.object(
        handle.task_runner, "shutdown", side_effect=lambda: call_order.append("task_runner_shutdown")
    )
    mocker.patch.object(
        handle.http_client, "close", side_effect=lambda: call_order.append("http_client_close")
    )
    real_execute = handle.write_conn.execute

    def _record_checkpoint(sql: str, *args: object) -> object:
        if "wal_checkpoint" in sql:
            call_order.append("db_checkpoint")
        return real_execute(sql, *args)

    mocker.patch.object(handle.write_conn, "execute", side_effect=_record_checkpoint)
    mocker.patch.object(
        handle.write_conn, "close", side_effect=lambda: call_order.append("db_close")
    )
    mocker.patch.object(
        handle.instance_lock, "release", side_effect=lambda: call_order.append("instance_lock_release")
    )

    # Act
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    assert call_order == [
        "flow_shutdown",
        "task_runner_shutdown",
        "http_client_close",
        "db_checkpoint",
        "db_close",
        "instance_lock_release",
    ]


def test_instance_lock_is_reacquirable_after_clean_quit(
    seeded_app_data_root: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-7

    Given the application has quit through the ordered shutdown, when a
    second process acquires the single-instance lock against the same
    application data directory, then acquisition succeeds immediately
    without needing the stale-owner reclaim path.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.close()

    # Act
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)
    reacquired = acquire_instance_lock(app_data_root=seeded_app_data_root, clock=make_system_clock())

    # Assert
    try:
        assert reacquired.outcome is InstanceLockOutcome.ACQUIRED
        assert reacquired.lock is not None
    finally:
        if reacquired.lock is not None:
            reacquired.lock.release()
```

- [ ] **Step 7: Run the new tests to verify they fail**

Run: `uv run pytest tests/integration/test_quit_sequence.py -v`
Expected: FAIL — `AppHandle.shutdown()` does not yet accept `timeout_ms`, does not yet touch
`handle.flow` (the field doesn't exist), and does not yet call `task_runner.shutdown()` or
`instance_lock.release()`.

- [ ] **Step 8: Extend `AppHandle` and `build_app`**

In `src/ollama_llm_bench/compose.py`, first update the imports (near the top, alongside the existing
`from ollama_llm_bench.adapters.qt_runnables import make_qt_task_runner` line — replace it):

```python
from ollama_llm_bench.adapters.qt_runnables import QtTaskRunner, make_qt_task_runner
```

Also change the import of `TaskRunner` — it is currently imported from
`ollama_llm_bench.backend.concurrency` alongside `CancellationToken, RunDispatcher` (line 56); leave
that import as-is (still needed elsewhere in the file for other type positions if any — check with
`grep -n "TaskRunner" src/ollama_llm_bench/compose.py` before removing it; if `TaskRunner` becomes
unused after this task's field-type change, `ruff` F401 will flag it and it should be removed then, not
speculatively).

Also add, near the top-level imports:

```python
from ollama_llm_bench.adapters.qt_benchmark_flow import QtBenchmarkFlow
```

(`QtBenchmarkFlow` must be checked for export from `adapters/qt_benchmark_flow`'s `__init__.py` the same
way Task 3 checked `QtTaskRunner` — confirmed already exported: `adapters/qt_benchmark_flow/__init__.py`
lists `"QtBenchmarkFlow"` in its `__all__`, so no equivalent Task 3-style export fix is needed here.)

Then replace the `AppHandle` class (current lines 172–189):

```python
class AppHandle(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Composition-root return value (ADR-0010): the shown window and the full
    5-step shutdown handle (`shutdown()`) plus the raw resource handles it needs.
    `shutdown()` performs steps 1-5 of the six-step ordered shutdown
    (`05_CONCURRENCY_GUARANTEES.md` §8); step 6 (process exit) is `__main__.py`'s
    responsibility, since it runs only after `app.exec()` itself has returned."""  # fmt: skip

    window: QMainWindow
    write_conn: sqlite3.Connection
    write_lock: threading.Lock
    task_runner: QtTaskRunner[object]
    run_dispatcher: RunDispatcher
    http_client: httpx.Client
    instance_lock: InstanceLockHandle
    loop: QEventLoop
    flow: QtBenchmarkFlow

    def shutdown(self, *, timeout_ms: int) -> None:
        """Run the ordered shutdown's steps 1-5, in order (steps 1-2 first).

        Args:
            timeout_ms: The bound passed to the pipeline's hard-cancel/dispatcher-join
                wait (step 1 and the dispatcher-join half of step 2).
        """
        self.flow.shutdown(timeout_ms)  # 1: hard-cancel; 2a: join the dispatcher thread
        self.task_runner.shutdown()  # 2b: drain the TaskRunner pool
        self.http_client.close()  # 3
        with self.write_lock:  # 4
            self.write_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.write_conn.close()
        self.instance_lock.release()  # 5
```

Then update the `AppHandle(...)` construction at the end of `build_app` (current line 492) to pass the
new field. `flow` is already a local variable in `build_app` (`flow = make_qt_benchmark_flow(pipeline=pipeline)`,
current line 414) — no new construction needed, only threading it into the return:

```python
    return AppHandle(
        window=window,
        write_conn=write_conn,
        write_lock=lock,
        task_runner=task_runner,
        run_dispatcher=dispatcher,
        http_client=http_client,
        instance_lock=instance_lock,
        loop=loop,
        flow=flow,
    )  # fmt: skip
```

Also update `task_runner`'s declared local type where it's first constructed (current line 387,
`task_runner: TaskRunner[object] = make_qt_task_runner()`) — with `make_qt_task_runner`'s own return
type still declared as `TaskRunner[T]` (Task 3 did not change that factory's signature, only exported
the concrete class), this line needs a `cast` or the annotation dropped so mypy infers the concrete
type from `make_qt_task_runner()`'s actual runtime type. Simplest: drop the explicit annotation and let
mypy infer through the call:

```python
    task_runner = make_qt_task_runner()
```

Since `make_qt_task_runner[T]() -> TaskRunner[T]` is declared to return the Protocol type, mypy will
still infer `TaskRunner[object]` here, **not** `QtTaskRunner[object]` — the annotation drop alone is not
sufficient. Use an explicit cast instead, importing `cast` from `typing` (already a common pattern
elsewhere in this codebase — `compose.py` does not currently import `cast`, so add it to the existing
`from typing import NoReturn` line):

```python
from typing import NoReturn, cast
```

And at the construction site:

```python
    task_runner = cast("QtTaskRunner[object]", make_qt_task_runner())
```

- [ ] **Step 9: Run the failing tests to verify they now pass**

Run:

```bash
uv run pytest tests/integration/test_compose_build_app.py -v
uv run pytest tests/integration/test_quit_sequence.py -v
uv run pytest tests/integration/test_launch_crash_recovery.py -v
```

Expected: PASS — all of `test_compose_build_app.py` (including the updated field-set test and every
other test using the now-shared `_shutdown()` helper), all three new `test_quit_sequence.py` tests, and
the Part A crash-recovery test.

- [ ] **Step 10: Run the full compose.py-adjacent regression sweep**

Run:

```bash
uv run pytest tests/integration/test_launch_seeding.py tests/integration/test_launch_instance_lock.py tests/integration/test_launch_abort_modal_quits.py tests/integration/test_ui_thread_exception_hook.py tests/integration/test_launch_app_data_dir.py tests/integration/test_launch_schema_check.py -v
```

Expected: PASS — none of these files construct `AppHandle` with positional args or otherwise touch the
changed field set, so they should be unaffected; this step is a safety net given how many launch-tier
integration tests exist near `compose.py`.

- [ ] **Step 11: Check `compose.py`'s architecture-test line budget**

Run: `uv run pytest tests/architecture/ -k compose -v`

If this fails on the line-count bound (STORY-077-AC-5's 50–500-line invariant), **stop and report** —
per this plan's Global Constraints, do not raise the budget unilaterally; the story's Design constraints
say the file was at 399 lines with "roughly a dozen lines" of headroom expected to be spent here, so this
should pass, but confirm rather than assume.

- [ ] **Step 12: Lint and typecheck**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/compose.py tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py tests/integration/test_launch_crash_recovery.py
uv run ruff format src/ollama_llm_bench/compose.py tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py tests/integration/test_launch_crash_recovery.py
uv run mypy --strict src/ollama_llm_bench/compose.py tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py tests/integration/test_launch_crash_recovery.py
uv run lint-imports
```

Expected: no findings.

- [ ] **Step 13: Commit**

```bash
git add src/ollama_llm_bench/compose.py tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py tests/integration/test_launch_crash_recovery.py
git commit -m "feat(compose): AppHandle performs the full 5-step ordered shutdown; wire the launch-time crash-recovery sweep (STORY-080-AC-4, AC-5, AC-6, AC-7)"
```

______________________________________________________________________

## Task 5: `__main__.py` calls `handle.shutdown()` after `app.exec()` returns (step 6)

**Files:**

- Modify: `src/ollama_llm_bench/__main__.py:220-226` (the crash hook's `_quit()`), `:308-334` (`main()`)

**Interfaces:**

- Consumes: `AppHandle.shutdown(self, *, timeout_ms: int) -> None` (Task 4).

- Produces: nothing new — `main()`'s own signature is unchanged.

- [ ] **Step 1: Write the failing test**

This change has no isolated unit test of its own — `main()` is an integration-level entry point already
exercised indirectly by `tests/integration/test_ui_thread_exception_hook.py`. Extend that file: find its
existing test that exercises `_handle_ui_thread_exception`'s `_quit()` nested function (search:
`grep -n "_quit\|handle_holder\|AppHandle" tests/integration/test_ui_thread_exception_hook.py`) and add
an assertion that `handle.shutdown` is called with a `timeout_ms` keyword argument, not the old no-arg
form. If the existing test already mocks `handle.shutdown` via `mocker.Mock(spec=AppHandle)` or similar,
this assertion is a one-line addition to that existing test rather than a new test — inspect the file
first (`cat tests/integration/test_ui_thread_exception_hook.py`) before writing this step's exact diff,
since the plan author has not read this specific test's current body in full. At minimum, add:

```python
    # Assert (append to the existing crash-hook-calls-shutdown test)
    shutdown_spy.assert_called_once_with(timeout_ms=mocker.ANY)
```

replacing whatever the current no-arg assertion is (likely `shutdown_spy.assert_called_once_with()` or
`assert_called_once()`).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_ui_thread_exception_hook.py -v`
Expected: FAIL on the updated assertion — today `handle.shutdown()` is called with zero arguments.

- [ ] **Step 3: Update `__main__.py`**

Add a module-level timeout constant near the existing `_FATAL_DIALOG_TITLE`/`_FATAL_DIALOG_MESSAGE`
constants (around line 62):

```python
_SHUTDOWN_TIMEOUT_MS: Final[int] = 5000
```

Update the crash hook's nested `_quit()` function (current lines 220–226):

```python
    def _quit() -> None:
        handle = collaborators.handle_holder.handle
        if handle is not None:
            handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)
        instance = QApplication.instance()
        if instance is not None:
            instance.exit(1)
```

Update `main()` (current lines 308–334) so the final two lines change from `handle.window.show(); sys.exit(app.exec())` to capturing the exit code, running the ordered shutdown, then exiting with that
code:

```python
def main(argv: Sequence[str] | None = None) -> None:
    """Launch the application: parse arguments, compose the object graph, run Qt.

    Implements ``08-M_app_lifecycle.md`` §2 steps 1-2 directly (argument parsing,
    platform detection), configures logging (step 3) before any worker or dialog
    can exist, then defers the remaining ordered launch steps to
    :func:`ollama_llm_bench.compose.build_app` per ADR-0010. After the Qt event
    loop returns, runs the ordered shutdown (`05_CONCURRENCY_GUARANTEES.md` §8
    steps 1-5, via `AppHandle.shutdown()`) before exiting with the loop's own
    exit code (step 6) -- STORY-080.

    Args:
        argv: The argument vector to parse (excluding the program name), or
            ``None`` to parse ``sys.argv[1:]`` — the normal
            ``python -m ollama_llm_bench`` / console-script invocation.
    """
    args = _parse_launch_arguments(argv)
    profile = make_platform_detector().detect()
    configure_logging(app_log_file=app_log_path(profile), level=args.log_level)

    app = QApplication(sys.argv[:1])
    clipboard = make_clipboard()
    event_bus = make_qt_event_bus_deliverer()
    handle_holder = _AppHandleHolder()
    _install_exception_hooks(clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder)

    handle = build_app(app=app, loop=QEventLoop())
    handle_holder.set_handle(handle)
    handle.window.show()
    exit_code = app.exec()
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)
    sys.exit(exit_code)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_ui_thread_exception_hook.py -v`
Expected: PASS

- [ ] **Step 5: Run the full worker-thread exception hook suite too (regression safety)**

Run: `uv run pytest tests/integration/test_worker_thread_exception_hook.py -v`
Expected: PASS — this file doesn't touch `main()`'s tail or the UI-thread crash hook's `_quit()`, so it
should be unaffected; run it anyway since it lives in the same file group STORY-076 introduced.

- [ ] **Step 6: Lint and typecheck**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/__main__.py tests/integration/test_ui_thread_exception_hook.py
uv run ruff format src/ollama_llm_bench/__main__.py tests/integration/test_ui_thread_exception_hook.py
uv run mypy --strict src/ollama_llm_bench/__main__.py tests/integration/test_ui_thread_exception_hook.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/__main__.py tests/integration/test_ui_thread_exception_hook.py
git commit -m "feat(main): run the ordered shutdown after app.exec() returns, before process exit (STORY-080-AC-6)"
```

______________________________________________________________________

## Task 6: Persist the active workspace on confirmed quit

**Files:**

- Modify: `src/ollama_llm_bench/ui/main_window/api.py:151-160`
- Modify: `tests/integration/test_quit_sequence.py` (add the AC-3 test to the file Task 4 created)

**Interfaces:**

- Consumes: `MainWindowGateway.set_active_workspace(self, value: str) -> None` (already exists,
  `adapters/ui_gateways/_internal/main_window/gateway.py:96`); `WorkspaceController.active(self) -> str`
  (already exists, `adapters/workspace_controller/protocols.py:19`, and is already a parameter
  `make_main_window` receives as `workspace`).

- Produces: nothing new — `_on_confirmed_quit`'s closure signature is internal to `api.py`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_quit_sequence.py` (created in Task 4):

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot


def test_quit_persists_ui_state_before_closing_db(
    seeded_app_data_root: Path, qapp: QApplication, qtbot: QtBot
) -> None:
    """Proves: STORY-080-AC-3

    Given a quit has been confirmed, when the confirmed-quit path runs, then
    the active workspace has been written through the settings service before
    the database write connection is closed.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    qtbot.addWidget(handle.window)
    task_editor_button = handle.window.findChild(QPushButton, "workspace_switcher_task_editor")
    assert task_editor_button is not None
    qtbot.mouseClick(task_editor_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    # Act
    handle.window.close()
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    after_write_conn, after_lock = open_write_connection(seeded_app_data_root / DB_FILENAME)
    try:
        from ollama_llm_bench.backend.persistence.app_settings import create_app_settings_store

        appset = create_app_settings_store(
            after_write_conn, after_lock, lambda: open_write_connection(
                seeded_app_data_root / DB_FILENAME
            )[0], make_system_clock()
        )
        assert appset.get_str("ui.active_workspace") == "task_editor"
    finally:
        after_write_conn.close()
```

Note: constructing a second `AppSettingsStore` against an already-closed write connection's file needs a
fresh read path — if `create_app_settings_store`'s `read_conn` factory parameter rejects the inline
lambda shown above (it expects a zero-arg callable returning a connection, matching the `functools.partial(open_read_connection, db_path)` pattern used everywhere else in this plan), replace that
inline lambda with the same `functools.partial(open_read_connection, seeded_app_data_root / DB_FILENAME)` pattern instead, importing `open_read_connection` alongside `open_write_connection` at the top of the
file. Prefer that over the inline lambda — it matches every other test in this plan.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_quit_sequence.py -k persists_ui_state -v`
Expected: FAIL — `appset.get_str("ui.active_workspace")` returns `None` (or the empty-string default),
since nothing writes it today.

- [ ] **Step 3: Wire the persistence call**

In `src/ollama_llm_bench/ui/main_window/api.py`, modify `_on_confirmed_quit` (current lines 151–153):

```python
    def _on_confirmed_quit() -> None:
        gateway.set_active_workspace(workspace.active())
        geometry_writer.flush()
        shell.force_close()
```

`gateway` and `workspace` are both already parameters `make_main_window` receives — no new parameter is
added to this function's own signature.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_quit_sequence.py -k persists_ui_state -v`
Expected: PASS

- [ ] **Step 5: Run the full `test_quit_sequence.py` file together**

Run: `uv run pytest tests/integration/test_quit_sequence.py -v`
Expected: PASS — all four tests in this file (AC-3, AC-4, AC-6, AC-7).

- [ ] **Step 6: Lint and typecheck**

Run:

```bash
uv run ruff check --fix src/ollama_llm_bench/ui/main_window/api.py tests/integration/test_quit_sequence.py
uv run ruff format src/ollama_llm_bench/ui/main_window/api.py tests/integration/test_quit_sequence.py
uv run mypy --strict src/ollama_llm_bench/ui/main_window/api.py tests/integration/test_quit_sequence.py
```

Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/ui/main_window/api.py tests/integration/test_quit_sequence.py
git commit -m "feat(main-window): persist ui.active_workspace on confirmed quit (STORY-080-AC-3)"
```

______________________________________________________________________

## Task 7: Full regression sweep, coverage, and traceability

**Files:** none new — this task only runs the project-wide gates.

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`
Expected: PASS — zero failures anywhere in the suite, including every file this plan touched and every
file it didn't.

- [ ] **Step 2: Full lint/typecheck/import/arch sweep**

Run: `just check`
Expected: PASS (lint, format-check, typecheck, import-check, arch-test, test all green).

- [ ] **Step 3: Per-layer coverage**

Run: `just coverage-layers`
Expected: PASS — backend ≥90%, view-models/controllers ≥85%, widgets ≥60%. If `just coverage-layers`
segfaults (exit 139) under `pytest-randomly`, rerun once before treating it as a real regression (known
flake, not specific to this story).

- [ ] **Step 4: Regenerate and validate traceability**

Run:

```bash
just trace
just trace-check
```

Expected: `just trace` regenerates `traceability.yaml` with STORY-080's 8 ACs and EC-M-4/6/7 now proven
by real tests. `just trace-check` should now show **zero** failures for EC-M-4, EC-M-6, and EC-M-7
specifically (they were the pre-existing intentional-red-state entries this story exists to close per
project memory). If `just trace-check` still fails on EC-M-5 or any edge case unrelated to this story,
that is pre-existing and out of this story's scope — confirm it was already failing before this story's
changes (`git stash` and re-run, per the established verification pattern for this repo) before treating
it as a regression this story introduced.

- [ ] **Step 5: Flip the story to done**

Once every prior step is green, update `docs/stories/story-080-quit-sequence-and-crash-recovery.md`:
check every box in its Definition of Done section, and change its front-matter `status: ready` to
`status: done`.

- [ ] **Step 6: Final commit**

```bash
git add docs/stories/story-080-quit-sequence-and-crash-recovery.md traceability.yaml
git commit -m "chore(story-080): mark done; regenerate traceability"
```

______________________________________________________________________

## Self-Review Notes (from the plan author, not a task to execute)

- **Spec coverage**: every acceptance criterion (AC-1 through AC-8) and every edge case (EC-M-4, EC-M-6,
  EC-M-7) maps to a task above. The three ambiguities the architect resolved in the story text (shutdown
  step ownership, Task Editor scope boundary, sweep call sites) are each implemented exactly as the story
  specifies — no task re-derives a decision the story already settled.
- **Task Editor deferral respected**: no task wires a real `dirty_buffer_count` or real per-file save —
  `save_all_buffers` (Task 2) stays a test-supplied hook, exactly like `dirty_buffer_count` already is,
  per the story's own out-of-scope boundary (STORY-114 owns the real implementation).
- **`APP_SHUTDOWN` vs `USER_STOP`**: no task touches `CancelReason` selection anywhere — `BenchmarkFlowApi.shutdown()`'s existing `CancelReason.USER_STOP` is left exactly as-is, per the story's explicit
  "do not fix" constraint.
- **New public surface kept to the minimum the story promised**: exactly one new field on `AppHandle`
  (`flow`), one new constructor parameter on `CloseHandler` (`save_all_buffers`), one retyped field
  (`task_runner`), and one new export (`QtTaskRunner` from `adapters/qt_runnables`) — matching the
  story's own "this story's single new public-surface change" framing (the `flow` field) plus the
  narrowly-scoped `adapters/qt_runnables/` addition this plan discovered and recorded in the story's
  Notes section before this plan was written.
