---
name: Phase 2 Task 13 — ProgressPanelWidget design (2026-04-16)
description: Design decisions for the structured progress panel widget consuming V2 EventBus events
type: project
---

ProgressPanelWidget is a new standalone QWidget added to `ui/widgets/panels/progress_panel_widget.py`.

**Why:** V2 pipeline emits `ProgressUpdateEvent`, `BenchmarkFinishedEvent`, `BenchmarkStoppedEvent`; no widget subscribed to them before this task.

**Key decisions:**

1. Constructor takes `event_bus: EventBus` (ABC), not `AppContext` — widget gets only what it needs, stays independently testable.

2. V1 flat progress labels in `ControlPanel` are preserved (no deletion). `ProgressPanelWidget` is added as a new section below `ControlTabWidget` inside `ControlPanel`'s existing `main_layout`.

3. `format_compact_duration(total_ms: float) -> str` added to `time_utils.py` — returns compact format `"2h 48m 33s"` / `"5m 4s"` / `"47s"`. Existing `format_elapsed_time()` produces a verbose non-matching format and must not be reused for the badge.

4. Stage badge uses `setStyleSheet()` with inline hex colors (not QSS tokens) — five PipelineStage values mapped via `_STAGE_COLORS: Final[dict[PipelineStage, str]]` constant; Stopped (non-enum state) uses `_STOPPED_COLOR = "#9E9E9E"`.

5. ETA label renders minutes only (`"ETA: 14 min"` / `"ETA: < 1 min"` / `"ETA: –"`). Hours ETA is an open question flagged for product owner.

6. Task label truncated at 30 chars with `"…"` suffix; full text in `setToolTip()`.

7. Tests require a `QApplication` fixture (`scope="module"`) for widget instantiation; EventBus mocked with `mocker.Mock(spec=EventBus)`.

8. `start_time_ms` and `current_time_ms` in `ProgressUpdateEvent` are in **milliseconds** — divide by 1000 before passing to existing time_utils functions that take seconds.

**How to apply:** When touching any widget that subscribes to V2 EventBus events, inject `event_bus: EventBus` directly in the constructor, not `AppContext`. When adding new widgets to `ControlPanel`, use `_setup_ui_layout` not `__init__` for layout composition.
