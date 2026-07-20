---
id: STORY-059
title: Build the Progress widget Current-task sub-controller with the inference and judge progress sub-rows
status: ready
spec_clauses:
  - 04_Progress_Widget/description.md#7-current-task-section
  - 04_Progress_Widget/description.md#71-inference-progress-row-and-judge-progress-row
  - 04_Progress_Widget/implementation_structure.md#42-currenttaskcontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#69-live-inference-progress-emission
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#41a-inferenceprogressevent--_inference_progress
modules:
  - ui/progress/
  - backend/events/
acceptance_criteria:
  - STORY-059-AC-1
  - STORY-059-AC-2
  - STORY-059-AC-3
  - STORY-059-AC-4
  - STORY-059-AC-5
  - STORY-059-AC-6
edge_cases:
  - EC-RUN-17
  - EC-RUN-18
  - EC-RUN-19
  - EC-RUN-23
  - EC-PROV-1
depends_on:
  - STORY-049
  - STORY-058
adrs:
  - ADR-0001
  - ADR-0008
  - ADR-0009
owner: coder
estimate: L
---

# STORY-059 — Build the Progress widget Current-task sub-controller with the inference and judge progress sub-rows

## Goal

Deliver the `CurrentTaskController`: the in-flight task grid (task id, stage, task time,
timeouts, the classified retry line) and the two live progress sub-rows — the Inference
progress sub-row (`context=BENCHMARK_TASK`) and the Judge progress sub-row
(`context=BENCHMARK_JUDGE`) — each with its waiting/generating sub-states, its reset and
visibility discipline, and the approximation marker when the token count is heuristic.

## In scope

- `_internal/current_task_controller.py`: subscribes `_inference_started`,
  `_inference_progress`, `_judge_started`, `_judge_completed`, `_task_completed`, `_task_retry`;
  derives the `CurrentTaskViewModel`.
- The `_inference_progress` context filter (accept only `BENCHMARK_TASK` and `BENCHMARK_JUDGE`;
  ignore `RUN_ANALYSIS` and `PROVIDER_TEST`).
- The Inference progress sub-row: sub-state A (waiting for first token) and sub-state B
  (generating), shown/reset on `_inference_started`, hidden on `_task_completed`, showing the
  `(complete — main inference finished)` placeholder during the judge phase.
- The Judge progress sub-row: sub-state A (judge waiting) and sub-state B (judge receiving),
  shown/reset on `_judge_started`, hidden on `_judge_completed` / `_task_completed`.
- The retry line rendered in error tone with the classified reason while a retry is active, and
  cleared when the task finishes; the verbosity-independence of both sub-rows; the leading `~`
  approximation marker when the token-estimation source is the 4-character heuristic.
- The defensive ignore of an out-of-order `BENCHMARK_JUDGE` progress event for a result whose
  main inference has not completed.

## Out of scope

- The header, counters, stage bar, stability callouts, and the parent controller — owned by
  STORY-058.
- The run event-log panel — owned by STORY-060.
- Wiring the concrete `ProgressGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `04_Progress_Widget/description.md#7-current-task-section` — the Current-task grid fields, the
  circuit-breaker `waiting for probe` stage rendering, and the past-run/paused placeholders.
- `04_Progress_Widget/description.md#71-inference-progress-row-and-judge-progress-row` — the two
  sub-rows, their sub-states, the context filter, the reset/visibility rules, and the heuristic
  `~` marker.
- `04_Progress_Widget/implementation_structure.md#42-currenttaskcontroller` — the
  sub-controller's concern, its subscriptions, and the context-filter derivation.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway` — the gateway surface the
  Progress widget declares (this sub-controller uses no additional method).
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The sub-controller depends only on `ProgressGateway` and `EventBus`; it holds no backend
  store/service Protocol (D-R-06).
- Both progress sub-rows are verbosity-independent — they never read `ui.run_log_verbosity`.
- The two `_inference_progress` streams never overlap on one `result_id`; the sub-controller
  renders only the most recent event for the active result.
- `first_token_received` is monotonic per call — the sub-controller never flips a sub-row from
  B back to A within one call.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-059-AC-1

