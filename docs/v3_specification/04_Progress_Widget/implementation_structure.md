# Progress Widget — Implementation Structure

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-06-06
**Cross-references:** `description.md`, `state_machine.md`, `flow_diagram.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `11_Services_and_Algorithms/15_LOG_FORMATTING.md`; `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`; `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`

This document defines the module layout, public API, controller decomposition, view-model structs, and test boundary for the Progress Widget. The Progress Widget is the highest event-bus subscription count of any widget in the app, so its controller is split into four cohesive sub-controllers as recommended by the specification structure guide.

---

## Table of Contents

1. Module path and file layout
2. Public API
3. Controller split rationale
4. Sub-controllers
5. View-model structs
6. View
7. Factory wiring example
8. Dependency protocols
9. Test boundary

---

## 1. Module path and file layout

```
src/ollama_llm_bench/ui/progress/
    __init__.py
    api.py                       # make_progress_widget(...) -> QWidget
    models.py                    # frozen view-model structs
    _internal/
        view.py                  # ProgressView QWidget subclass, render only
        controller.py            # ProgressController, owns the four sub-controllers
        counters_controller.py   # CountersController
        current_task_controller.py  # CurrentTaskController
        log_controller.py        # LogController
        stability_controller.py  # StabilityController
        select.py                # pure (event payload) -> view-model functions
    tests/
        conftest.py
        test_view.py
        test_counters_controller.py
        test_current_task_controller.py
        test_log_controller.py
        test_stability_controller.py
```

The public surface stays small: `api.py` and `models.py`. Everything else lives under `_internal/`. The split keeps each `_internal/` file well under the size at which a module must be broken up.

## 2. Public API

`api.py` exports one factory:

```python
def make_progress_widget(
    *,
    bus: EventBus,
    gateway: ProgressGateway,
    log_formatter: LogFormatter,
) -> QWidget:
    """Build the Progress Widget. The caller mounts the returned QWidget.

    Per D-R-06, the controller depends on the adapter-provided `ProgressGateway`
    rather than on backend Protocols directly; the gateway wraps the benchmark-flow
    controls, the run-registry / run / results reads, the past-log reader, the run-log
    settings, and the manual provider-probe command (08-E §7b.4). Model- and
    provider-stability state is NOT read by calling a backend service — it arrives via
    the `_model_stability_changed` and progress events on the bus (so
    `AdaptiveTimeoutService` and the breaker are not injected into the widget). The
    widget-factory signature has been migrated to the explicit gateway type as part of
    the D-R-06 propagation."""
