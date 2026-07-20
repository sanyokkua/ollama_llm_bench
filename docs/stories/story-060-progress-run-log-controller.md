---
id: STORY-060
title: Build the Progress widget run event-log sub-controller with verbosity, search, bounded buffer, and auto-scroll
status: done
spec_clauses:
  - 04_Progress_Widget/description.md#8-benchmark-event-log-panel
  - 04_Progress_Widget/description.md#83-event-kinds
  - 04_Progress_Widget/description.md#84-buffer-cap
  - 04_Progress_Widget/description.md#85-auto-scroll
  - 04_Progress_Widget/implementation_structure.md#43-logcontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/progress/
  - backend/domain/
  - backend/log_formatting/
acceptance_criteria:
  - STORY-060-AC-1
  - STORY-060-AC-2
  - STORY-060-AC-3
  - STORY-060-AC-4
  - STORY-060-AC-5
  - STORY-060-AC-6
edge_cases:
  - EC-LOG-1
  - EC-LOG-3
  - EC-PERF-3
  - EC-PROV-4a
depends_on:
  - STORY-049
  - STORY-058
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-060 — Build the Progress widget run event-log sub-controller with verbosity, search, bounded buffer, and auto-scroll

## Goal

Deliver the `LogController` and the run event-log panel: the verbosity dropdown (Short / Normal
/ Verbose) rendering each event through the log-formatting service from a cached raw-event
buffer, the case-insensitive search filter, the Clear-view action, the bounded display buffer
that drops oldest lines at the cap, the persisted auto-scroll behaviour, the log-write-failure
warning indicator, and the past-run log replay.

## In scope

- `_internal/log_controller.py`: subscribes the fifteen log-source events (`_inference_started`,
  `_inference_completed`, `_task_completed`, `_judge_started`, `_judge_completed`, `_task_retry`,
  `_stage_changed`, `_provider_switched`, `_model_switched`, `_run_stopped`, `_run_finished`,
  `_run_failed`, `_model_stability_changed`, `_provider_registry_reloaded`, `_log_cleared`);
  caches every raw event and renders one HTML line per event via `LogFormatter`.
- The verbosity control reading/persisting `ui.run_log_verbosity` and re-rendering from cache
  without data loss on change.
- The search filter, the Clear (view-only) action, the bounded buffer capped by
  `ui.run_log_max_lines` (dropping oldest), and the auto-scroll toggle persisted in
  `ui.auto_scroll_run_log`.
- The `file_write_warning` indicator surfaced when the run-log file writer fails.
- The past-run log replay through `ProgressGateway.load_past_log(run_id)` on `_run_id_changed`
  when no run is active.

## Out of scope

- The header, counters, stability, and Current-task sections — owned by STORY-058 and STORY-059.
- The `LogFormatter` implementation and the run-log file writer — consumed as Protocols/gateway.
- Wiring the concrete `ProgressGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `04_Progress_Widget/description.md#8-benchmark-event-log-panel` — the toolbar, the
  verbosity-aware field model, the event-kind tone mapping, and the pass/resume/judge-exclusion
  canonical log lines rendered through the formatter.
- `04_Progress_Widget/description.md#84-buffer-cap` — the `ui.run_log_max_lines` cap, the
  oldest-line eviction, and the guarantee the per-run file is never trimmed by the widget.
- `04_Progress_Widget/description.md#85-auto-scroll` — the follow-newest-line behaviour, the
  suspend-on-scroll-up rule, and the `ui.auto_scroll_run_log` persistence.
