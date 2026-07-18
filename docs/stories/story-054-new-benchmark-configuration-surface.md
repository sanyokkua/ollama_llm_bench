---
id: STORY-054
title: Build the New Benchmark configuration surface — mode selector, section visibility, selection store, task files, and test models
status: ready
spec_clauses:
  - 02_New_Benchmark_Widget/description.md#3-run-modes-and-the-mode-selector
  - 02_New_Benchmark_Widget/description.md#5-behaviour-per-element
  - 02_New_Benchmark_Widget/description.md#46-test-models
  - 02_New_Benchmark_Widget/description.md#12-section-visibility-decision-table
  - 02_New_Benchmark_Widget/state_machine.md#3-test-models-multi-provider-sub-machine
  - 02_New_Benchmark_Widget/state_machine.md#4-task-files-sub-machine
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#62-the-policy-table
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/new_benchmark/
acceptance_criteria:
  - STORY-054-AC-1
  - STORY-054-AC-2
  - STORY-054-AC-3
  - STORY-054-AC-4
  - STORY-054-AC-5
  - STORY-054-AC-6
  - STORY-054-AC-7
edge_cases:
  - EC-TASK-1
  - EC-TASK-3
  - EC-TASK-8
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-054 — Build the New Benchmark configuration surface — mode selector, section visibility, selection store, task files, and test models

## Goal

Deliver the interactive core of the New Benchmark panel: the three-mode radio selector that
persists `benchmark.last_mode`, the data-driven section-visibility engine that shows or hides
each section per the Mode Visibility Policy, the in-memory multi-provider `(provider, model)`
selection store, the Task Files section with drag-drop and per-file task-count badges, and the
Test Models section. This is the widget's skeleton and its two workload-input sections, on top
of which the judge/advanced/validation/start half (STORY-055) is built.

## In scope

- `ui/new_benchmark/protocols.py`: the `NewBenchmarkGateway` Protocol declared locally with the
  exact method signatures of 08-E §7b.2 (`get_setting` / `set_setting`, `provider_list`,
  `readiness_snapshot`, `start_run`).
- `ui/new_benchmark/api.py`: `make_new_benchmark_widget(...) -> QWidget` scaffolding the
  controller, view, and the `_internal/` section modules; the section public surface exists but
  the judge/advanced/start behaviours are stubbed for STORY-055.
- `_internal/mode_selector.py`: the radio list restoring and persisting `benchmark.last_mode`
  and emitting `mode_changed`.
- The section-visibility engine driving the visible-section set from `ModeVisibilityPolicy`.
- `_internal/selection_store.py`: the in-memory ordered `(provider_id, model_name)` set,
  preserved across provider switches.
- `_internal/task_files.py`: the Task Files list, drag-drop of YAML files/folders, Add File /
  Add Folder / Remove, and the per-file `(N tasks)` badge read from `TaskFileLoader`.
- `_internal/test_models.py`: the browsed-provider dropdown, the available-models toggle list,
  Select All / Clear All, and the selected-models summary.

## Out of scope

- The Judge section, the embedding status row, the Advanced Options section, the Run Validator
  wiring, the Start button, and the Run Summary dialog — owned by STORY-055.
- The `ProviderRegistry`, `TaskFileLoader`, and `ModeVisibilityPolicy` concrete
  implementations — consumed as Protocols; owned by earlier phases.
- Wiring the concrete `NewBenchmarkGateway` — done in `compose.py`, which this story **must not
  touch** (Phase 11 owns `compose.py`).

## Spec inputs

- `02_New_Benchmark_Widget/description.md#3-run-modes-and-the-mode-selector` — the three
  `RunMode` values, the fixed display order, and the `benchmark.last_mode` persistence and
  restore rules.
- `02_New_Benchmark_Widget/description.md#5-behaviour-per-element` — the enablement and effect of
  the Task Files controls (Add File / Add Folder / Remove / drop) and the Test Models controls
  per element and per mode.
- `02_New_Benchmark_Widget/description.md#46-test-models` — the multi-provider picker, the
  hide-embedding filter, Select All / Clear All, and the preserved cross-provider selection.
- `02_New_Benchmark_Widget/description.md#12-section-visibility-decision-table` — the per-mode
  visible-section matrix the visibility engine must reproduce via the policy.
- `02_New_Benchmark_Widget/state_machine.md#3-test-models-multi-provider-sub-machine` — the
  selection-store state transitions across provider switches.
