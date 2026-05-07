# Audit Gap Remediation — Implementation Plan

> **Source**: Traceability audit of `.AdditionalDocs/improved_changes_plan/` vs `feature/v2-app-redesign`.
> **Branch**: `feature/v2-app-redesign`
> **Date**: 2026-04-30

---

## Overview

Four confirmed gaps require implementation. All others in the audit were promoted to ✅ after full code verification.

| Step | Gap | Spec Ref | Files Affected | Effort |
|------|-----|----------|----------------|--------|
| 1 | Splitter collapse on run start | 1.9 | `central_widget.py` | ~1h |
| 2 | Judge widget health filter + status notification | 1.4 | `judge_widget.py`, `run_config_controller.py` | ~1.5h |
| 3 | `RunSummary` dataclass | 1.7 prereq | `backend/core/models.py` | ~30m |
| 4 | `RunSummaryDialog` — pre-start confirmation | 1.7 | `panels/run_summary_dialog.py` (new), `panels/run_config_panel.py` | ~4h |
| 5 | `ResumeSummaryDialog` — resume confirmation | 1.8 | `panels/resume_summary_dialog.py` (new), `panels/run_config_panel.py`, `controllers/run_config_controller.py` | ~3h |

**Execute in order**: Steps 1 and 2 are independent; Step 3 must precede Steps 4 and 5.

---

## Step 1 — Splitter collapse on run start/finish (Gap 1.9)

### Motivation

When a benchmark starts the Left Panel (run configuration) is irrelevant — the user confirmed their config in the pre-start dialog. Collapsing it gives the Center Panel (progress + log) more width. On finish/stop the panel restores.

### Files modified

- `src/ollama_llm_bench/ui/widgets/central_widget.py`

### Implementation

**1.1 — Promote `splitter` from local to instance attribute**

In `_setup_layout()` (line 52), change:
```python
splitter = QSplitter(Qt.Orientation.Horizontal)
```
to:
```python
self._splitter = QSplitter(Qt.Orientation.Horizontal)
```
Update all three subsequent `splitter.addWidget` and `splitter.setSizes` calls to `self._splitter.*`.
Change `layout.addWidget(splitter)` to `layout.addWidget(self._splitter)`.

**1.2 — Store EventBus and add pre-run-sizes attribute**

In `__init__` (after `super().__init__()`), before `_setup_layout()`:
```python
self._event_bus = ctx.get_event_bus()
self._pre_run_sizes: list[int] = []
```

**1.3 — Subscribe to lifecycle events**

At the end of `__init__` (after `_setup_layout()`), add:
```python
self._event_bus.subscribe_to_benchmark_started(self._on_benchmark_started)
self._event_bus.subscribe_to_benchmark_finished(self._on_benchmark_finished)
self._event_bus.subscribe_to_benchmark_stopped(self._on_benchmark_stopped)
```

**1.4 — Add event handler methods**

Add three new private methods to `CentralWidget`:

```python
def _on_benchmark_started(self, _event: BenchmarkStartedEvent) -> None:
    self._pre_run_sizes = self._splitter.sizes()
    self._splitter.setSizes([0, *self._pre_run_sizes[1:]])

def _on_benchmark_finished(self, _event: BenchmarkFinishedEvent) -> None:
    self._restore_splitter()

def _on_benchmark_stopped(self, _event: BenchmarkStoppedEvent) -> None:
    self._restore_splitter()

def _restore_splitter(self) -> None:
    if self._pre_run_sizes:
        self._splitter.setSizes(self._pre_run_sizes)
        self._pre_run_sizes = []
```

**1.5 — Add required imports**

Add to the import block in `central_widget.py`:
```python
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
)
```

### Tests

File: `tests/unit/widgets/test_run_config_panel_locking.py` (extend existing file)

| Test | Assertion |
|------|-----------|
| `test_splitter_collapses_on_benchmark_started` | After emitting `BenchmarkStartedEvent`, `splitter.sizes()[0] == 0` |
| `test_splitter_restores_on_benchmark_finished` | After collapse then `BenchmarkFinishedEvent`, `splitter.sizes()[0]` equals pre-run value |
| `test_splitter_restores_on_benchmark_stopped` | Same as above for `BenchmarkStoppedEvent` |
| `test_splitter_noop_restore_when_no_prior_run` | Emitting finished without a prior started does not crash |

