---
name: Phase 2 Task 14 — LogWidget V2 + LogFileWriter design (2026-04-16)
description: LogWidget injects EventBus directly (not controller); chunk buffer drained by QTimer at 50ms; LogFileWriter is pure service with lazy file open; log_file_writer threaded through FlowApi → ExecutionTask
type: project
---

Widget subscribes to EventBus directly (consistent with Task 13 ProgressPanelWidget pattern).
LogWidgetControllerApi is kept alive for V1 compat (log_clean + log_append signals) but no longer the primary driver.

`LogFileWriter` constructed with only `app_root: Path`; log directory and file handles opened lazily on first `write_entry`. Uses `buffering=1` (line-buffered) — no explicit flush needed.

`_write_log_entry` helper on `BenchmarkExecutionTask` guards all writes with `get_bool(SETTING_LOG_TO_FILE)`. `close(run_id)` called directly in the `finally` block of `run()`.

`LogWidget` uses three-phase construction: `_create_widgets()` → `_configure_widgets()` → `_build_layout()` → `_subscribe_events()`. Chunk buffer pattern: `_chunk_buffer: list[str]` + `_drain_timer: QTimer` at 50ms. Jump-to-bottom button positioned via layout (not absolute), shown/hidden via scrollbar `valueChanged` signal.

Scrollback enforcement: `document().blockCount()` + cursor-based head deletion. Check runs on every `_append_html` call.

**Why:** Widget-direct subscription avoids a thin no-logic controller pass-through, matching the Task 13 precedent.

**How to apply:** For any new V2 widget that displays pipeline events, inject EventBus directly rather than routing through a controller. Controllers are reserved for widgets that need to orchestrate multiple services or perform stateful business logic.
