---
id: STORY-055
title: Build the New Benchmark judge, advanced options, validation, and Start flow with the Run Summary dialog
status: ready
spec_clauses:
  - 02_New_Benchmark_Widget/description.md#44-judge
  - 02_New_Benchmark_Widget/description.md#47-advanced-options
  - 02_New_Benchmark_Widget/description.md#6-validation-rules
  - 02_New_Benchmark_Widget/description.md#48-start-button
  - 07_Common_Dialogs/run_summary_dialog.md#6-per-mode-contents
  - 07_Common_Dialogs/run_summary_dialog.md#8-preflight-re-check-on-open
  - 07_Common_Dialogs/run_summary_dialog.md#12-start-effects
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/new_benchmark/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-055-AC-1
  - STORY-055-AC-2
  - STORY-055-AC-3
  - STORY-055-AC-4
  - STORY-055-AC-5
  - STORY-055-AC-6
  - STORY-055-AC-7
  - STORY-055-AC-8
edge_cases:
  - EC-RUN-1
  - EC-RUN-3
  - EC-TASK-2
  - EC-PROV-6
depends_on:
  - STORY-049
  - STORY-051
  - STORY-052
  - STORY-054
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-055 — Build the New Benchmark judge, advanced options, validation, and Start flow with the Run Summary dialog

## Goal

Complete the New Benchmark panel: the Judge section (analysis toggle plus the shared
provider/model dropdowns and the `GRADED` embedding status row), the collapsible Advanced
Options section of per-run setting overrides, the Run Validator wiring that gates the Start
button, the single-inference-gate binding on Start, and the Run Summary confirmation dialog
that opens on Start and issues the run through the gateway. After this story the widget can
assemble a `RunStartRequest` and launch a run.

## In scope

- `_internal/judge_section.py`: the "Generate run analysis" toggle with its per-mode default,
  the shared `ui/shared/provider_dropdown` and `ui/shared/model_dropdown` wired together (the
  model dropdown filtered to non-embedding chat-capable models), the Refresh action, and the
  `GRADED`-only embedding status row.
- `_internal/advanced_options.py`: the activation-checkbox-gated collapsible section whose
  controls are seeded from `NewBenchmarkGateway.get_setting`, carried on the request only when
  changed (DD-47 carriage rule), and the timeout-pair validation.
- The Run Validator wiring: hard-error / soft-warning entries recomputed on every configuration
  change, and the Start button enablement gated on no hard error AND the single-inference gate
  being `IDLE` (subscribing to `_inference_activity_changed`).
- The Start flow: build the `RunStartRequest`, open the Run Summary dialog, and on Accept issue
  `NewBenchmarkGateway.start_run(request)`; the Locked transition on `_run_started`.
- `ui/common_dialogs/` Run Summary dialog factory: the mode-aware review dialog with its
  preflight re-check on open, the Work-to-be-done line, the settings-snapshot transparency
  sections, the Warnings callout, and the Back / Start Benchmark buttons.

## Out of scope

- The mode selector, section-visibility engine, selection store, task files, and test models —
  delivered by STORY-054, which this story builds on.
- The concrete `RunValidator`, `ProviderRegistry`, and pipeline — consumed as Protocols/gateway.
- Wiring the concrete `NewBenchmarkGateway` and mounting the dialog factory in `compose.py` —
  this story **must not touch** `compose.py` (Phase 11 owns it).

## Spec inputs

- `02_New_Benchmark_Widget/description.md#44-judge` — the analysis toggle defaults per mode, the
  greyed-vs-hidden dropdown rule, the shared-dropdown wiring, and the embedding status row.
- `02_New_Benchmark_Widget/description.md#47-advanced-options` — the activation-checkbox gating,
  the per-run override seeding, the completeness rule, and the carriage rule.
- `02_New_Benchmark_Widget/description.md#6-validation-rules` — the hard-error / soft-warning
  table the Run Validator produces and how each maps onto the Start button.
- `02_New_Benchmark_Widget/description.md#48-start-button` — the enablement gate (no hard error
  AND `InferenceActivityStore` `IDLE`) and the open-Run-Summary-then-start sequence.
- `07_Common_Dialogs/run_summary_dialog.md#6-per-mode-contents` — the per-mode section content
  the dialog renders.
- `07_Common_Dialogs/run_summary_dialog.md#8-preflight-re-check-on-open` — the on-open re-check
  that refuses to open on a broken environment.
- `07_Common_Dialogs/run_summary_dialog.md#12-start-effects` — the create-run / start-pipeline /
  emit-run-started sequence on Start Benchmark.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway` — `start_run`,
  `readiness_snapshot`, `get_setting` / `set_setting` used by this half.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store` — the gate the
  Start button binds to; the button is `IDLE`-only.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only; no `setStyleSheet`, no colour literal.