```

The factory builds the view and the `ProgressController`, wires the four sub-controllers, and returns the view. Callers never instantiate the concrete classes; the factory is the swap point.

## 3. Controller split rationale

A single controller for this widget would subscribe to fifteen event-bus signals and own four unrelated derived-state computations. The specification structure guide sets a soft limit: when a widget subscribes to more than four stores or sources, split the controller. The Progress Widget crosses that limit decisively, so its controller is decomposed by concern.

`ProgressController` is a thin parent. It constructs the four sub-controllers, owns the `Disposable` returned by each subscription, applies state transitions from `state_machine.md`, and routes the run-control button clicks. Each sub-controller owns exactly the subscriptions for its concern, holds its own slice of view state, and pushes a view-model slice into the view through a dedicated `apply_*` method.

## 4. Sub-controllers

### 4.1 CountersController

| Property | Value |
|---|---|
| Concern | run-progress counters, stage progress bar, per-stage badges, ETA, model identification |
| Subscribes to | `_progress_updated`, `_stage_changed`, `_run_started` |
| Derives | counter values per `ResultStatus`, stage-bar segment sizes, badge counts, ETA from a rolling average |
| Pushes | `CountersViewModel` |
| Coalescing | consecutive `_progress_updated` events are coalesced; the last payload wins (see `state_machine.md` section 6) |

### 4.2 CurrentTaskController

| Property | Value |
|---|---|
| Concern | the current-task section — task id, stage, task time, timeouts, retry line, the **Inference progress** sub-row, and the **Judge progress** sub-row |
| Subscribes to | `_inference_started`, `_inference_progress`, `_judge_started`, `_judge_completed`, `_task_completed`, `_task_retry` |
| Derives | the in-flight task identity, the running task timer, the retry line with its classified reason, and **two** progress sub-rows: the Inference progress sub-row (sub-state derived from `_inference_progress` events filtered to `context=BENCHMARK_TASK`) and the Judge progress sub-row (sub-state derived from `_inference_progress` events filtered to `context=BENCHMARK_JUDGE`). |
| Pushes | `CurrentTaskViewModel` |
| Notes | The controller subscribes to `_inference_progress` and **filters by `context`**: it accepts only `InferenceContext.BENCHMARK_TASK` and `InferenceContext.BENCHMARK_JUDGE`, ignoring `RUN_ANALYSIS` and `PROVIDER_TEST` (those events are consumed by the Generate Analysis dialog and the Provider Edit inference-test panel respectively). Each sub-row is updated by its own display label, refreshed on every accepted `_inference_progress` arrival (the event is already coalesced at ≥ 1 Hz per call at the emitter — see `08_Cross_Cutting/08-J_event_bus_catalog.md` §5.3). The labels are verbosity-independent — they do not read `ui.run_log_verbosity`. The Inference progress sub-row is reset and shown on `_inference_started` and hidden on `_task_completed` (and on every state transition out of `TaskInflight`; see `state_machine.md` §3). The Judge progress sub-row is reset and shown on `_judge_started` and hidden on `_judge_completed` / `_task_completed`. The token-estimation source flag — provider per-chunk `delta_tokens`, provider running count, or 4-char heuristic — is tracked on the controller from the pipeline-side decision (the `_inference_progress` payload does not carry it explicitly; the controller infers "approximation" when the `tokens_received` value is non-`None` while no chunk has carried a `delta_tokens` field, see `04_Progress_Widget/description.md` §7.1). |

### 4.3 LogController

| Property | Value |
|---|---|
| Concern | the run event-log panel — raw event cache, verbosity rendering, search, clear, buffer cap, auto-scroll |
| Subscribes to | `_inference_started`, `_inference_completed`, `_task_completed`, `_judge_started`, `_judge_completed`, `_task_retry`, `_stage_changed`, `_provider_switched`, `_model_switched`, `_run_stopped`, `_run_finished`, `_run_failed`, `_model_stability_changed`, `_provider_registry_reloaded`, `_log_cleared` |
| Derives | one HTML log line per event, produced by the log-formatting service at the active verbosity; the search filter; the bounded buffer |
| Pushes | `LogViewModel` |
| Notes | caches every raw event so a verbosity change re-renders without data loss; reads `ui.run_log_verbosity` and `ui.run_log_max_lines`; loads the saved log file of a past run through the run-log reader |

### 4.4 StabilityController

| Property | Value |
|---|---|
| Concern | the model-stability and provider-stability callouts |
| Subscribes to | `_model_stability_changed` |
| Derives | the model band (ok, warn, excluded) from the adaptive-timeout fields and the provider band (closed, half-open, open) from the circuit-breaker fields of the payload |
| Pushes | `StabilityViewModel` |
| Notes | the "retry probe" action calls `ProgressGateway.manual_provider_probe()` (the adapter wraps the breaker/probe — never a direct breaker call, D-R-06); the payload already carries a snapshot for rendering |

## 5. View-model structs

All view-models are `msgspec.Struct(frozen=True, kw_only=True, gc=False)`. The view applies a slice through a dedicated method; it never reads stores.

```python
class CountersViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    stage: RunStage
    tasks_done: int
    tasks_total: int
    eta_label: str
    total_time_label: str
    counts_by_status: dict[ResultStatus, int]
    bar_segments: tuple[tuple[str, int], ...]   # (segment name, weight)
    badge_counts: tuple[tuple[str, int], ...]
    judge_phase_active: bool
    provider_label: str
    model_label: str

class CurrentTaskViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    task_id: str | None
    stage_label: str
    task_time_label: str
    timeouts: int
    retry_active: bool
    retry_label: str | None        # "2/3 - Connection refused"
    inference_progress_visible: bool
    inference_progress_label: str | None   # e.g. "Waiting for first token — 1.2 s" or "Generating — 184 tokens · 5.6 s elapsed"
    judge_progress_visible: bool
    judge_progress_label: str | None       # e.g. "Judge: waiting for response — 2.4 s" or "Judge: receiving — 96 tokens · 3.1 s elapsed"
    last_progress_context: InferenceContext | None    # latest accepted context for the active result (BENCHMARK_TASK or BENCHMARK_JUDGE); None when no progress event has been observed for the active result

class LogLineViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    kind: str                      # "stage" | "system" | "task_start" | ...
    html: str

class LogViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    verbosity: RunLogVerbosity     # SHORT | NORMAL | VERBOSE
    lines: tuple[LogLineViewModel, ...]
    search_term: str
    auto_scroll: bool
    file_write_warning: bool       # set on EC-LOG-1

class StabilityViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    model_band: str                # "ok" | "warn" | "excluded"
    model_text: str
    provider_band: str             # "closed" | "warn" | "open"
    provider_text: str
    show_retry_probe: bool
    show_open_settings: bool

class ProgressViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    widget_state: str              # one of state_machine.md states
    run_name: str
    show_rename_pencil: bool
    pause_resume_label: str        # "Pause" | "Resume"
    pause_resume_enabled: bool
    stop_enabled: bool
    counters: CountersViewModel
    current_task: CurrentTaskViewModel
    log: LogViewModel
    stability: StabilityViewModel