Use `mocker.Mock(spec=AppContext)` for all service dependencies.

---

## Step 2 — Judge widget health filter + status notification (Gap 1.4)

### Motivation

The current `_refresh_providers()` in `JudgeWidget` calls `controller.get_provider_names()`, which returns enabled providers — but does **not** filter by health. An unhealthy provider (failed API key, unreachable host) should not appear. Additionally, when the previously-selected provider disappears after a refresh, the widget silently switches to the first item with no user feedback. The spec requires a `QStatusBar` notification.

### Files modified

- `src/ollama_llm_bench/ui/controllers/run_config_controller.py`
- `src/ollama_llm_bench/ui/widgets/panels/control/judge_widget.py`

### Implementation

**2.1 — Add health cache and `get_healthy_provider_ids()` to controller**

`RunConfigController` subscribes to `ProviderHealthCheckEvent` during benchmarks. Add a health-state cache:

In `__init__` (after existing attribute assignments, line ~60):
```python
self._provider_health: dict[str, bool] = {}
```

Subscribe in `__init__`:
```python
event_bus.subscribe_to_provider_health_check(self._on_provider_health_check)
```

Add handler method:
```python
def _on_provider_health_check(self, event: ProviderHealthCheckEvent) -> None:
    self._provider_health[event.provider_id] = event.is_healthy
```

Add new public method:
```python
def get_healthy_provider_ids(self) -> list[str]:
    """Return enabled provider IDs whose last health check passed (or were never checked).

    A provider that has never been health-checked is considered healthy (optimistic default).
    """
    try:
        enabled = self._provider_registry.get_enabled_providers()
        return [
            p.provider_id
            for p in enabled
            if self._provider_health.get(p.provider_id, True)
        ]
    except Exception:
        _logger.warning("Failed to list healthy providers", exc_info=True)
        return []
```

**2.2 — Add `show_status_message()` to controller**

Inject `NotificationService` into the controller. In `__init__` signature (keyword-only), add:
```python
notification_service: NotificationService,
```
Store as `self._notification_service = notification_service`.

Add public method:
```python
def show_status_message(self, text: str, msecs: int = 5000) -> None:
    """Display a transient message in the application status bar."""
    self._notification_service.show_info(text, msecs)
```

**Wire in `app_context.py`**: pass `notification_service=ctx.notification_service` (or however the DI root wires `NotificationService`) when constructing `RunConfigController`. Verify the existing wiring in `app_context.py` / `_create_app_context()`.

**2.3 — Update `JudgeWidget._refresh_providers()`**

At line 172, replace:
```python
providers = self._controller.get_provider_names()
```
with:
```python
providers = self._controller.get_healthy_provider_ids()
```

In the fallback block (lines 207–211), after setting `currentIndex(0)`, add:
```python
if current_provider and current_provider not in providers:
    first = self._provider_combo.currentText()
    if first and first != _PLACEHOLDER_TEXT:
        self._controller.show_status_message(
            f"Judge provider '{current_provider}' is no longer available; selecting '{first}'."
        )
```

**2.4 — Subscribe to `ProviderRegistryReloadedEvent` in JudgeWidget**

The widget already has `_on_refresh_clicked` — also trigger a refresh on `ProviderRegistryReloadedEvent` from the event bus. This requires passing the event bus into `JudgeWidget` or subscribing via the controller. Preferred pattern: add an optional `subscribe_to_registry_reloaded` callback method on the controller and call it in `JudgeWidget.__init__`:

```python
# In JudgeWidget.__init__, after _connect_signals():
self._controller.subscribe_to_provider_registry_reloaded(self._refresh_providers)
```

Add `subscribe_to_provider_registry_reloaded(callback)` to controller:
```python
def subscribe_to_provider_registry_reloaded(
    self, callback: Callable[[], None]
) -> None:
    self._event_bus.subscribe_to_provider_registry_reloaded(
        lambda _event: callback()
    )
```

### Required imports

In `run_config_controller.py`:
```python
from ollama_llm_bench.backend.core.models import ProviderHealthCheckEvent
from ollama_llm_bench.ui.qt_classes.notification_service import NotificationService
```

