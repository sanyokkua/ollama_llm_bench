# Result Widget — Run Analysis Tab

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `05_Result_Widget/description.md`; `05_Result_Widget/tabs/summary_tab.md`; `05_Result_Widget/tabs/details_tab.md`; `05_Result_Widget/tabs/charts_tab.md`; `05_Result_Widget/implementation_structure.md`; `05_Result_Widget/flow_diagram.md`; `07_Common_Dialogs/generate_analysis_dialog.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md`; `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-H_app_modes.md`; `08_Cross_Cutting/08-I_edge_cases.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `10_Domain_and_Data/05_EXPORT_FORMATS.md`; `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`

The Run Analysis tab presents the single consolidated run-level narrative of the selected run — the Markdown text held in `BenchmarkRun.run_analysis`. Exactly one such field exists for every run mode; this tab displays it. The narrative is produced by the run-analysis service: automatically when the run finishes, and on demand when the user clicks Regenerate. The tab renders the narrative in full with no length cap, shows the generation metadata, and exports the narrative to a Markdown file.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Data source — the single consolidated run analysis
4. Generation timing
5. Generation-metadata line
6. Rendering and no length cap
7. Toolbar — Copy and Generate / Regenerate
8. Generate / Regenerate flow
9. Empty and failed states
10. Footer export
11. Live update
12. Persistence
13. Event-bus integration
14. Edge cases
15. Function inventory

---

## 1. Role and ownership

The Run Analysis tab owns the display of the consolidated run-level narrative. It is responsible for:

- Rendering `BenchmarkRun.run_analysis` as formatted Markdown, in full.
- Showing the generation metadata — when the narrative was produced, how long it took, and which model produced it.
- Letting the user copy the narrative to the clipboard and regenerate it.
- Exporting the narrative to a Markdown file.
- Showing a clear empty or failed state when no narrative exists.

The tab does not own run selection (the parent Result Widget does — see `05_Result_Widget/description.md`), it never generates the narrative itself (the run-analysis service does — see `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`), and it never starts, stops, or mutates a run.

## 2. Layout

```
+--------------------------------------------------------------------+
| Generated 2026-05-22 14:23 - 3.2 s - model: ollama / gpt-oss:20b   |
|                            [Copy]  [Generate / Regenerate analysis]|  <- in-tab toolbar
+--------------------------------------------------------------------+
|                                                                    |
|              <Markdown-rendered run-analysis narrative>            |
|                          (scrolls; no length cap)                 |
|                                                                    |
+--------------------------------------------------------------------+
| [Export Markdown]                [x] Save to app data folder       |  <- uniform footer
+--------------------------------------------------------------------+
```

The in-tab toolbar carries the **non-file actions** — Copy and the dynamic-label Generate / Regenerate button — because neither writes a file to disk; this keeps the uniform footer reserved for the file export, as required by `description.md` section 5. The narrative body fills the centre and scrolls when it exceeds the visible area. The mockup `05_Result_Widget/mockup.html` is the visual source of truth.

## 3. Data source — the single consolidated run analysis

The tab reads exactly one field — `BenchmarkRun.run_analysis` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` section 6.7). There is one consolidated run-level analysis for every run mode; there is no separate performance-analysis surface and no separate judge-summary field. The tab presents whatever that single field holds, or its empty state when the field is `None`.

The narrative is structured Markdown — an `Overview`, a `Per-model observations` section with one sub-heading per test model, and a `Notable tasks` list; a section with nothing to report for the run's mode is omitted by the generator. The structure is fixed by the run-analysis service and the export format (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` section 3, `10_Domain_and_Data/05_EXPORT_FORMATS.md`). The judge produces **no numeric score** in the narrative; the only numeric quality value that appears is the Cosine Score.

## 4. Generation timing

The consolidated run analysis is produced by the run-analysis service. Whether it is generated automatically when the run finishes depends on the run's per-run snapshot of `feature.judge_run_analysis_enabled` — **not on the run mode**:

| Run mode | Snapshot default | Automatic generation when the run finishes |
|---|---|---|
| `GRADED` | default ON | Generated when the snapshot is ON (the default); skipped when the user opted the toggle off at run start. |
| `TASKS` | default OFF | Generated only when the user opted the toggle on at run start. |
| `SYNTHETIC` | default OFF | Generated only when the user opted the toggle on at run start. |

