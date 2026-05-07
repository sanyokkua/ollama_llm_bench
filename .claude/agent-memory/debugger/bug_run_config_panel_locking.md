---
name: run_config_panel locking omissions (2026-04-30)
description: Three bugs in RunConfigPanel/MainWindow found via test failures — missing lockable widgets, missing tooltips, missing is_running guard in _open_settings
type: project
---

Fixed 2026-04-30 on feature/v2-app-redesign.

**Bug 1 — Incomplete lockable list in `_on_benchmark_status_changed`:**
`_prev_runs_combo`, `_resume_run_btn`, `_refresh_runs_btn`, `_advanced_group`,
`_streaming_checkbox`, `_warmup_checkbox`, `_reasoning_combo`, and `_judge_model_combo`
were missing from the `lockable` list. Adding new widgets to `RunConfigPanel`
requires manually adding them to this list — there is no automatic registry.

**Why:** The list is hand-maintained in `_on_benchmark_status_changed`; new widgets
added to the panel during feature development were not added to the lock list.

**Bug 2 — Missing tooltips on `_pause_btn` and `_stop_btn`:**
No `setToolTip()` calls existed in `_configure_widgets`. Tests expected descriptive
tooltips containing "current task" and "skipped"/"remaining".

**Bug 3 — `_open_settings()` had no `is_running()` guard:**
`MainWindow._open_settings()` opened `SettingsDialog` unconditionally. Added guard
that calls `QMessageBox.information` and returns early when benchmark is running.

**How to apply:** When adding new configuration widgets to RunConfigPanel,
always add them to the `lockable` list in `_on_benchmark_status_changed`.
Consider extracting to a `_lockable_widgets()` method returning a list to
avoid this class of omission in future.
