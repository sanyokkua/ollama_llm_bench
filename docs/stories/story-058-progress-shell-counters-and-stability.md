---
id: STORY-058
title: Build the Progress widget shell, run controls, counters, stage bar, and stability sub-controllers
status: done
spec_clauses:
  - 04_Progress_Widget/description.md#3-header-row
  - 04_Progress_Widget/description.md#4-run-progress-counters
  - 04_Progress_Widget/description.md#5-stage-progress-bar
  - 04_Progress_Widget/description.md#6-model-panel-and-stability-indicators
  - 04_Progress_Widget/description.md#12-event-bus-integration
  - 04_Progress_Widget/implementation_structure.md#3-controller-split-rationale
  - 04_Progress_Widget/implementation_structure.md#41-counterscontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/progress/
acceptance_criteria:
  - STORY-058-AC-1
  - STORY-058-AC-2
  - STORY-058-AC-3
  - STORY-058-AC-4
  - STORY-058-AC-5
  - STORY-058-AC-6
  - STORY-058-AC-7
edge_cases:
  - EC-RUN-2
  - EC-PROV-3
  - EC-PROV-4
  - EC-PROV-4b
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-058 — Build the Progress widget shell, run controls, counters, stage bar, and stability sub-controllers

## Goal

Deliver the Progress widget's shell and its two lowest-fan-out sub-controllers: the header
(stage badge, run name, rename pencil, Pause/Resume, Stop with confirmation), the parent
`ProgressController` that owns and routes to the four sub-controllers, the `CountersController`
(counters, stage progress bar, per-stage badges, ETA, model identification), and the
`StabilityController` (the model- and provider-stability callouts and the judge-model exclusion
callout). The CurrentTask and Log sub-controllers are added by STORY-059 and STORY-060.

## In scope

- `ui/progress/protocols.py`: the `ProgressGateway` Protocol declared locally with the exact
  method signatures of 08-E §7b.4 (pause/resume/stop, run metadata/header, task counters,
  past-log load, run-log settings get/set, manual provider probe, rename).
- `ui/progress/api.py`: `make_progress_widget(...) -> QWidget` and the parent
  `ProgressController` that constructs the four sub-controllers and applies the state-machine
  transitions.
- The header pieces: stage badge, run-name label, rename-pencil (visible only while the run is
  actively executing), Pause/Resume toggle, and Stop with its confirmation modal and the
  draining sub-state status line.
- `_internal/counters_controller.py`: subscribes `_progress_updated`, `_stage_changed`,
  `_run_started`; derives per-`ResultStatus` counters, stage-bar segment weights, badge counts,
  ETA, and the provider/model labels; coalesces rapid `_progress_updated` events.
- `_internal/stability_controller.py`: subscribes `_model_stability_changed` and
  `_judge_model_excluded`; derives the model band (ok/warn/excluded), the provider band
  (closed/warn/open), and the persistent red judge-exclusion callout.

## Out of scope

- The Current-task section and its inference/judge progress sub-rows — owned by STORY-059.
- The run event-log panel — owned by STORY-060.
- The `AdaptiveTimeoutService` / circuit breaker reads — stability arrives via bus events; the
  manual probe is triggered through `ProgressGateway.manual_provider_probe()`, not a direct
  breaker call.
- Wiring the concrete `ProgressGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `04_Progress_Widget/description.md#3-header-row` — the stage badge colour table, the
  rename-pencil visibility, the Pause vs Stop semantics, the Stop confirmation, and the draining
  status lines.
- `04_Progress_Widget/description.md#4-run-progress-counters` — the counter keys, their sources,
  and the refresh on `_progress_updated`.
- `04_Progress_Widget/description.md#5-stage-progress-bar` — the segment tones, the
  `counts_by_status` derivation, and the full-completion success fill.
- `04_Progress_Widget/description.md#6-model-panel-and-stability-indicators` — the test-model
  callout bands, the judge-model exclusion callout, and the provider-breaker callout bands.
