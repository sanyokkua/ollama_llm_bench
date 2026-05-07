---
name: Results Panel Live Updates design (2026-04-22)
description: Six-bug fix for real-time results table updates, scroll preservation, locking, theme, and cache during active runs
type: project
---

Debounce-based live refresh chosen for StatusListener: subscribe to task_completed and judge_completed EventBus events; use time.monotonic() + _LIVE_UPDATE_DEBOUNCE_S=0.5 constant.

**Why:** StatusListener is a plain Python class (no QObject/QTimer available). time.monotonic() is idiomatic and keeps the class free of Qt dependencies. FINISHED/FAILED stage handler acts as guaranteed final flush.

**How to apply:** Any future live-progress feature in StatusListener should use the same debounce pattern — _last_live_update float + time.monotonic() comparison.

Key decisions:
- _summary_table, _detailed_table, and _task_detail_widget removed from _benchmark_sensitive_widgets so they remain interactive during a run.
- _summary_also_save_checkbox and _details_also_save_checkbox ADDED to _benchmark_sensitive_widgets (they were missing — bug).
- Scroll preservation: snapshot vbar.value() + at-bottom flag before _update_table, restore after. @staticmethod _update_table unchanged; new instance wrapper method added.
- TaskDetailWidget theme fix: QGuiApplication.styleHints().colorScheme() compared to Qt.ColorScheme.Light — never hardcode "dark".
- ResultWidgetController live cache: _set_detailed_summary incrementally fetches new model|task_id keys from DB instead of only rebuilding cache on _set_run_id(). Uses incoming_keys - cache.keys() diff to minimise DB calls.
- _HasRunId Protocol (run_id: int) defined at module level in status_listener.py to type the combined task/judge handler.