### Tests

File: `tests/unit/widgets/test_judge_widget_health_filter.py` (new)

| Test | Assertion |
|------|-----------|
| `test_unhealthy_provider_excluded_from_combo` | After emitting `ProviderHealthCheckEvent(is_healthy=False)`, provider absent from combo |
| `test_healthy_provider_included_in_combo` | Provider with `is_healthy=True` appears |
| `test_never_checked_provider_included` | Provider with no health event appears (optimistic default) |
| `test_fallback_shows_status_message` | When selected provider disappears on refresh, `show_status_message` called with expected text |

---

## Step 3 — `RunSummary` dataclass (prerequisite for Steps 4 and 5)

### Files modified

- `src/ollama_llm_bench/backend/core/models.py`

### Implementation

Add after `BenchmarkRun` (around line 205):

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class RunSummary:
    """Snapshot of run configuration assembled at Start-click time.

    Passed to ``RunSummaryDialog`` for user confirmation before the benchmark starts.
    Every value is the *effective* value (per-run override if set, else Settings default).
    Source strings identify where the value came from.
    """

    mode: RunMode
    judge_provider_id: str
    judge_model: str
    selected_models: tuple[ModelDescriptor, ...]  # ordered; all providers
    task_paths: tuple[str, ...]
    task_count: int
    streaming_enabled: bool
    streaming_source: str   # "default from Settings" | "per-run override"
    warmup_enabled: bool
    warmup_source: str
    reasoning_effort: str
    reasoning_source: str
    perf_config: PerformanceConfig | None = None
    prompt_variants: tuple[str, ...] = ()
```

No new imports needed — `ModelDescriptor`, `RunMode`, `PerformanceConfig` are already in `models.py`.

---

## Step 4 — `RunSummaryDialog` (Gap 1.7)

### Motivation

Clicking `Start` currently begins the benchmark immediately after `_build_run_start_event()` assembles the config. The spec requires a confirmation dialog summarising the complete effective configuration so the user can catch mistakes before committing to a potentially multi-hour run.

### Files modified / created

- `src/ollama_llm_bench/ui/widgets/panels/run_summary_dialog.py` **(new)**
- `src/ollama_llm_bench/ui/widgets/panels/run_config_panel.py` (wire at lines 240–245)
- `src/ollama_llm_bench/backend/core/models.py` (Step 3 adds `RunSummary`)

### Implementation

**4.1 — Create `RunSummaryDialog`**

New file `src/ollama_llm_bench/ui/widgets/panels/run_summary_dialog.py`:

```
Class: RunSummaryDialog(QDialog)
Constructor: def __init__(self, *, summary: RunSummary, parent: QWidget | None = None) -> None
```

Constructor phases (mirroring project pattern):
1. `_build_widgets(summary)` — create all section widgets
2. `_build_layout()` — assemble scroll area + dialog button box
3. `_wire_signals()` — connect section toggle buttons, validate state
4. `_validate()` — called on init; disables `Start Benchmark` if blocking conditions met

**Layout structure:**
```
QVBoxLayout (dialog root)
├── QLabel("Confirm benchmark configuration")  [role="heading"]
├── QScrollArea
│   └── QWidget (scroll contents)
│       └── QVBoxLayout
│           ├── _CollapsibleSection("Mode", _build_mode_body(summary))
│           ├── _CollapsibleSection("Judge", _build_judge_body(summary))   [hidden if mode == SPEED/PERFORMANCE]
│           ├── _CollapsibleSection("Test Models", _build_models_body(summary))
│           ├── _CollapsibleSection("Task Files", _build_task_files_body(summary))
│           ├── _CollapsibleSection("Advanced Options", _build_advanced_body(summary))
│           ├── _CollapsibleSection("Mode-specific", _build_mode_specific_body(summary))  [hidden if no content]
│           └── _CollapsibleSection("Estimated Work", _build_estimated_work_body(summary))
└── QDialogButtonBox
    ├── QPushButton("Edit")         [RejectRole — closes dialog, does NOT start]
    └── QPushButton("Start Benchmark")  [AcceptRole — starts run]