- `04_Progress_Widget/implementation_structure.md#43-logcontroller` — the sub-controller's
  concern, its fifteen subscriptions, the raw-event cache, and the past-run replay.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway` — `load_past_log`,
  `get_setting` / `set_setting` for the run-log settings.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles resolve each event-kind tone; the widget never builds the HTML itself.

## Design constraints

- The sub-controller depends only on `ProgressGateway`, `EventBus`, and `LogFormatter`; it holds
  no backend store/service Protocol (D-R-06).
- The widget never builds the HTML — it passes each event to `LogFormatter` and appends the
  returned line.
- The raw-event cache is retained so a verbosity change re-renders without loss; the per-run log
  file is never trimmed by the widget.
- The bounded buffer counts events and lines interchangeably; the oldest lines are evicted
  first.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-060-AC-1

Given a stream of pipeline events, when each arrives, then the panel appends exactly one line
produced by `LogFormatter` for that event at the active verbosity.

### STORY-060-AC-2

Given the panel holds cached raw events, when the user changes the verbosity dropdown, then the
panel re-renders every cached event at the new verbosity with no event lost, and persists the
new value to `ui.run_log_verbosity`.

### STORY-060-AC-3

Given the visible buffer is at `ui.run_log_max_lines`, when a further event is appended, then
the oldest line is removed from the top so the buffer stays at the cap.

### STORY-060-AC-4

Given the user clicks Clear, when the view clears, then the visible lines are removed but the
cached raw events are retained, so a subsequent verbosity change re-renders the full buffer.

### STORY-060-AC-5

Given the run-log file writer reports a write failure, when the panel renders, then the
log-write-failure warning indicator is shown and the panel keeps appending lines from the
in-memory buffer.

### STORY-060-AC-6

Given no run is active, when a `_run_id_changed` selects a past run, then the panel loads and
replays that run's saved log through `ProgressGateway.load_past_log(run_id)`.

## Test plan

- STORY-060-AC-1 — unit (`pytest-qt`, fake `LogFormatter`), colocated
  `src/ollama_llm_bench/ui/progress/tests/test_log_controller.py`,
  `test_one_line_per_event_via_formatter`. Covers EC-PROV-4a (the `task_judge_timeout` line).
  Wrapped in `structlog.testing.capture_logs()`; asserts no captured entry's `log_level` is in
  `{"error", "critical"}`.
- STORY-060-AC-2 — unit, same file, `test_verbosity_change_rerenders_from_cache`.
  Covers EC-LOG-3.
- STORY-060-AC-3 — unit, same file, `test_buffer_cap_evicts_oldest`. Covers EC-PERF-3.
- STORY-060-AC-4 — unit (`pytest-qt`), same file, `test_clear_empties_view_not_cache`.
- STORY-060-AC-5 — unit (`pytest-qt`), same file, `test_file_write_warning_indicator`.
  Covers EC-LOG-1.
- STORY-060-AC-6 — unit (`pytest-qt`, fake `ProgressGateway`), same file,
  `test_past_run_replay_loads_saved_log`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-060.
- [x] EC-LOG-1, EC-LOG-3, EC-PERF-3, and EC-PROV-4a each have a passing test.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the log-panel states of
  `04_Progress_Widget/state_machine.md`.
- [x] An architecture test confirms the sub-controller depends only on `ProgressGateway`,
  `EventBus`, and `LogFormatter`, never builds HTML itself, and that the module references no
  `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/progress/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-060.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes

Two lower-severity gaps were identified during a post-implementation spec-conformance review
and are recorded here as explicitly out of scope, per the project's "if something is genuinely
out of scope, say so explicitly" rule, rather than being silently implemented or silently
dropped:

- **Search does not highlight matches.** `04_Progress_Widget/description.md#8.1` (cited clause)
  says the search input should "filter visible lines and highlight matches"; this story's
  `filter_search` only filters -- no acceptance criterion in this story covers search behaviour
  at all, and no highlighting was implemented (the originally approved plan flagged this exact
  ambiguity and deferred confirming it against `mockup.html`). Recommend a fast-follow story/AC
  if highlighting is wanted.
- **`judge_started` and `judge_excluded` gaps.** `select_judge_started` reuses
  `RunLogEventKind.JUDGE` rather than a distinct kind (the authoritative enum in
  `10_Domain_and_Data/02_DTOS_AND_ENUMS.md §7.7` only defines `JUDGE`, so this follows the
  authoritative source over `04_Progress_Widget/description.md#8.3`'s table, which lists them
  separately -- a pre-existing spec inconsistency, not a coder defect). `judge_excluded` (tied
  to EC-PROV-4b, which is **not** in this story's `edge_cases:` list) is entirely unimplemented
  here -- no enum member, no tone entry, no `LogController` subscription -- and should be picked
  up by whichever future story owns EC-PROV-4b.