Given no main inference is in flight, when the Current-task section renders, then the Inference
progress sub-row is hidden; and given an `_inference_started` for the active task, then the
Inference progress sub-row is shown reset to sub-state A ("Waiting for first token — 0.0 s").

### STORY-059-AC-2

Given the Inference progress sub-row is in sub-state A, when an `_inference_progress` event with
`context=BENCHMARK_TASK` and `first_token_received == True` arrives, then the sub-row transitions
to sub-state B rendering the generating label with the token count and elapsed seconds from the
snapshot.

### STORY-059-AC-3

For each `_inference_progress` context, the Current-task controller either accepts or ignores it:

| context         | Accepted by CurrentTaskController |
| --------------- | --------------------------------- |
| BENCHMARK_TASK  | yes (Inference sub-row)           |
| BENCHMARK_JUDGE | yes (Judge sub-row)               |
| RUN_ANALYSIS    | no                                |
| PROVIDER_TEST   | no                                |

### STORY-059-AC-4

Given the active result has finished its main inference and a `_judge_started` fires, when the
section renders, then the Judge progress sub-row is shown in sub-state A and the Inference
progress sub-row shows the `(complete — main inference finished)` placeholder rather than being
hidden.

### STORY-059-AC-5

Given a `_task_retry` event for the active task, when the Current-task section renders, then the
retry line appears in error tone with the classified reason; and when a `_task_completed` event
follows, then the retry line clears.

### STORY-059-AC-6

Given the token-estimation source for the active call is the 4-character heuristic, when the
active sub-row renders its token count, then the count is prefixed with `~` to mark it as an
approximation.

## Test plan

- STORY-059-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/progress/tests/test_current_task_controller.py`,
  `test_inference_row_hidden_until_started_then_waiting`. Covers EC-RUN-18. Wrapped in
  `structlog.testing.capture_logs()`; asserts no captured entry's `log_level` is in
  `{"error", "critical"}`.
- STORY-059-AC-2 — unit, same file, `test_inference_row_transitions_to_generating`.
  Covers EC-RUN-19.
- STORY-059-AC-3 — table-driven unit, same file, `test_progress_context_filter`.
  Covers EC-RUN-23.
- STORY-059-AC-4 — unit (`pytest-qt`), same file,
  `test_inference_placeholder_during_judge_phase`.
- STORY-059-AC-5 — unit (`pytest-qt`), same file,
  `test_retry_line_appears_then_clears`. Covers EC-PROV-1.
- STORY-059-AC-6 — unit, same file, `test_heuristic_token_count_marked_with_tilde`.
  Covers EC-RUN-17.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-059.
- [x] EC-RUN-17, EC-RUN-18, EC-RUN-19, EC-RUN-23, and EC-PROV-1 each have a passing test.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the TaskInflight and
  progress-sub-row states of `04_Progress_Widget/state_machine.md`.
- [x] An architecture test confirms the sub-controller depends only on `ProgressGateway` and
  `EventBus`, reads no verbosity setting for the sub-rows, and that the module references no
  `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/progress/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-059.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes

This story includes a small additive backend change: the `tokens_estimated: bool = False` field
is added to `InferenceProgressEvent` in `backend/events/`. This change is purely additive — the
field is optional with a default value, so existing STORY-030/STORY-035 tests that construct
`InferenceProgressEvent` without it are unaffected by msgspec's evolution rules. The `backend/events/`
module is therefore cited in the `modules:` front-matter even though most of the story's implementation
is in the UI layer.

An independent spec-conformance review found that this field is not enumerated by
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7a or `08_Cross_Cutting/08-Q_event_payload_schemas.md`
§4.1a, and that `04_Progress_Widget/implementation_structure.md` §4.2's stated "the controller
infers it" mechanism is not implementable from the event payload alone (no per-chunk
`delta_tokens` history reaches the event). **ADR-0009** records the resulting decision: keep the
additive field, since it is the only implementable path to AC-6/EC-RUN-17, and the vendored spec
documents remain out of date relative to the shipped code until they are next revised upstream.

Note: the `backend/inference_progress/` module is missing entirely from
`docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md`, a pre-existing gap in
the vendored specification unrelated to this story.