- `04_Progress_Widget/description.md#12-event-bus-integration` — the subscribed events and their
  handler effects.
- `04_Progress_Widget/implementation_structure.md#3-controller-split-rationale` — the four-way
  controller split this widget requires because of its subscription count.
- `04_Progress_Widget/implementation_structure.md#41-counterscontroller` — the Counters
  sub-controller's concern, subscriptions, derivations, and coalescing.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway` — the gateway surface this
  widget's `protocols.py` declares.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only; colour never conveys state alone.

## Design constraints

- Each sub-controller depends only on `ProgressGateway`, `EventBus`, and `LogFormatter`; none
  holds a backend store/service Protocol (D-R-06).
- The parent is a thin router: it owns each subscription's disposable, applies the
  `state_machine.md` transitions, and forwards run-control clicks; it holds no business logic.
- The draining sub-states arm a bounded reconciliation timeout so `Pausing…`/`Stopping…` can
  never hang if a terminal event is lost (SPEC-098).
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-058-AC-1

For each pipeline stage, the header stage badge renders the specified tone and always carries
the stage name text:

| Stage                                      | Tone    |
| ------------------------------------------ | ------- |
| INITIALIZING                               | info    |
| INFERENCE                                  | primary |
| KEYWORD_CHECK / COSINE_CHECK / JUDGE_CHECK | warn    |
| COMPLETED                                  | success |
| FAILED                                     | error   |
| STOPPED / PAUSED                           | mute    |

### STORY-058-AC-2

Given a run is actively executing, when the widget renders the header, then the rename pencil is
visible and Pause and Stop are enabled; and when the displayed run is a terminal or past run,
then the rename pencil is hidden and Pause/Resume and Stop are disabled.

### STORY-058-AC-3

Given the run is executing, when the user clicks Stop, then the Stop confirmation modal is shown
before any pipeline call, and only on Confirm is `ProgressGateway.stop_run(...)` invoked.

### STORY-058-AC-4

Given a `_progress_updated` event carrying a `counts_by_status` map, when the CountersController
derives its view-model, then each counter equals the map value for its `ResultStatus`, the
Failed counter equals the sum of the five terminal-failure statuses, and the stage-bar segment
weights derive from the same map.

### STORY-058-AC-5

Given a burst of consecutive `_progress_updated` events, when the CountersController processes
them, then it coalesces the burst and the last payload wins for the refreshed counters.

### STORY-058-AC-6

For each model- and provider-stability condition, the StabilityController derives the specified
band:

| Signal                                               | Band                                                    |
| ---------------------------------------------------- | ------------------------------------------------------- |
| no consecutive max-timeout failures (role=INFERENCE) | model band "ok"                                         |
| below the exclusion threshold                        | model band "warn"                                       |
| role=INFERENCE exclusion reached                     | model band "excluded"                                   |
| `_judge_model_excluded` received                     | red judge-exclusion callout shown, persists for the run |
| breaker CLOSED                                       | provider band "closed"                                  |
| breaker OPEN                                         | provider band "open" with retry-probe link              |

### STORY-058-AC-7

Given the widget is constructed via its own factory function (`make_progress_widget`) with a
fake `ProgressGateway` (and fakes for the declared collaborators `EventBus` and `LogFormatter`)
and mounted under `qtbot`, when it is shown (`qtbot.addWidget(...)`, `.show()`, one
`qtbot.wait(0)`/event-loop pump), then no exception is raised, the widget reports `isVisible()`,
and no `error`/`critical`-level `structlog` record is captured — verified by wrapping
construction+show in `structlog.testing.capture_logs()` and asserting no captured entry's
`log_level` is in `{"error", "critical"}`.

## Test plan

