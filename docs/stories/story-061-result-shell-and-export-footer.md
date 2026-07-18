---
id: STORY-061
title: Build the Result widget shell — run selector, tab strip, per-run view-state store, and the export footer
status: ready
spec_clauses:
  - 05_Result_Widget/description.md#4-tab-strip-and-the-four-tabs
  - 05_Result_Widget/description.md#51-per-tab-export-button-cluster
  - 05_Result_Widget/description.md#52-save-destination-toggle-and-open-exports-folder
  - 05_Result_Widget/description.md#6-run-selection-logic
  - 05_Result_Widget/description.md#7-view-only-during-run-rule
  - 05_Result_Widget/description.md#9-per-run-table-and-chart-view-state
  - 05_Result_Widget/description.md#12-event-bus-integration
  - 05_Result_Widget/implementation_structure.md#4-parent-controller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/results/
acceptance_criteria:
  - STORY-061-AC-1
  - STORY-061-AC-2
  - STORY-061-AC-3
  - STORY-061-AC-4
  - STORY-061-AC-5
  - STORY-061-AC-6
  - STORY-061-AC-7
edge_cases:
  - EC-RES-5
  - EC-RES-6
  - EC-WS-1
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-061 — Build the Result widget shell — run selector, tab strip, per-run view-state store, and the export footer

## Goal

Deliver the Result widget's parent shell: the header run-selector dropdown, the four-tab strip
(persisting the selected tab), the parent `ResultController` with run-selection and the
user-locked-selection flag, the `PerRunViewStateStore` that hands each tab its per-run slice,
and the uniform export footer (`FooterController`) — the per-tab export cluster, the shared
save-destination toggle, and the Open-Exports-Folder button. This is the container the four tab
stories mount into.

## In scope

- `ui/results/protocols.py`: the `ResultGateway` Protocol declared locally with the exact method
  signatures of 08-E §7b.5.
- `ui/results/api.py`: `make_result_widget(...) -> QWidget` and `ResultView` (header, tab strip,
  footer host, tab-body host).
- `_internal/controller.py` (`ResultController`): the selected run id, the user-locked-selection
  flag, subscriptions (`_run_list_changed`, `_run_id_changed`, `_run_renamed`, `_run_started`,
  terminal events, `_app_settings_changed`), and the run-selector auto-jump rule.
- `_internal/view_state_store.py` (`PerRunViewStateStore`): per-`run_id` slice storage, the
  mode-default-on-first-open vs restore-on-reopen rule, persisted through the gateway.
- `_internal/footer.py` (`FooterController`): the content-kind-driven export cluster, the shared
  `ui.export_save_directly` toggle, the Open-Exports-Folder visibility, the view-only-during-run
  disable rule, and the empty-run "nothing to export" disable.
- The four tab sub-controllers are constructed and mounted here as placeholders; their tab
  bodies are delivered by STORY-062..065.

## Out of scope

- The Summary, Details, Charts, and Run Analysis tab bodies and their sub-controller logic —
  owned by STORY-062, STORY-063, STORY-064, STORY-065.
- The chart aggregation, table serialisation, and run-analysis services — consumed behind the
  gateway.
- Wiring the concrete `ResultGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `05_Result_Widget/description.md#4-tab-strip-and-the-four-tabs` — the four tabs, the default
  Summary tab, and the `ui.last_result_tab` persistence.
- `05_Result_Widget/description.md#51-per-tab-export-button-cluster` — the content-kind export
  button set per tab.
- `05_Result_Widget/description.md#52-save-destination-toggle-and-open-exports-folder` — the
  shared save-destination toggle, the direct-write vs picker behaviour, and the feedback wording.
- `05_Result_Widget/description.md#6-run-selection-logic` — the run-selector auto-jump on a run's
  first appearance and the user-locked-selection rule.
- `05_Result_Widget/description.md#7-view-only-during-run-rule` — every export and regeneration
  disabled while any run is non-terminal, driven by the shared run-activity source.
- `05_Result_Widget/description.md#9-per-run-table-and-chart-view-state` — the per-run view-state
  persistence rule the store implements.
- `05_Result_Widget/description.md#12-event-bus-integration` — the subscribed events and the
  emitted `_run_id_changed`.