```

`RunStage`, `ResultStatus`, `RunLogVerbosity`, and `InferenceContext` are the canonical enums defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; this widget does not redefine them.

## 6. View

`ProgressView` is a `QWidget` subclass built programmatically with Qt Widgets. It exposes:

- `apply(vm: ProgressViewModel) -> None` — the single top-level render entry point; idempotent.
- `apply_counters(vm: CountersViewModel) -> None`, `apply_current_task(...)`, `apply_log(...)`, `apply_stability(...)` — slice methods so each sub-controller repaints only its region without a full re-render.

The view holds no business logic, imports no stores, and emits widget-local signals only — button clicks, verbosity selection, search text, clear, and the inline stability links — which `ProgressController` connects to service calls.

## 7. Factory wiring example

```python
# src/ollama_llm_bench/compose.py (excerpt)
progress = make_progress_widget(
    bus=event_bus,
    gateway=progress_gateway,
    log_formatter=log_formatter,
)
benchmark_workspace.set_center_panel(progress)
```

## 8. Dependency protocols

The widget consumes these interfaces; full method contracts live in `08_Cross_Cutting/08-E_interfaces_contracts.md`:

| Protocol | Used for |
|---|---|
| `EventBus` | owner-bound subscription to every live-update signal |
| `ProgressGateway` | The adapter gateway (08-E §7b.4) exposing the widget's run-control / read / log surface: `pause_run`/`resume_run`/`stop_run` for the active run, `run_metadata`/`rename_run`, `run_header` (elapsed time, header, terminal summary), `task_counters` (per-task counter reads), `load_past_log`, `get_setting`/`set_setting` for `ui.run_log_verbosity` and `ui.auto_scroll_run_log`, and `manual_provider_probe()`; wraps `BenchmarkFlowService`, `RunRegistryStore`, `RunsStore`, `ResultsStore`, `RunLogReader`, `SettingsStore`, and the manual provider-probe command (D-R-06). |
| `LogFormatter` | render an event into an HTML log line at a verbosity |
| model-/provider-stability | Delivered via the `_model_stability_changed` and progress events on the bus — the widget does NOT call `AdaptiveTimeoutService` or the breaker for stability (D-R-06). A manual provider probe is triggered through `ProgressGateway.manual_provider_probe()`, not a direct breaker call. (See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`, `08_CIRCUIT_BREAKER.md`.) |

**Adapter boundary (D-R-06).** The four sub-controllers depend only on `ProgressGateway` (plus the Event Bus and the retained `LogFormatter`), never on a backend Protocol — no `BenchmarkFlowService`, `RunRegistryStore`, `RunsStore`, `ResultsStore`, `RunLogReader`, or `SettingsStore` reaches the widget (08-A §5/§6); the adapter holds those behind the gateway.

## 9. Test boundary

| Target | Location | Tested with |
|---|---|---|
| `select.py` pure functions | colocated `tests/` | plain pytest, no Qt |
| Each sub-controller | colocated `tests/test_*_controller.py` | fake `EventBus`, a fake `ProgressGateway`, and the fake `LogFormatter` from its module's `testing.py` |
| `ProgressView.apply` and slice methods | colocated `tests/test_view.py` | pytest-qt `qtbot`, asserting rendered text per view-model |
| Full widget assembly | top-level integration tests | qtbot driving a fake pipeline through a real event bus, asserting state transitions from `state_machine.md` |

Per-sub-controller test scenarios:

- **CountersController** — `counts_by_status` to counter mapping; stage-bar segment weighting; ETA from the rolling average; `judge_phase_active` toggling the judge-wait badge; coalescing of rapid `_progress_updated` events.
- **CurrentTaskController** — retry line appears in `error` tone on `_task_retry` and clears on `_task_completed`; timeout accumulation; task timer reset on `_inference_started`. **Inference progress sub-row** — hidden when no main inference is in flight; reset to sub-state A (waiting) on `_inference_started`; transitions to sub-state B (generating) on the first `_inference_progress` event with `context=BENCHMARK_TASK` and `first_token_received == True`; label updates on every subsequent `_inference_progress` (filtered to `BENCHMARK_TASK`); replaced/reset by the next task's `_inference_started`; verbosity-independent (no read of `ui.run_log_verbosity`); "approximation" marker shown when the pipeline's token-estimation source is the 4-char heuristic. **Judge progress sub-row** — hidden when no judge call is in flight; reset to sub-state A (judge waiting) on `_judge_started`; transitions to sub-state B (judge receiving) on the first `_inference_progress` event with `context=BENCHMARK_JUDGE` and `first_token_received == True`; label updates on every subsequent `_inference_progress` (filtered to `BENCHMARK_JUDGE`); hidden on `_judge_completed` / `_task_completed`; same verbosity-independence and approximation-marker rules. **Context filter** — `_inference_progress` events whose `context` is `RUN_ANALYSIS` or `PROVIDER_TEST` are ignored by this controller.
- **LogController** — verbosity re-render from cached raw events with no loss (EC-LOG-3); buffer cap trims from the top (EC-PERF-3); search filters and highlights; Clear empties the view but not the cache; file-write-failure warning (EC-LOG-1); past-run replay from the run-log reader.
- **StabilityController** — model band transitions ok to warn to excluded across the exclusion threshold (EC-PROV-4); provider band transitions closed to open to half-open (EC-PROV-3); the retry-probe link triggers a probe.