```

**`_CollapsibleSection` helper** (private inner class or module-level):
- `QPushButton(title, checkable=True, flat=True)` with `▶`/`▼` triangle icon
- Child `QFrame` toggled via `button.toggled.connect(frame.setVisible)` + `setChecked(True)` by default (expanded)

**Section bodies:**

| Section | Content | Visibility rule |
|---------|---------|-----------------|
| Mode | `RUN_MODE_LABELS[mode]` + `RUN_MODE_DESCRIPTIONS[mode]` as `QLabel(wordWrap=True)` | Always |
| Judge | `QFormLayout`: Provider, Model, Reasoning Effort | Hidden when `mode in (SPEED, PERFORMANCE)` |
| Test Models | Per-provider `QGroupBox`: provider label + sub-list of model names. Disabled-provider models in yellow "Will be skipped" section with `Remove` `QToolButton` per row. If zero selected: warning `QLabel`. | Always |
| Task Files | `QListWidget` of paths; each item shows `path (N tasks)` | Always |
| Advanced Options | `QFormLayout` per option: `"{value} ({source})"` format | Always |
| Mode-specific | Performance Matrix checkboxes (PERFORMANCE mode) or prompt variant count (PROMPT_EVAL) | Hidden when mode is SPEED or FULL_GRADING |
| Estimated Work | `QLabel(f"{len(models)} model(s) × {task_count} tasks = {len(models) * task_count} inference calls")` | Always |

**Validation (disable `Start Benchmark` when):**
- `len(summary.selected_models) == 0` — warning label: "Select at least one test model."
- `len(summary.task_paths) == 0` — warning label: "Add at least one task file."
- All selected models belong to disabled/unhealthy providers — warning label: "All selected models will be skipped. Enable at least one provider."

**Dialog geometry:** `setMinimumWidth(720)`. `QScrollArea` uses `setWidgetResizable(True)`.

**4.2 — Add `_build_run_summary()` to `RunConfigPanel`**

New method after `_build_run_start_event()` (around line 258):

```python
def _build_run_summary(self, event: RunStartEvent) -> RunSummary:
    """Build a RunSummary snapshot from the current widget state."""
    store = self._test_models_widget.get_selection_store()
    opts = self._advanced_widget.get_effective_options()
    task_paths = tuple(self._task_files_widget.get_task_paths())
    # task_count: sum of task counts per file via controller
    task_count = self._controller.count_tasks_in_paths(task_paths)
    return RunSummary(
        mode=event.run_mode,
        judge_provider_id=event.judge_provider_id,
        judge_model=event.judge_model,
        selected_models=tuple(store.all()),
        task_paths=task_paths,
        task_count=task_count,
        streaming_enabled=opts.streaming_enabled,
        streaming_source=opts.streaming_source,
        warmup_enabled=opts.warmup_enabled,
        warmup_source=opts.warmup_source,
        reasoning_effort=opts.reasoning_effort,
        reasoning_source=opts.reasoning_source,
        perf_config=event.perf_config,
        prompt_variants=tuple(
            v.variant_id for v in self._prompt_variants.get_variants()
        ),
    )
```

Add `count_tasks_in_paths(paths: tuple[str, ...]) -> int` to `RunConfigController` (delegates to `task_file_loader`).

**4.3 — Replace TODO at `run_config_panel.py:244`**

Replace lines 243–245:
```python
# TODO (Task 4.1): open RunSummaryDialog here; only proceed on accept.
self._controller.handle_start_click(event)
```
with:
```python
summary = self._build_run_summary(event)
dlg = RunSummaryDialog(summary=summary, parent=self)
if dlg.exec() != QDialog.DialogCode.Accepted:
    return
