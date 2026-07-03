# 08-R · Screen Index and Screen↔Spec Traceability

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, reviewer
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-L_ui_standardization.md`, `08_Cross_Cutting/08-D_color_palette_and_typography.md`, `08_Cross_Cutting/08-H_app_modes.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`, `00_Foundation/06_CROSS_REF.md`

---

This document is the single navigation map for the application's user interface. It indexes every UI screen, the variant states each screen's mockup draws, and — in the traceability table — the specification documents that govern each screen and its major controls. It is the forward direction of the per-screen validation that established the mockups as the visual source of truth: from a screen, find the spec; from the spec, find the screen.

Two rules frame everything below:

- **The mockup is the visual source of truth.** Each screen's `mockup.html` is the canonical rendering of its controls, states, colours, and glyphs. Where a description and a mockup disagree on a visual detail, the mockup wins and the description is corrected (not the reverse).
- **Cross-cutting UI law is owned centrally.** Button order, modality, glyphs, status names, semantic colours, typography, accessible names, and the event vocabulary are owned by the cross-cutting documents listed in section 4, not re-decided per screen.

## Table of Contents

1. Purpose and scope
2. Screen index — every mockup and its drawn states
3. Screen → spec traceability
4. Cross-cutting governing documents
5. Maintenance rule

## 1. Purpose and scope

The application presents two workspaces (Benchmark and Task Editor) inside one main window, plus a set of modal dialogs reachable from anywhere. Each screen is specified by a folder of Markdown documents and is drawn by one `mockup.html` (the Result widget additionally ships `charts_gallery.html` for its twelve chart kinds). This document does not redefine any behaviour; it only indexes and cross-links. The authoritative behaviour for each screen lives in the documents named in section 3.

## 2. Screen index — every mockup and its drawn states

| # | Screen | Mockup file | Drawn states / variants | One-line purpose |
|---|---|---|---|---|
| 01 | Main Window | `01_Main_Window/mockup.html` | Application shell; status-bar health-dot states; workspace switcher; running pill | The application shell: menu bar, workspace switcher, status bar, and the run-in-progress pill. |
| 02 | New Benchmark | `02_New_Benchmark_Widget/mockup.html` | Three run modes (Synthetic Benchmark / Task Benchmark / Graded Benchmark); Advanced Options collapsed vs activated; Start-button validation states (disabled hard-errors, enabled soft-warnings); section-visibility matrix | Configure and launch a new benchmark run for the selected mode. |
| 03 | Resume Benchmark | `03_Resume_Benchmark_Widget/mockup.html` | Run list with row actions; Resume Summary dialog with drift warnings and the inline task picker | Browse past runs and resume, retry, clone, rename, export, or delete them. |
| 04 | Progress | `04_Progress_Widget/mockup.html` | Running (verbose); judge-in-flight; paused; pausing-draining; stopping-draining; failed-terminal; viewing a past run; three log-verbosity levels | Live view of the executing run: counters, current task, activity log, stability. |
| 05 | Result | `05_Result_Widget/mockup.html` + `05_Result_Widget/charts_gallery.html` | Four tabs (Summary, Details, Charts, Run Analysis); run-active overlay; Run Analysis generated vs empty states; the twelve chart kinds with low-sample hatch and per-chart empty states | Inspect a finished run's tables, charts, and consolidated analysis; export. |
| 06 | Settings | `06_Settings_Dialog/mockup.html` | Providers tab (dirty); General tab (clean); Provider Edit reachability + inference-test panel; gate-busy disabled state; Import preview modal | Manage providers (env-var-name credentials), embedding selection, and app settings. |
| 07 | Common Dialogs | `07_Common_Dialogs/mockup.html` | Rename Run; Run Summary (mode-aware: Graded Benchmark + Synthetic Benchmark + Task Benchmark variants); Resume Summary; Retry Selection; Error (three patterns); About; Generate Analysis (Generate / Regenerate / gate-busy) | The shared modal dialogs reachable from anywhere in the app. |
| 09 | Task Editor | `09_Task_Editor/mockup.html` | Default/dirty; help popover; YAML preview; hard-error; empty; unsaved-changes confirm; external-file-change banner; parse-error banner | Full-window editor for YAML task files with live per-row validation. |

## 3. Screen → spec traceability

Each row maps a screen to the documents that specify it. Unless noted, every widget folder carries a `description.md` (behaviour), `state_machine.md` (states/transitions), `flow_diagram.md` (sequences), and `implementation_structure.md` (module/MVC layout); those four are abbreviated as **(core four)** below.

| Screen | Governing spec documents |
|---|---|
| 01 Main Window | `01_Main_Window/` (core four); workspace model `08_Cross_Cutting/08-H_app_modes.md`; readiness indicator `11_Services_and_Algorithms/09_READINESS_PROBE.md`. |
| 02 New Benchmark | `02_New_Benchmark_Widget/` (core four) + `mode_specifics/{graded,tasks,synthetic}.md`; per-run overridable flags `08_Cross_Cutting/08-C_*`; synthetic matrix `11_Services_and_Algorithms` performance-task generator; judge/embedding selection `06_Settings_Dialog/description.md` + D-R-13. |
| 03 Resume Benchmark | `03_Resume_Benchmark_Widget/` (core four); Resume Summary + Retry Selection `07_Common_Dialogs/resume_summary_dialog.md`, `07_Common_Dialogs/retry_selection_dialog.md`; drift `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`; recovery `12_Quality_and_NFRs` data-integrity. |
| 04 Progress | `04_Progress_Widget/` (core four); pipeline state `08_Cross_Cutting/08-B_benchmark_state_machine.md`; serial execution + pause/stop `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (D-R-16); event vocabulary `08_Cross_Cutting/08-J_event_bus_catalog.md` (`_run_*`); log verbosity `11_Services_and_Algorithms/15_LOG_FORMATTING.md`. |
| 05 Result | `05_Result_Widget/` (core four) + `tabs/{summary_tab,details_tab,charts_tab,run_analysis_tab}.md`; chart aggregation `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`; run analysis `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`; exports `10_Domain_and_Data/05_EXPORT_FORMATS.md`; redaction scope `10_Domain_and_Data/08_REDACTION_PATTERNS.md`. |
| 06 Settings | `06_Settings_Dialog/` (core four) + `sub_dialogs/{provider_edit,reset_confirmation}.md`; credential model (env-var NAME) `12_Quality_and_NFRs/02_SECURITY_MODEL.md` + D-R-18; import/export `10_Domain_and_Data/06_IMPORT_FORMATS.md`; feature flags `08_Cross_Cutting/08-G_feature_flags.md`; provider registry `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`. |
| 07 Common Dialogs | `07_Common_Dialogs/{rename_run,run_summary,resume_summary,retry_selection,error,about,generate_analysis}_dialog.md`; modality + button order `08_Cross_Cutting/08-L_ui_standardization.md`; About surface (no crash reporting) `13_Distribution_and_Release/07_CRASH_REPORTING.md` + D-R-17. |
| 09 Task Editor | `09_Task_Editor/` (core four) + `field_reference.md`; validation `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`; YAML formatting `11_Services_and_Algorithms/12_YAML_FORMATTER.md`; task file format `10_Domain_and_Data/06_IMPORT_FORMATS.md`. |

## 4. Cross-cutting governing documents

These documents own UI law that applies to every screen above; a screen never re-decides them locally.

| Concern | Owning document |
|---|---|
| Button order, dialog modality, glyphs, status names | `08_Cross_Cutting/08-L_ui_standardization.md` |
| Semantic colours, palette, typography | `08_Cross_Cutting/08-D_color_palette_and_typography.md` |
| Run modes and workspace model | `08_Cross_Cutting/08-H_app_modes.md` |
| Event-bus vocabulary (`_run_*`, `_inference_activity_changed`, …) | `08_Cross_Cutting/08-J_event_bus_catalog.md` |
| Accessible names, stable test objectNames, icon-only registry | `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7 / §7.2 |
| Per-run overridable flag snapshot | `08_Cross_Cutting/08-C_*` |
| Edge cases per screen | `08_Cross_Cutting/08-I_edge_cases.md` (→ `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`) |

## 5. Maintenance rule

When a screen gains, loses, or renames a control or a drawn state, update this document in the same change: add or amend the screen's row in section 2 (drawn states) and section 3 (governing docs), and — if the control is icon-only — add it to the accessible-name registry in `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2. This document and the mockups must never disagree about which screens and states exist.