## Design constraints

- The controller depends only on its `NewBenchmarkGateway` Protocol plus the declared non-store
  helpers; the Judge dropdowns consume the shared widgets and their `ProviderRegistry` Protocol
  through those widgets, not directly (D-R-06).
- Only the setting keys the user changed from the seeded value are carried on
  `RunStartRequest.setting_overrides`; an unchanged key is not carried (DD-47).
- The judge model dropdown is driven by the sibling provider dropdown via
  `set_provider(provider_id)`; the two widgets carry no coupling.
- The Run Summary dialog presents and re-checks only; it never edits configuration.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-055-AC-1

For each `RunMode`, the "Generate run analysis" toggle initialises to the specified default:

| RunMode   | Analysis toggle default |
| --------- | ----------------------- |
| SYNTHETIC | OFF                     |
| TASKS     | OFF                     |
| GRADED    | ON                      |

### STORY-055-AC-2

Given the Judge section, when the user selects a judge provider, then the judge model dropdown
is repopulated from that provider via `set_provider(provider_id)` and lists only non-embedding
chat-capable models.

### STORY-055-AC-3

Given the Advanced Options activation checkbox is unchecked, when a `RunStartRequest` is
assembled, then `advanced_options_overridden` is false and no per-run override is carried; and
given the checkbox is checked and the user changed exactly one control from its seeded value,
then only that one changed key appears in the request's setting overrides.

### STORY-055-AC-4

For each Run Validator condition, the Start button reflects the produced severity:

| Condition                                           | Start button          |
| --------------------------------------------------- | --------------------- |
| 0 models selected                                   | disabled (hard error) |
| TASKS/GRADED with no task files                     | disabled (hard error) |
| Maximum timeout < minimum timeout                   | disabled (hard error) |
| No enabled judge provider while a judge is required | disabled (hard error) |
| Only a streaming-unconfirmed soft warning           | enabled               |
| No validation entries                               | enabled               |

### STORY-055-AC-5

Given the configuration has no hard error, when a `_inference_activity_changed` event reports
the gate held by any activity, then the Start button is disabled with the in-flight tooltip;
and when the gate returns to `IDLE`, the Start button re-enables.

### STORY-055-AC-6

Given a valid configuration, when the user clicks Start Benchmark and confirms the Run Summary
dialog, then `NewBenchmarkGateway.start_run(request)` is called once with the assembled request,
and on the subsequent `_run_started` event the widget transitions to its read-only Locked
state.

### STORY-055-AC-7

Given the Run Summary dialog is asked to open, when its preflight re-check detects that no test
model is reachable, then the dialog does not open and the "No test model is reachable" outcome
is surfaced, leaving every field value on the widget intact.

### STORY-055-AC-8

Given the Run Summary dialog is constructed via its own factory function
(`make_run_summary_dialog`) with a fake `NewBenchmarkGateway` and mounted under `qtbot`, when it
is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), then no
exception is raised, the dialog reports `isVisible()`, and no `error`/`critical`-level
`structlog` record is captured — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-055-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_judge_section.py`,
  `test_analysis_toggle_default_per_mode`.
- STORY-055-AC-2 — unit (`pytest-qt`, fake shared dropdowns), same file,
  `test_judge_model_dropdown_follows_provider`.
- STORY-055-AC-3 — unit, colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_advanced_options.py`,
  `test_only_changed_overrides_are_carried`.
- STORY-055-AC-4 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_validation_and_start.py`,
  `test_start_button_reflects_validator_severity`. Covers EC-RUN-3, EC-TASK-2, EC-PROV-6.
- STORY-055-AC-5 — unit (`pytest-qt`), same file,
  `test_start_button_gated_on_inference_activity`. Covers EC-RUN-1.
- STORY-055-AC-6 — integration (`pytest-qt`),
  `tests/integration/test_new_benchmark_start.py`,
  `test_confirm_run_summary_starts_run_and_locks`.
- STORY-055-AC-7 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_run_summary_dialog.py`,
  `test_preflight_recheck_refuses_open_when_no_model_reachable`.
- STORY-055-AC-8 — unit (`pytest-qt`, fake `NewBenchmarkGateway`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_run_summary_dialog.py`,
  `test_run_summary_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-055.
- [ ] EC-RUN-1, EC-RUN-3, EC-TASK-2, and EC-PROV-6 each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the widget-level and
  Judge-section sub-machine states of `02_New_Benchmark_Widget/state_machine.md` and the Run
  Summary dialog state machine.
- [ ] An architecture test confirms the controller and the dialog depend only on
  `NewBenchmarkGateway` (via the widget) and consume `ProviderRegistry` only through the
  shared dropdowns; that the modules reference no `setStyleSheet`, embed no colour literal,
  and import no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/new_benchmark/` and
  `ui/common_dialogs/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-055.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