- STORY-058-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/progress/tests/test_view.py`,
  `test_stage_badge_tone_and_text_per_stage`.
- STORY-058-AC-2 — unit (`pytest-qt`), same file,
  `test_header_controls_visibility_per_run_state`.
- STORY-058-AC-3 — unit (`pytest-qt`, fake `ProgressGateway`), colocated
  `src/ollama_llm_bench/ui/progress/tests/test_controller.py`,
  `test_stop_requires_confirmation_before_stop_run`. Covers EC-RUN-2.
- STORY-058-AC-4 — unit, colocated
  `src/ollama_llm_bench/ui/progress/tests/test_counters_controller.py`,
  `test_counts_by_status_maps_to_counters_and_segments`.
- STORY-058-AC-5 — unit, same file, `test_progress_updated_bursts_coalesce`.
- STORY-058-AC-6 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/progress/tests/test_stability_controller.py`,
  `test_stability_bands_per_signal`. Covers EC-PROV-3, EC-PROV-4, EC-PROV-4b.
- STORY-058-AC-7 — unit (`pytest-qt`, fake `ProgressGateway`), colocated
  `src/ollama_llm_bench/ui/progress/tests/test_view.py`,
  `test_progress_widget_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-058.
- [ ] EC-RUN-2, EC-PROV-3, EC-PROV-4, and EC-PROV-4b each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Empty, Initializing,
  Running, Paused, Stopping, and ViewingPastRun states of `04_Progress_Widget/state_machine.md`
  that the shell/counters/stability own.
- [ ] An architecture test confirms every sub-controller depends only on `ProgressGateway`
  (plus `EventBus` and `LogFormatter`) and not on `AdaptiveTimeoutService` or a breaker, and
  that the module references no `setStyleSheet`, embeds no colour literal, and imports no
  `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/progress/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-058.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes (post-review defect-fix pass)

- Fixed: the header stage badge is now pushed to the correct terminal/paused `RunStage` by
  `ProgressController` on `_run_paused`/`_run_resumed`/`_run_stopped`/`_run_finished`/
  `_run_failed` and on SPEC-098 reconciliation (`CountersController.set_stage`/
  `resume_live_stage`), since the pipeline's own `_stage_changed` never emits those five values.
- Fixed: Pause/Stop are now hidden (`HeaderAffordances.pause_resume_visible`/`stop_visible`),
  not merely disabled, in the `Empty`/`ViewingPastRun` states, matching `state_machine.md` §4
  and the no-placeholder-UI rule.
- Fixed: the SPEC-098 draining status line (`"Pausing — finishing the current call…"` /
  `"Stopping — cancelling the current call…"`, `description.md` §3.4's exact wording) is now
  rendered in the header and cleared on settle (terminal event or reconciliation timeout).
- Fixed (minor finding): the SPEC-098 reconciliation timeout now reconciles to the *specific*
  terminal/paused display (`RunStage.COMPLETED`/`FAILED`/`STOPPED`/`PAUSED`, read from
  `run_header(run_id).status` via `terminal_stage_for_run_status`, or `RunStage.PAUSED` when
  the drain was a Pause and the run is still active) rather than only the generic
  Running/ViewingPastRun buckets.
- Deferred (minor finding, by design): the reconciliation timeout stays a fixed
  `_DEFAULT_RECONCILE_TIMEOUT_MS = 5000` rather than being derived from
  `provider.hard_cancel_max_ms + margin`. `hard_cancel_max_ms` is a field on each concrete
  provider adapter's own client-config struct (`provider_openai_compatible`/`provider_anthropic`/
  `provider_gemini` `models.py`), not something any existing Gateway or settings surface
  resolves for "the currently active provider of this run" — determining it correctly would
  require `ProgressGateway` to resolve the live provider from the last-known
  `current_provider_id` and read its client config, a materially larger surface change than a
  narrow accessor addition, and arguably outside this widget's D-R-06 collaborator set
  (`ProgressGateway`/`EventBus`/`LogFormatter`). Left as a fixed, generously-bounded constant;
  a future story can add a purpose-built accessor if this needs to track the real per-provider
  bound.