- `05_Result_Widget/implementation_structure.md#4-parent-controller` — the parent controller's
  responsibilities, the view-state store, and the footer collaborator.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — the gateway surface this
  widget's `protocols.py` declares.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The parent and every tab sub-controller depend only on `ResultGateway` plus the retained UI
  helpers (`NativePickers`, `Clipboard`, `FileSystemActions`, `NotificationService`,
  `ExportFilenameHelper`) and the widget-local `PerRunViewStateStore` (D-R-06).
- The view-only-during-run state is read from the shared run-activity source and `_run_*`
  events; the widget never independently re-derives run-active state.
- The run-selector auto-jumps only on a run's first appearance and never overrides a user-locked
  selection.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-061-AC-1

Given a `_run_started` event for a run not previously in the dropdown and no user-locked
selection, when the shell processes it, then the run is added to the dropdown and auto-selected;
and given the user has manually selected a different run (user-locked), then a later
`_run_started` does not move the selection.

### STORY-061-AC-2

Given the user changes the run-selector dropdown, when the selection changes, then the shell
emits `_run_id_changed` carrying the chosen run id; and given a `_run_id_changed` from another
widget, then the dropdown updates without re-emitting the event.

### STORY-061-AC-3

For each active tab, the footer export cluster matches the tab's content kind:

| Active tab   | Export buttons              |
| ------------ | --------------------------- |
| Summary      | Export CSV, Export Markdown |
| Details      | Export CSV, Export Markdown |
| Charts       | Export PNG, Export SVG      |
| Run Analysis | Export Markdown             |

### STORY-061-AC-4

Given any run is in a non-terminal state, when the footer renders, then every export button is
disabled with the "Disabled — a benchmark is in progress." tooltip; and when the run reaches a
terminal state and the inference gate is `IDLE`, then the exports re-enable.

### STORY-061-AC-5

Given the save-destination toggle bound to `ui.export_save_directly`, when it is on, then the
Open-Exports-Folder button is visible and an export writes directly to the exports folder; and
when it is off, then the button is hidden and an export opens a native save picker.

### STORY-061-AC-6

Given a run opened for the first time, when a tab requests its slice, then the
`PerRunViewStateStore` returns the built-in default view state for that tab and the run's mode;
and given a previously opened run, then the store returns the exact stored slice for that run,
with no slice crossing between runs.

### STORY-061-AC-7

Given the widget is constructed via its own factory function (`make_result_widget`) with a fake
`ResultGateway` (and fakes for the declared collaborators `NativePickers`, `Clipboard`,
`FileSystemActions`, `NotificationService`, and `ExportFilenameHelper`) and mounted under
`qtbot`, when it is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop
pump), then no exception is raised, the widget reports `isVisible()`, and no
`error`/`critical`-level `structlog` record is captured — verified by wrapping construction+show
in `structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-061-AC-1 — unit (`pytest-qt`, fake `ResultGateway`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_controller.py`,
  `test_run_selector_auto_jump_and_user_lock`.
- STORY-061-AC-2 — unit (`pytest-qt`), same file,
  `test_dropdown_change_emits_and_external_selection_syncs`.
- STORY-061-AC-3 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_footer.py`,
  `test_export_cluster_per_active_tab`.
- STORY-061-AC-4 — unit (`pytest-qt`), same file,
  `test_exports_disabled_while_run_non_terminal`. Covers EC-RES-5, EC-RES-6.
- STORY-061-AC-5 — unit (`pytest-qt`, fake `NativePickers`/`FileSystemActions`), same file,
  `test_save_destination_toggle_direct_vs_picker`. Covers EC-WS-1 (detached footer parity).
- STORY-061-AC-6 — unit, colocated
  `src/ollama_llm_bench/ui/results/tests/test_view_state_store.py`,
  `test_first_open_defaults_vs_reopen_restore`.
- STORY-061-AC-7 — unit (`pytest-qt`, fake `ResultGateway`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_controller.py`,
  `test_result_widget_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-061.
- [ ] EC-RES-5, EC-RES-6, and EC-WS-1 each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Loading, NoRun,
  RunSelected, and live states of `05_Result_Widget/state_machine.md` that the shell owns.
- [ ] An architecture test confirms the parent controller depends only on `ResultGateway` (plus
  the retained UI helpers), that it reads run-active state from the shared source, and that
  the module references no `setStyleSheet`, embeds no colour literal, and imports no
  `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/results/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-061.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