- `02_New_Benchmark_Widget/state_machine.md#4-task-files-sub-machine` — the empty-drop-zone vs
  populated states.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway` — the exact gateway
  surface this widget's `protocols.py` declares.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#62-the-policy-table` — the
  `(mode, flags) -> visible section set` contract the widget consumes; it never hard-codes
  per-mode conditionals.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` —
  appearance comes from theme roles only.

## Design constraints

- The controller depends only on its own `NewBenchmarkGateway` Protocol plus the non-store
  helpers (`EventBus`, `TaskFileLoader`, `ModeVisibilityPolicy`, `WorkspaceController`); it holds
  no `ProviderRegistry`, `SettingsStore`, or `ReadinessService` directly (D-R-06).
- Section visibility is computed exclusively via `ModeVisibilityPolicy`; no `if mode ==` branch
  decides section presence.
- `provider_id` (UUID4) is the selection key; the picker displays the provider's user-facing
  `name`, never the id.
- No `setStyleSheet` and no colour literal outside `ui/theme/` (ADR-0001); no `asyncio`.
- The `SelectionStore` is widget-local, not a shared backend store.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-054-AC-1

Given the widget is constructed with `benchmark.last_mode` reading `TASKS`, when the mode
selector initialises, then `TASKS` is the selected mode; and when the user selects a different
mode, then `NewBenchmarkGateway.set_setting("benchmark.last_mode", <value>)` is called with the
newly selected mode.

### STORY-054-AC-2

For each `RunMode`, the visible-section set the widget renders equals the set the Mode
Visibility Policy returns for that mode:

| Section              | SYNTHETIC | TASKS   | GRADED  |
| -------------------- | --------- | ------- | ------- |
| Performance Matrix   | visible   | hidden  | hidden  |
| Task Files           | hidden    | visible | visible |
| Embedding status row | hidden    | hidden  | visible |
| Test Models          | visible   | visible | visible |

### STORY-054-AC-3

Given the user has selected models from provider A, when the user switches the browsed provider
to B and selects a model, then the selection store contains the models from both A and B, and
the selected-models summary lists every selected `provider · model` pair.

### STORY-054-AC-4

Given `mode` is `TASKS` or `GRADED`, when a valid YAML task file is added (by Add File or by
drop), then a row is appended showing the file name and a `(N tasks)` badge whose count equals
`TaskFileLoader`'s parsed task count for that file.

### STORY-054-AC-5

Given the Test Models section is browsing a provider, when the user clicks Clear All, then
every one of that browsed provider's `(provider, model)` pairs is removed from the selection
store while any pairs from other providers are left unchanged.

### STORY-054-AC-6

Given a folder is chosen through Add Folder that contains no `.yaml` or `.yml` file, when the
add completes, then no Task Files row is added and the widget surfaces the "no YAML files
found" message.

### STORY-054-AC-7

Given the widget is constructed via its own factory function (`make_new_benchmark_widget`) with
a fake `NewBenchmarkGateway` (and fakes for the declared non-store helpers `EventBus`,
`TaskFileLoader`, `ModeVisibilityPolicy`, and `WorkspaceController`) and mounted under `qtbot`,
when it is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), then
no exception is raised, the widget reports `isVisible()`, and no `error`/`critical`-level
`structlog` record is captured — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-054-AC-1 — unit (`pytest-qt`, fake `NewBenchmarkGateway`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_mode_selector.py`,
  `test_restores_and_persists_last_mode`.
- STORY-054-AC-2 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_section_visibility.py`,
  `test_visible_sections_match_policy_per_mode`.
- STORY-054-AC-3 — unit, colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_selection_store.py`,
  `test_selection_preserved_across_provider_switch`.
- STORY-054-AC-4 — unit (`pytest-qt`, fake `TaskFileLoader`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_task_files.py`,
  `test_added_file_shows_task_count_badge`. Covers EC-TASK-1, EC-TASK-3.
- STORY-054-AC-5 — unit, `test_selection_store.py`,
  `test_clear_all_scopes_to_browsed_provider`.
- STORY-054-AC-6 — unit (`pytest-qt`), `test_task_files.py`,
  `test_empty_folder_adds_no_row`. Covers EC-TASK-8.
- STORY-054-AC-7 — unit (`pytest-qt`, fake `NewBenchmarkGateway`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_smoke.py`,
  `test_new_benchmark_widget_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-054.
- [ ] EC-TASK-1, EC-TASK-3, and EC-TASK-8 each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises every state in the Test
  Models and Task Files sub-machines of `02_New_Benchmark_Widget/state_machine.md`.
- [ ] An architecture test confirms the controller depends only on `NewBenchmarkGateway` (plus
  the declared non-store helpers), that section visibility is resolved via
  `ModeVisibilityPolicy`, and that the module references no `setStyleSheet`, embeds no
  colour literal, and imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/new_benchmark/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-054.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