Regardless of mode, the user can produce or replace the analysis at any time after the run reaches a terminal status by clicking the Generate / Regenerate button (section 8) — **including for a `GRADED` run that was started with the toggle OFF and therefore has `run_analysis = null`**, as well as for any `TASKS` or `SYNTHETIC` run that did not originally request one. The narrative is never generated mid-run: the service requires the run to be in a terminal status, and the button is disabled while any run is non-terminal.

This run-level analysis is distinct from the per-task judge phase. The per-task judge phase is an evaluation phase that grades individual results and contributes the `judge_verdict` and `judge_reasoning` shown in the Details tab; this tab shows only the one run-level narrative. The two are independent: a `GRADED` run may run with the per-task judge phase off and still produce the run-level analysis (when the analysis toggle is on), or with the per-task judge phase on and skip the run-level analysis (when the analysis toggle is off).

## 5. Generation-metadata line

The toolbar's left side shows a one-line metadata strip describing the displayed narrative:

- **Generated** — the timestamp at which the narrative was produced, formatted in the user's locale.
- **Duration** — how long the generating model call took, in seconds.
- **Model** — the `(provider_id, model_name)` of the analysis model that produced the narrative; the user-visible cell renders the SNAPSHOT `judge_provider_name` from `BenchmarkRun` (DD-33) so historical fidelity is preserved across a later provider rename. The internal `provider_id` is the linkage value but is never displayed. For an automatic generation this is whichever model the run designated for analysis (typically the run's snapshot judge); for an on-demand (re)generation this is whichever model the user picked in the Generate Analysis dialog — in that case the on-demand generation also writes the chosen provider's then-current name into `BenchmarkRun.judge_provider_name`.

When `run_analysis` is absent the metadata line is hidden. While a generation or regeneration is in flight for this run, the line reads `Generating...` until the new narrative arrives.

## 6. Rendering and no length cap

The narrative is rendered from Markdown to formatted text. Rendering supports headings, ordered and unordered lists, tables, inline code, and code blocks. The rendering is theme-aware: under the dark theme the body uses light text on a dark surface, under the light theme dark text on a light surface, with colours from `08_Cross_Cutting/08-D_color_palette_and_typography.md`.

There is **no length cap** and **no truncation**. The full `run_analysis` text from the Data Store is rendered in the tab body, and the Markdown export (section 10) writes it verbatim. When the rendered body exceeds the visible area it scrolls; a very long narrative is rendered lazily so a multi-megabyte analysis stays responsive, but the user-visible contract is unconditional — everything stored is shown and everything stored is exported.

## 7. Toolbar — Copy and Generate / Regenerate

The in-tab toolbar carries two buttons:

- **Copy** — copies the narrative's Markdown source to the system clipboard. It never opens a save picker. It is enabled whenever narrative text is present, including while a run is non-terminal — copying has no side effect.
- **Generate / Regenerate analysis** — a single button whose **label changes dynamically**: it reads **Generate analysis** when the selected run has no `run_analysis` yet, and **Regenerate analysis** when it does. Clicking either label opens the Generate Analysis dialog (`07_Common_Dialogs/generate_analysis_dialog.md`), which lets the user pick the analysis `(provider, model)` pair before the call is dispatched. The button is disabled with a tooltip whenever any of the following holds:
  - The selected run is in a non-terminal state — tooltip: `A benchmark run is in progress; analysis can be generated when it finishes.`
  - The application-wide single-inference gate (`InferenceActivityStore`, `08_Cross_Cutting/08-E_interfaces_contracts.md` §13) is held by an activity **other than `JUDGE_ANALYSIS` for this run** — tooltip: `Another inference activity is in flight; analysis can be generated when it finishes.`
  - The selected run has zero completed results (an empty run cannot be analysed) — tooltip: `This run has no completed results — there is nothing to analyse.`
  - A generation or regeneration is already in flight for this run — while held by `JUDGE_ANALYSIS` for this same run the button's label becomes `Generating...` and is disabled. See §8.

## 8. Generate / Regenerate flow

Clicking the Generate / Regenerate analysis button opens the Generate Analysis dialog. The user picks the `(provider, model)` pair and confirms; the dialog dispatches the call through the parent controller:

1. The dialog calls the parent controller's `regenerate_analysis(run_id, provider_id, model_name)` (which covers both the first-generation and regeneration paths — the entry point is the same).
2. The parent reads the run header and its results from the Data Store and dispatches `RunAnalysisService.generate(run_id, provider_id, model_name)` on a `QThreadPool` worker, so the UI thread stays responsive.
3. The service calls `InferenceActivityStore.try_acquire(InferenceActivity.JUDGE_ANALYSIS, ctx)`. On a returned `GateLease` (DD-50), the dialog closes immediately and the tab enters the **Generating** state — a spinner over the analysis area, the metadata line reads `Generating...`, the toolbar button reads `Generating...` and is disabled, and the `_inference_activity_changed` event reflects the held gate so every other inference-initiating control in the application is gated for the duration. On `None`, the dialog stays open with the inline busy message — the tab does **not** enter the Generating state.
4. The service calls the chosen analysis model exactly once. On success it returns the new Markdown body; the parent persists it into `BenchmarkRun.run_analysis` and emits `_run_analysis_received` (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.5). The service releases the gate in `finally`.
5. The tab receives the `_run_analysis_received` event on the UI thread and repaints the narrative and the metadata line; the toolbar button label returns to `Regenerate analysis`.

A failed generation **preserves any previously stored narrative**: when the analysis model is unreachable or returns unusable text, the service returns `FAILED`, the parent does not overwrite `run_analysis`, and the tab shows a soft error banner above the analysis area with the classified reason (network, provider down, judge model not available, etc.). The prior good narrative, if any, stays on screen unchanged. The full sequence is in `flow_diagram.md` flow G; the service contract is in `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`; the dialog itself is specified at `07_Common_Dialogs/generate_analysis_dialog.md`. There is no run-count limit on (re)generations — each is one model call.

## 9. Empty and failed states

When the selected run has no narrative, the tab body shows a centred message in `mute` tone instead of an empty surface:

| State | Condition | Message |
|---|---|---|
| Not generated — graded run still running | `run_analysis` is absent and the run has not finished | `Run-level analysis is generated when the benchmark finishes.` |
| Not generated — analysis was not requested | a finished run in **any mode** — `GRADED`, `TASKS`, or `SYNTHETIC` — whose snapshot had `feature.judge_run_analysis_enabled = false` at run start, so `run_analysis` is absent | `Run-level analysis was not requested for this run. Click Generate analysis to produce it now.` |
| Generation in flight | a generation or regeneration is running for this run (the single-inference gate is held by `JUDGE_ANALYSIS` for this run) | `Generating run-level analysis...` with a busy spinner over the analysis area; the toolbar button reads `Generating...` and is disabled |
| Generation failed | the most recent generation or regeneration failed and no prior narrative exists | `Run-level analysis could not be generated. See the run log for details.` with a soft error banner naming the classified reason and a `Generate analysis` affordance |

When a regeneration fails but a prior good narrative exists, the prior narrative stays rendered and a soft error banner appears above the analysis area — the failed state never replaces a good narrative (section 8). In every empty or failed state the Generate / Regenerate analysis button is the path forward, gated by the view-only-during-run rule and the single-inference gate (§7).

## 10. Footer export

The uniform footer carries one export button — `Export Markdown` — because the tab's content kind is text. The export writes the full `run_analysis` narrative, with no truncation, into a `.md` file. The caller wraps the body with the metadata header — run name, generation time, run mode — fixed by `10_Domain_and_Data/05_EXPORT_FORMATS.md`. The filename is `<effective_run_name>_RunAnalysis.md`.

The button is **disabled while any run is in a non-terminal state** and while no narrative exists. The save behaviour — direct write to `<app_data>/exports/` versus a save picker — follows the shared `ui.export_save_directly` rule used by every Result Widget tab. The tab exposes no `Detach window` action: a single text body has no comparison use case, and Copy and Regenerate in the toolbar already cover its actions (see `description.md` section 8).

## 11. Live update

The tab subscribes to `_run_analysis_received` on the event bus. The same event delivers both the automatic post-run narrative — produced once when a run finishes — and any on-demand (re)generated narrative; the tab handles both identically: it caches the narrative per `run_id` and repaints when the user has the corresponding run selected. The tab also subscribes to `_inference_activity_changed` (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.7) so the Generate / Regenerate button's enabled state and tooltip reflect the live gate state — in particular, the button enters the `Generating...` state when the gate is held by `JUDGE_ANALYSIS` for the currently selected run, and is disabled with a tooltip when the gate is held by any other activity. The tab does not subscribe to the per-task result events; it has nothing to repaint as individual tasks complete, only when the run-level narrative is produced.

## 12. Persistence

The tab holds **no persisted view state** of its own — no filters, no columns, no per-run preferences. The narrative itself is persisted as `BenchmarkRun.run_analysis` in the Data Store, written by the parent controller after a successful generation or regeneration. On reopen the tab rebuilds purely from the Data Store; there is nothing tab-local to restore. The scroll position in the narrative body is session state and is not persisted across an application restart.

## 13. Event-bus integration

All subscriptions are owner-bound to the tab; the bus auto-cancels them on destruction.

| Direction | Signal | Handler effect |
|---|---|---|
| Subscribes | `_run_analysis_received` (for the displayed run) | cache the narrative for the run; repaint when it is the selected run; toolbar button label returns to `Regenerate analysis` |
| Subscribes | `_run_id_changed` (from the parent Result Widget) | reload `run_analysis` for the newly selected run; repaint or show the empty state; toolbar button label switches between `Generate analysis` and `Regenerate analysis` based on whether `run_analysis` is present |
| Subscribes | `_run_started`, `_run_finished`, `_run_stopped`, `_run_failed` | enable or disable the Generate / Regenerate analysis and Export buttons as runs enter or leave a non-terminal state |
| Subscribes | `_inference_activity_changed` | enable or disable the Generate / Regenerate analysis button based on the held activity; show the `Generating...` label and spinner when the gate is held by `JUDGE_ANALYSIS` for this run |

The tab emits no event directly. Clicking Generate / Regenerate opens the Generate Analysis dialog (`07_Common_Dialogs/generate_analysis_dialog.md`); the dialog dispatches the run-analysis service through the parent controller, which emits `_run_analysis_received` on the tab's behalf when the new narrative is ready.

## 14. Edge cases

| ID | Concern | Handling |
|---|---|---|
| EC-RUN-3 | the selected run failed | the tab shows whatever `run_analysis` exists; if none, the not-generated empty state, with Regenerate available once no run is in progress |
| EC-RES-1 | a run with zero completed results | the run-analysis service skips generation; the tab shows the not-generated empty state; a Regenerate also yields a skip |
| EC-RES-3 | a very long run-analysis narrative | the full text is rendered with no length cap and is exported verbatim; a long body is rendered lazily and scrolls (section 6) |
| EC-RES-5 | a direct-write Markdown export fails | an error modal reports the failure; the narrative on screen is unchanged |
| EC-RES-6 | a run name that sanitises to an empty string | the export filename falls back to `Run_<run_id>_RunAnalysis.md` |
| JA-EC-1 | a regeneration fails while a prior narrative is stored | the prior narrative stays on screen; a transient failure notice appears; `run_analysis` is not overwritten (section 8) |
| JA-EC-2 | a run in any mode — including a `GRADED` run started with the analysis toggle OFF — created without analysis | the tab shows the not-requested empty state; Generate analysis produces the narrative on demand once the run is terminal |
| JA-EC-3 | text in the model's narrative that matches a redaction pattern | the run-analysis service does NOT redact the narrative body (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1); the narrative is a summary of the user's own benchmark data on the user's own machine. The text is displayed and exported verbatim. |
| JA-EC-4 | another inference activity holds the single-inference gate when the user clicks the toolbar button | the button is already disabled with the matching tooltip (`Another inference activity is in flight; analysis can be generated when it finishes.`); a click is therefore a no-op. If the user reached this state by clicking the moment a benchmark run started, the click is dropped by the disabled state. See `08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-12. |
| JA-EC-5 | the user opens the Generate Analysis dialog and a benchmark run starts before they confirm | the dialog's Confirm button is bound to `_inference_activity_changed` and is disabled with the inline busy message; the dialog stays open. See `07_Common_Dialogs/generate_analysis_dialog.md` §8. |

## 15. Function inventory

| Function | Primitive | Enabled when |
|---|---|---|
| Read the run-level narrative | text body | always; shows the narrative or an empty/failed state |
| Copy the narrative to the clipboard | button in the toolbar | narrative text is present; allowed during a run |
| Generate the run analysis (label = `Generate analysis`) | dynamic-label button in the toolbar | no run is in a non-terminal state; the inference-activity gate is `IDLE` or held by `JUDGE_ANALYSIS` for this run; the run has at least one completed result; `run_analysis` is absent for the selected run |
| Regenerate the run analysis (label = `Regenerate analysis`) | the same dynamic-label button | same conditions as above, plus `run_analysis` is already present |
| Export the narrative as Markdown | button in the footer | no run is in a non-terminal state and narrative text is present |
| Toggle save-directly / Open Exports Folder | toggle plus button in the footer | always; shared across every Result Widget tab |