self._controller.handle_start_click(event)
```

**Required imports in `run_config_panel.py`:**
```python
from PySide6.QtWidgets import QDialog
from ollama_llm_bench.ui.widgets.panels.run_summary_dialog import RunSummaryDialog
from ollama_llm_bench.backend.core.models import RunSummary
```

### Tests

File: `tests/unit/widgets/test_run_summary_dialog.py` (new)

| Test | Assertion |
|------|-----------|
| `test_dialog_renders_seven_sections` | All 7 `_CollapsibleSection` headers present in layout |
| `test_start_disabled_when_no_models` | `Start Benchmark` button disabled when `selected_models=()` |
| `test_start_disabled_when_no_tasks` | `Start Benchmark` disabled when `task_paths=()` |
| `test_start_enabled_with_valid_summary` | Enabled when models + tasks populated |
| `test_judge_section_hidden_for_speed_mode` | Judge section not visible when `mode=SPEED` |
| `test_test_models_grouped_by_provider` | Model entries rendered under their provider label |
| `test_will_be_skipped_section_for_disabled_provider` | Skipped-models section appears when a provider is inactive |
| `test_advanced_options_show_source` | Each option label contains the source string |
| `test_edit_button_rejects_dialog` | Clicking `Edit` returns `QDialog.Rejected`; no `handle_start_click` call |
| `test_start_button_accepts_dialog` | Clicking `Start Benchmark` returns `QDialog.Accepted` |

---

## Step 5 — `ResumeSummaryDialog` (Gap 1.8)

### Motivation

Resuming a run currently starts without any confirmation. The user cannot see what the original run's configuration was, whether it has drifted (provider now disabled), or what progress was made. The spec requires a read-only confirmation dialog before the resume worker starts.

### Files modified / created

- `src/ollama_llm_bench/ui/widgets/panels/resume_summary_dialog.py` **(new)**
- `src/ollama_llm_bench/ui/widgets/panels/run_config_panel.py` (wire at lines 247–252)
- `src/ollama_llm_bench/ui/controllers/run_config_controller.py` (add data-access methods)

### Implementation

**5.1 — Add data-access methods to `RunConfigController`**

Add public methods exposing the private `_data_api`:

```python
def get_run(self, run_id: int) -> BenchmarkRun:
    """Load a single BenchmarkRun from the database."""
    return self._data_api.get_run(run_id)

def get_results_for_run(self, run_id: int) -> list[BenchmarkResult]:
    """Load all BenchmarkResult rows for the given run."""
    return self._data_api.get_results_for_run(run_id)

def get_enabled_provider_ids(self) -> set[str]:
    """Return the set of currently enabled provider IDs."""
    try:
        return {p.provider_id for p in self._provider_registry.get_enabled_providers()}
    except Exception:
        _logger.warning("Failed to list enabled providers for drift check", exc_info=True)
        return set()
```

**5.2 — Create `ResumeSummaryDialog`**

New file `src/ollama_llm_bench/ui/widgets/panels/resume_summary_dialog.py`:

```
Class: ResumeSummaryDialog(QDialog)
Constructor: def __init__(self, *, run_id: int, controller: RunConfigController, parent: QWidget | None = None) -> None
```

On construction the dialog performs three synchronous reads (all small, single-row):
1. `run = controller.get_run(run_id)`
2. `results = controller.get_results_for_run(run_id)`
3. `enabled_providers = controller.get_enabled_provider_ids()`

Then builds the UI using those values.

**Layout structure:**
```
QVBoxLayout (dialog root)
├── QLabel("Resume benchmark")  [role="heading"]
├── QLabel("These values are frozen from the original run and cannot be changed. …")
│   [role="secondary", wordWrap=True]
├── QScrollArea
│   └── QWidget (scroll contents)
│       └── QVBoxLayout
│           ├── [DRIFT WARNING BANNER — QFrame, role="warning", visible only when drift exists]
│           │   QLabel("<provider/model> is no longer enabled or reachable. …")
│           ├── _CollapsibleSection("Original Configuration")
│           │   └── QFormLayout: Mode, Judge Provider, Judge Model, Test Models, Task Files, Advanced Options
│           └── _CollapsibleSection("Current Progress")
│               └── QFormLayout: Completed, Not Completed, Waiting for Judge, Failed, Last activity
└── QDialogButtonBox
    ├── QPushButton("Cancel")    [RejectRole]
    └── QPushButton("Resume Run")  [AcceptRole, role="primary"]
```

**Drift detection logic:**

```python
def _detect_drift(
    self, run: BenchmarkRun, enabled_providers: set[str]
) -> list[str]:
    """Return list of drift warning strings."""
    warnings: list[str] = []
    if run.judge_provider_id and run.judge_provider_id not in enabled_providers:
        warnings.append(
            f"Judge provider '{run.judge_provider_id}' is no longer enabled."
        )
    import json
    try:
        models: list[dict[str, str]] = json.loads(run.models_json)
    except (json.JSONDecodeError, ValueError):
        models = []
    drifted = {
        m["provider_id"]
        for m in models
        if m.get("provider_id") and m["provider_id"] not in enabled_providers
    }
    for pid in sorted(drifted):
        warnings.append(f"Test provider '{pid}' is no longer enabled.")
    return warnings
```

**Original configuration section** — reads fields from `BenchmarkRun`:
- Mode: `RUN_MODE_LABELS[run.run_mode]`
- Judge: `run.judge_provider_id` + `run.judge_model`
- Test Models: parse `run.models_json` (list of `{provider_id, model_name}`) into a simple list
- Task Files: `run.task_file_paths`

**Current progress section** — aggregates from `results: list[BenchmarkResult]`:
```python
from collections import Counter
counts = Counter(r.status for r in results)
```
Show: Completed, Not Completed, Waiting for Judge, Failed as `QFormLayout` rows. Plus `run.total_tasks` and `run.completed_tasks`.

**5.3 — Replace TODO at `run_config_panel.py:251`**

Replace lines 250–252:
```python
# TODO (Task 4.2): open ResumeSummaryDialog here; only proceed on accept.
self._controller.handle_resume_run_click(run_id)
```
with:
```python
dlg = ResumeSummaryDialog(run_id=run_id, controller=self._controller, parent=self)
if dlg.exec() != QDialog.DialogCode.Accepted:
    return
self._controller.handle_resume_run_click(run_id)
```

**Required import in `run_config_panel.py`:**
```python
from ollama_llm_bench.ui.widgets.panels.resume_summary_dialog import ResumeSummaryDialog
```

### Tests

File: `tests/unit/widgets/test_resume_summary_dialog.py` (new)

| Test | Assertion |
|------|-----------|
| `test_dialog_shows_run_name` | Title area shows `run.run_name` or synthesized fallback |
| `test_progress_counts_correct` | Counts derived from result list match expected totals |
| `test_no_drift_no_warning_banner` | Drift banner hidden when all providers still enabled |
| `test_drift_warning_when_judge_provider_disabled` | Drift banner visible with correct provider name |
| `test_drift_warning_when_test_provider_disabled` | Drift banner lists disabled test provider |
| `test_cancel_rejects_dialog` | Cancel returns `QDialog.Rejected`; no `handle_resume_run_click` call |
| `test_resume_accepts_dialog` | Resume Run returns `QDialog.Accepted` |
| `test_config_section_is_readonly` | No editable widgets inside Original Configuration section |

---

## Verification

### Automated checks (run after each step)

```bash
# After each step:
uv run pytest tests/unit/widgets/ -q --tb=short

# Full pipeline after all steps:
./scripts/ai-check.sh
```

### Manual spot-checks

| Check | Expected result |
|-------|----------------|
| Start benchmark → dialog appears | 7-section confirmation dialog opens; run does NOT start |
| Click `Edit` in dialog | Dialog closes, no run started, panel state preserved |
| Click `Start Benchmark` | Dialog accepts, run begins |
| Disable a provider in Settings, then click Start | Affected models appear in yellow "Will be skipped" section in dialog |
| Resume a run → dialog appears | Frozen config shown, current progress counts correct |
| Resume with a now-disabled provider | Yellow drift warning visible before confirming |
| Start a run → Left Panel collapses | Left pane width → 0; Center + Right expand |
| Stop run → Left Panel restores | Left pane width = pre-run width |
| Judge combobox after provider health failure | Unhealthy provider absent from combo |
| Previous provider disappears on refresh | Status bar shows "Judge provider 'X' is no longer available; selecting 'Y'." |

---

## Dependencies between steps

```
Step 1 (splitter)     ← independent
Step 2 (judge health) ← independent
Step 3 (RunSummary dataclass) ← must precede Steps 4 and 5
Step 4 (RunSummaryDialog)     ← requires Step 3
Step 5 (ResumeSummaryDialog)  ← requires Step 3; Step 2 controller changes may be reused
```

Steps 1 and 2 can be implemented in parallel by separate sessions.
Steps 4 and 5 can be implemented in the same session after Step 3.
