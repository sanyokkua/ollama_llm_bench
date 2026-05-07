# Phase 5 — UI Redesign: Implementation Plan

**Generated**: 2026-04-17
**Source**: `docs/v2/v2-implementation-plan.md` sections 5.1–5.5; `docs/v2/v2-ui-design-guide.html`
**Scope**: Redesign the application from a 2-panel (Control | Results) layout to a 3-panel (Run Config | Progress+Log | Results) layout, introduce a QSS-based theme engine with dark/light support, and update result tables with V2 metrics (TTFT, pass rate, cosine, resolution layer).

---

## Prerequisites

- Phases 1–4 are complete and all tests pass (`uv run pytest -q`).
- The following services exist and are wired in `app_context.py`:
  - `ProviderRegistry` (for listing providers and fetching models per provider)
  - `BenchmarkFlowApi` (`start_execution`, `stop_execution`, `pause_execution`, `resume_execution`, `is_running`)
  - `AppSettingsService` (for reading `ui.theme` setting)
  - `TaskFileLoader` (task file management)
  - `SqLiteDataApi` (persisting runs)
- `ui/style/tokens.py` exists at `src/ollama_llm_bench/ui/style/tokens.py` with `DARK_TOKENS`, `LIGHT_TOKENS`, `SHARED_TOKENS`, `get_tokens()`.

---

## Architecture Decisions

1. **No hardcoded hex colors anywhere** — all colors via `tokens.py` → QSS `{token}` substitution.
2. **3-panel QSplitter layout**: Left (RunConfigPanel) | Center (CenterPanel) | Right (ResultsPanel). Default px sizes: 280 | flex | 440. Minimums: 250 | 320 | 380.
3. **Minimum window size**: 1200 × 700 px (`setMinimumSize`).
4. **RunConfigPanel replaces ControlPanel + ControlTabWidget + NewRunWidget + PreviousRunWidget**. Old files are removed in Task 10.
5. **CenterPanel replaces the log tab** in the old ResultsPanel. LogWidget is no longer inside a tab — it fills the lower half of CenterPanel.
6. **ResultsPanel no longer has tabs** — it holds ResultWidget directly (ResultTabWidget removed).
7. **QSS theme applied once at startup** via `ThemeLoader.apply_theme(app, theme_name)` in `main.py`, and reapplied when `ui.theme` setting changes.
8. **RunConfigController** supersedes `NewRunWidgetController` + `PreviousRunWidgetController`. Old controllers are removed in Task 10.
9. **V2 result columns**: summary adds `TTFT (ms)` and `Pass%`; detailed adds `Cosine` and `Layer`. Models `AvgSummaryTableItem` and `SummaryTableItem` are extended accordingly.
10. **No Qt imports in `core/` or `services/`** — `RunStartEvent` lives in `backend/core/models.py` as a frozen dataclass.

---

## Task 1: Extend Design Tokens and Create QSS Theme System

**Files to create**:
- `src/ollama_llm_bench/ui/style/theme_dark.qss`
- `src/ollama_llm_bench/ui/style/theme_light.qss`
- `src/ollama_llm_bench/ui/style/theme_loader.py`

**Files to modify**:
- `src/ollama_llm_bench/ui/style/tokens.py`

**Depends on**: None

### Context

The current `tokens.py` has 14 tokens (dark + light) but the QSS design system requires ~28 theme-specific tokens plus 2 font tokens in SHARED. No QSS files exist. This task creates the full token vocabulary and a loader that applies the theme to the running `QApplication`.

### Requirements

1. `DARK_TOKENS` must be extended with these additional keys (exact hex values from the design guide):
   - `primary_hover`: `#0FA898`
   - `primary_pressed`: `#0D9488`
   - `primary_disabled`: `#2D5A54`
   - `text_on_primary`: `#111827`
   - `accent`: `#A78BFA`
   - `success_bg`: `#064E3B`
   - `failure_bg`: `#7F1D1D`
   - `warning_bg`: `#78350F`
   - `selection`: `#134E4A`
   - `hover`: `#1A3A35`
   - `scrollbar_bg`: `#1F2937`
   - `scrollbar_handle`: `#4B5563`
2. `LIGHT_TOKENS` must be extended with the light equivalents:
   - `primary_hover`: `#0B7E73`
   - `primary_pressed`: `#096B62`
   - `primary_disabled`: `#A7D3CF`
   - `text_on_primary`: `#FFFFFF`
   - `accent`: `#8B5CF6`
   - `success_bg`: `#ECFDF5`
   - `failure_bg`: `#FEF2F2`
   - `warning_bg`: `#FFFBEB`
   - `selection`: `#CCFBF1`
   - `hover`: `#F0FDFA`
   - `scrollbar_bg`: `#E5E7EB`
   - `scrollbar_handle`: `#9CA3AF`
3. `SHARED_TOKENS` must be extended with:
   - `font_sans`: `"SF Pro Text", "Segoe UI", "Cantarell", "Ubuntu", "Helvetica Neue", "Noto Sans", "DejaVu Sans", sans-serif`
   - `font_mono`: `"SF Mono", "Cascadia Mono", "Menlo", "Consolas", "Ubuntu Mono", "DejaVu Sans Mono", "Monaco", "Courier New", monospace`
4. `theme_dark.qss` and `theme_light.qss` must use `{token_name}` placeholders (not literal hex) for every color, font, spacing, and radius. Both files contain the same selectors — only the token values differ. Required selectors (minimum):
   - `QMainWindow, QDialog` — bg_primary, text_primary, font_sans, 13px
   - `QLabel` — text_primary
   - `QLabel[role="secondary"]` — text_secondary, 12px
   - `QLabel[role="heading"]` — text_secondary, 11px, font-weight 700, text-transform uppercase
   - `QLabel[role="badge"]` — 11px, 700, border-radius radius_sm, padding 2px 8px
   - `QPushButton[role="primary"]` — primary bg, text_on_primary, radius_md, 6px 16px padding, 600 weight, min-height 32px; `:hover` primary_hover; `:pressed` primary_pressed; `:disabled` primary_disabled bg + text_disabled
   - `QPushButton[role="secondary"]` — transparent bg, primary text, border 1px solid border, radius_md; `:hover` hover bg + primary border
   - `QPushButton[role="danger"]` — failure text, border; `:hover` failure_bg + failure border
   - `QComboBox` — bg_input, border, radius_md, 5px 12px padding, text_primary, min-height 32px; `:focus` border_focus; `::drop-down` no border, 20px; `QAbstractItemView` bg_secondary, selection bg
   - `QLineEdit, QSpinBox, QDoubleSpinBox` — bg_input, border, radius_md, 5px 12px, text_primary, min-height 32px; `:focus` border_focus
   - `QTextEdit` — bg_input, border, radius_md, 8px padding, text_primary, font_mono, 12px
   - `QCheckBox::indicator` — 18px × 18px, radius_sm, 2px solid border, bg_input; `:checked` primary bg + border
   - `QRadioButton::indicator` — 18px × 18px, 9px border-radius, 2px solid border, bg_input; `:checked` primary bg + border
   - `QProgressBar` — bg_secondary, border, 10px radius, min-height 20px, text-align center, 11px, text_primary; `::chunk` primary, 10px radius
   - `QTabBar::tab` — 8px 20px padding, text_secondary, 600, 2px solid transparent bottom border; `:selected` primary text + primary bottom border
   - `QTableView` — bg_primary, border, gridline bg_secondary, selection bg, text_primary, 12px
   - `QHeaderView::section` — bg_secondary, text_secondary, 600, 11px, 8px 10px padding, no border, 1px border-bottom border
   - `QGroupBox` — border, radius_md, 16px padding, 16px margin-top; `::title` text_secondary, 11px, 700
   - `QScrollBar:vertical` — scrollbar_bg, 8px width, 4px radius; `::handle:vertical` scrollbar_handle, 4px radius, 30px min-height
   - `QToolTip` — bg_secondary, text_primary, border, radius_sm, 6px 10px padding, 12px
   - `QSplitter::handle` — border color, 5px width; `:hover` primary
5. `theme_loader.py` must export a single function `apply_theme(app: QApplication, theme: str) -> None` that:
   - Accepts `"dark"` or `"light"` (falls back to `"dark"` for unknown)
   - Reads the appropriate `.qss` file using `importlib.resources.files("ollama_llm_bench").joinpath(f"ui/style/theme_{theme}.qss")` (or falls back to `Path(__file__).parent / f"theme_{theme}.qss"` for development)
   - Calls `get_tokens(theme)` and replaces all `{key}` placeholders in the QSS string
   - Calls `app.setStyleSheet(resolved_qss)`
   - Logs at INFO level: `theme_applied`, with `theme` context key

### Existing Code Reference

- `src/ollama_llm_bench/ui/style/tokens.py` lines 11–54 — current token dicts (extend, do not replace)
- `src/ollama_llm_bench/ui/style/tokens.py` lines 57–71 — `get_tokens()` factory to call from `theme_loader.py`

### Implementation Guidance

```python
# theme_loader.py signature
def apply_theme(app: "QApplication", theme: str) -> None:
    ...
```

The QSS substitution is a simple string `.format_map(tokens)` after wrapping token dict values in `{}`. Example:
```python
resolved = qss_template.format_map(tokens)
```
This works because `{bg_primary}` in QSS maps to `tokens["bg_primary"]`. Use `str.format_map()` not `.format(**tokens)` to avoid KeyError on unrecognized `{}` patterns in QSS.

Both `.qss` files must be included in the Python package. Add them to `pyproject.toml` under `[tool.hatch.build.targets.wheel]` if needed, or verify they are included via the `src/` layout + hatchling defaults (hatchling includes all non-`.py` files by default if under `src/`).

### Verification

- [ ] `from ollama_llm_bench.ui.style.tokens import get_tokens; t = get_tokens("dark"); assert "primary_hover" in t and "font_sans" in t`
- [ ] `from ollama_llm_bench.ui.style.theme_loader import apply_theme` imports without error
- [ ] `uv run pytest tests/ -q` still passes
- [ ] Both `.qss` files exist and contain `{bg_primary}` (grep check)

---

## Task 2: Create Shared Micro-Widgets (BadgeLabel, HealthDot)

**Files to create**:
- `src/ollama_llm_bench/ui/widgets/common/__init__.py`
- `src/ollama_llm_bench/ui/widgets/common/badge_label.py`
- `src/ollama_llm_bench/ui/widgets/common/health_dot.py`

**Files to modify**: None

**Depends on**: None

### Context

Several panels need the same small visual components: a colored badge label (for pipeline stage and verdict display) and a health dot indicator (for provider status). Centralizing them avoids duplicating inline `setStyleSheet` calls across multiple widgets.

### Requirements

1. `BadgeLabel` is a `QLabel` subclass with:
   - `set_stage(stage: PipelineStage) -> None` — sets text to `stage.value`, applies background color from `_STAGE_COLORS` dict (same values as in existing `progress_panel_widget.py` lines 19–26)
   - `set_verdict(verdict: EvalVerdict) -> None` — sets text to `verdict.value`, green bg for PASS, red for FAIL, grey for UNKNOWN
   - `set_custom(text: str, bg_color: str) -> None` — raw escape hatch
   - Default style: `border-radius: 4px; padding: 2px 8px; font-weight: bold; color: #FFFFFF;` applied via `setStyleSheet` on init and updated per call
2. `HealthDot` is a `QLabel` subclass with:
   - Fixed size: 12 × 12 px (`setFixedSize(12, 12)`)
   - `set_live() -> None` — sets background to `#34D399` (success token color)
   - `set_down() -> None` — sets background to `#F87171` (failure)
   - `set_unknown() -> None` — sets background to `#FBBF24` (warning)
   - Style applied via `setStyleSheet` with `border-radius: 6px;` (makes it a circle)
   - Initial state: unknown
3. Both classes use `logging.getLogger(__name__)` and `from __future__ import annotations`.
4. `__init__.py` is empty (just `__all__ = []`).

### Existing Code Reference

- `src/ollama_llm_bench/ui/widgets/panels/progress_panel_widget.py` lines 19–26 — `_STAGE_COLORS` to reuse in `BadgeLabel.set_stage()`
- `src/ollama_llm_bench/ui/widgets/settings/provider_card_widget.py` — existing health dot implementation to supersede

### Implementation Guidance

```python
# badge_label.py
from PySide6.QtWidgets import QLabel
from ollama_llm_bench.backend.core.models import EvalVerdict, PipelineStage

_STAGE_COLORS: dict[PipelineStage, str] = {
    PipelineStage.INITIALIZING: "#2196F3",
    PipelineStage.BENCHMARKING: "#FF9800",
    PipelineStage.JUDGING: "#9C27B0",
    PipelineStage.FINISHED: "#4CAF50",
    PipelineStage.FAILED: "#F44336",
}
_VERDICT_COLORS: dict[EvalVerdict, str] = {
    EvalVerdict.PASS: "#34D399",
    EvalVerdict.FAIL: "#F87171",
    EvalVerdict.UNKNOWN: "#9E9E9E",
}
_BASE_STYLE = "border-radius: 4px; padding: 2px 8px; font-weight: bold; color: #FFFFFF; background-color: {color};"
```

### Verification

- [ ] `from ollama_llm_bench.ui.widgets.common.badge_label import BadgeLabel` imports without error
- [ ] `from ollama_llm_bench.ui.widgets.common.health_dot import HealthDot` imports without error
- [ ] `uv run pytest tests/ -q` still passes

---

## Task 3: Add RunConfigControllerApi and RunStartEvent to Core Layer

**Files to modify**:
- `src/ollama_llm_bench/backend/core/models.py`
- `src/ollama_llm_bench/backend/core/ui_controllers.py`
- `src/ollama_llm_bench/backend/core/interfaces.py`

**Depends on**: None

### Context

Phase 5 introduces a unified left-panel controller that merges `NewRunWidgetControllerApi` and `PreviousRunWidgetControllerApi`, adds provider selection, task file management, and pause/resume support. The Protocol and supporting dataclass must live in the core layer (no Qt imports).

### Requirements

1. Add `RunStartEvent` frozen dataclass to `models.py` (after line 396, near `NewRunWidgetStartEvent`):
   ```python
   @dataclass(frozen=True, slots=True, kw_only=True)
   class RunStartEvent:
       run_mode: RunMode
       judge_provider: str
       judge_model: str
       test_provider: str
       test_models: tuple[str, ...]
       task_paths: tuple[Path, ...]
       streaming_enabled: bool = True
       warmup_enabled: bool = True
       reasoning_effort: str = "default"
   ```
   Import `Path` from `pathlib` at the top of `models.py` (add if not present).
2. Add `RunConfigControllerApi` Protocol to `ui_controllers.py` (after `SettingsWidgetControllerApi`):
   ```python
   class RunConfigControllerApi(Protocol):
       def get_provider_names(self) -> list[str]: ...
       def get_models_for_provider(self, provider_name: str) -> list[str]: ...
       def get_unfinished_runs(self) -> list[tuple[int, str]]: ...
       def handle_start_click(self, event: RunStartEvent) -> None: ...
       def handle_pause_click(self) -> None: ...
       def handle_resume_click(self) -> None: ...
       def handle_stop_click(self) -> None: ...
       def handle_resume_run_click(self, run_id: int) -> None: ...
       def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None: ...
       def subscribe_to_runs_change(self, callback: Callable[[list[tuple[int, str]]], None]) -> None: ...
   ```
   Add `RunStartEvent` to the import from `ollama_llm_bench.backend.core.models` at the top of `ui_controllers.py`.
3. Add `get_run_config_controller() -> RunConfigControllerApi` abstract method to the `AppContext` ABC in `interfaces.py`. Import `RunConfigControllerApi` from `ui_controllers.py` in `interfaces.py`.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` lines 391–396 — `NewRunWidgetStartEvent` pattern to follow for `RunStartEvent`
- `src/ollama_llm_bench/backend/core/ui_controllers.py` lines 233–261 — `SettingsWidgetControllerApi` Protocol pattern to follow for `RunConfigControllerApi`
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 1–51 — existing imports; `AppContext` ABC definition

### Implementation Guidance

`RunConfigControllerApi` uses `Protocol` (not `ABC`) — consistent with `SettingsWidgetControllerApi`. Import `Protocol` from `typing` (already imported in `ui_controllers.py`).

For `models.py`, add `from pathlib import Path` to imports if not already present. Keep `RunStartEvent` near the other UI event dataclasses (`NewRunWidgetStartEvent`, `ProgressUpdateEvent`, etc.).

### Verification

- [ ] `from ollama_llm_bench.backend.core.models import RunStartEvent` imports without error
- [ ] `from ollama_llm_bench.backend.core.ui_controllers import RunConfigControllerApi` imports without error
- [ ] `uv run mypy src/` passes with no new errors on modified files
- [ ] `uv run pytest tests/ -q` still passes

---

## Task 4: Implement RunConfigController

**Files to create**:
- `src/ollama_llm_bench/ui/controllers/run_config_controller.py`

**Files to modify**: None

**Depends on**: Task 3

### Context

`RunConfigController` is the concrete implementation of `RunConfigControllerApi`. It replaces both `NewRunWidgetController` (creates/starts new runs using V2 `ProviderRegistry`) and `PreviousRunWidgetController` (lists unfinished runs and resumes them). It also handles pause/resume which neither old controller supported.

### Requirements

1. Class signature:
   ```python
   class RunConfigController:
       def __init__(
           self,
           *,
           data_api: DataApi,
           provider_registry: ProviderRegistryApi,
           benchmark_flow_api: BenchmarkFlowApi,
           event_bus: EventBus,
           task_file_loader: TaskFileLoaderApi,
       ) -> None: ...
   ```
2. `get_provider_names() -> list[str]`: returns `list(provider_registry.list_enabled_providers().keys())` (or equivalent). Catches exceptions and returns `[]` on failure; logs a warning.
3. `get_models_for_provider(provider_name: str) -> list[str]`: calls `provider_registry.get_provider(provider_name).list_models()` (sync call). Returns `[]` and warns on exception.
4. `get_unfinished_runs() -> list[tuple[int, str]]`: calls `get_benchmark_runs(data_api)` from `backend/utils/run_utils.py`. Returns only runs with `status == BenchmarkRunStatus.NOT_COMPLETED`.
5. `handle_start_click(event: RunStartEvent) -> None`:
   - Guard: if `benchmark_flow_api.is_running()`, emit global message and return.
   - Guard: if `event.test_models` is empty, emit message and return.
   - Create `BenchmarkRun` with V2 fields: `run_id=0`, `timestamp=datetime.now().isoformat()`, `judge_model=event.judge_model`, `status=BenchmarkRunStatus.NOT_COMPLETED`, `run_mode=event.run_mode`, `provider_id=event.test_provider`, `judge_provider_id=event.judge_provider`.
   - Persist: `run_id = data_api.create_benchmark_run(run)`.
   - Load tasks: `tasks = task_file_loader.load_from_paths(list(event.task_paths))` — if `event.task_paths` is empty, fall back to `task_file_loader.load_tasks()`.
   - Create skeleton `BenchmarkResult` for each `(model, task)` pair, with `run_id`, `task_id`, `model_name`, `provider_id=event.test_provider`.
   - Persist: `data_api.create_benchmark_results(results)`.
   - Emit: `event_bus.emit_run_id_changed(run_id)`, `event_bus.emit_log_clean()`.
   - Start: `benchmark_flow_api.start_execution(run_id)`.
6. `handle_pause_click() -> None`: calls `benchmark_flow_api.pause_execution()` if running.
7. `handle_resume_click() -> None`: calls `benchmark_flow_api.resume_execution()` if running.
8. `handle_stop_click() -> None`: calls `benchmark_flow_api.stop_execution()` if running.
9. `handle_resume_run_click(run_id: int) -> None`:
   - Guard: if running, emit message and return.
   - Retrieve run; guard: if status != NOT_COMPLETED, emit message.
   - Emit `event_bus.emit_run_id_changed(run_id)`.
   - Call `benchmark_flow_api.start_execution(run_id)`.
10. `subscribe_to_benchmark_status_change(callback)` → `event_bus.subscribe_to_background_thread_is_running(callback)`.
11. `subscribe_to_runs_change(callback)` → `event_bus.subscribe_to_run_ids_changed(callback)`. Also subscribe internally to `background_thread_is_running`: when it goes `False`, refresh runs and emit `run_ids_changed`.
12. All exceptions from `data_api` calls are caught with `except Exception`; log warning and emit global message.

### Existing Code Reference

- `src/ollama_llm_bench/ui/controllers/new_run_widget_controller.py` lines 77–141 — `handle_start_click` logic to adapt (use `RunStartEvent` instead of `NewRunWidgetStartEvent`; use `task_file_loader` instead of `task_api`)
- `src/ollama_llm_bench/ui/controllers/previous_run_widget_controller.py` lines 79–125 — refresh and resume logic
- `src/ollama_llm_bench/backend/utils/run_utils.py` — `get_benchmark_runs(data_api)` utility

### Implementation Guidance

Check whether `BenchmarkRun` dataclass in `models.py` already has `run_mode`, `provider_id`, `judge_provider_id` fields. If not, create the run with only the fields that exist — do NOT add new fields to `BenchmarkRun` in this task (that would be out of scope). Use only existing fields.

For `task_file_loader.load_from_paths()` — check the `TaskFileLoaderApi` interface in `interfaces.py`. If this method doesn't exist, fall back to `task_file_loader.load_tasks()` regardless of paths. Note this in a comment.

`BenchmarkFlowApi.pause_execution()` and `resume_execution()` — check `interfaces.py`. If not defined on the ABC, use `hasattr(benchmark_flow_api, "pause_execution")` guard and cast with `# type: ignore[attr-defined]`.

### Verification

- [ ] `from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController` imports without error
- [ ] `RunConfigController` satisfies `RunConfigControllerApi` Protocol (use `isinstance(ctrl, RunConfigControllerApi)` or verify via mypy)
- [ ] `uv run pytest tests/ -q` still passes

---

## Task 5: Build RunConfigPanel (New Left Panel)

**Files to create**:
- `src/ollama_llm_bench/ui/widgets/panels/run_config_panel.py`

**Files to modify**: None

**Depends on**: Tasks 2, 3, 4

### Context

`RunConfigPanel` is the new left panel that replaces `ControlPanel` + `ControlTabWidget` + `NewRunWidget` + `PreviousRunWidget`. It provides mode selection, provider/model selection, task file management, advanced options, action buttons, and a previous runs section — all in a single scrollable panel.

### Requirements

1. Class signature: `class RunConfigPanel(QWidget): def __init__(self, *, controller: RunConfigControllerApi, parent: QWidget | None = None) -> None`
2. Panel structure (top to bottom, inside a `QScrollArea`):
   - **Mode section** (`QGroupBox` title "Run Mode"): three `QRadioButton` in a `QButtonGroup` — "Speed", "Full Grading" (default checked), "Prompt Eval"
   - **Judge section** (`QGroupBox` title "Judge"): `QComboBox` for provider + `QComboBox` for model, both with labels; populated from `controller.get_provider_names()` on init
   - **Test Models section** (`QGroupBox` title "Test Models"): `QComboBox` for provider + `QListWidget` (checkboxes via `Qt.ItemFlag.ItemIsUserCheckable`) + "Select All" / "Clear All" `QPushButton` rows; model list refreshed when provider combo changes
   - **Task Files section** (`QGroupBox` title "Task Files"): `QListWidget` showing added YAML files + "Add File" (`QFileDialog`) + "Add Folder" (`QFileDialog`) buttons + remove button per item; drag-and-drop hint `QLabel` below list
   - **Advanced section** (collapsible `QGroupBox` title "Advanced ▸"): `QCheckBox` "Enable Streaming" (checked by default) + `QCheckBox` "Enable Warmup" (checked) + `QComboBox` "Reasoning" with options ["default", "low", "medium", "high"]
   - **Action bar** (`QHBoxLayout` below the scroll area, NOT inside scroll): `QPushButton("▶ Start", role="primary")`, `QPushButton("⏸ Pause", role="secondary")`, `QPushButton("⏹ Stop", role="secondary")`. Properties set via `widget.setProperty("role", "primary")` then `widget.style().unpolish(widget); widget.style().polish(widget)` after setting property.
   - **Previous Runs section** (`QGroupBox` title "Previous Runs"): `QComboBox` populated from `controller.get_unfinished_runs()` + "Resume" `QPushButton` + "Refresh" `QPushButton`
3. Widget state rules (controlled by `_on_benchmark_status_changed(is_running: bool)`):
   - When running: disable mode buttons, judge combos, test model list, task file section, Add buttons, Start button. Enable only Pause and Stop.
   - When paused: Pause button text changes to "▶ Resume". (Subscribe to `BenchmarkPausedEvent` / `BenchmarkResumedEvent` from event_bus if available, or track internally.)
   - When idle: re-enable all, reset Pause button text.
4. Start button click flow:
   - Read mode, judge provider/model, selected test models (checked items), task paths from list, advanced options.
   - Guard: if no test models checked, show `QMessageBox.warning(...)`.
   - Construct `RunStartEvent(run_mode=..., judge_provider=..., judge_model=..., test_provider=..., test_models=tuple(...), task_paths=tuple(...), ...)`.
   - Call `controller.handle_start_click(event)`.
5. Subscribe to `controller.subscribe_to_benchmark_status_change(self._on_benchmark_status_changed)`.
6. Subscribe to `controller.subscribe_to_runs_change(self._update_previous_runs_combo)`.
7. Drag-and-drop for YAML files onto task files list: use existing `DragDropHandler` from `ui/qt_classes/drag_drop_handler.py`; connect its `yaml_file_dropped` signal to `_add_task_file(path: Path)`.
8. Collapsible Advanced section: clicking the group box title toggles the inner widget visibility. Implement via `QGroupBox.setCheckable(True)` and `toggled` signal, or a simple boolean toggle on a child `QWidget`.

### Existing Code Reference

- `src/ollama_llm_bench/ui/widgets/panels/control/new_run_widget.py` — model list widget pattern (QListWidget + checkboxes)
- `src/ollama_llm_bench/ui/widgets/panels/control/previous_run_widget.py` — previous runs combo + refresh/resume pattern
- `src/ollama_llm_bench/ui/qt_classes/drag_drop_handler.py` — `DragDropHandler` for YAML drag-drop

### Implementation Guidance

**QListWidget checkboxes**:
```python
item = QListWidgetItem(model_name)
item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
item.setCheckState(Qt.CheckState.Unchecked)
```

**Reading checked models**:
```python
models = [
    self._models_list.item(i).text()
    for i in range(self._models_list.count())
    if self._models_list.item(i).checkState() == Qt.CheckState.Checked
]
```

**QProperty role for styled buttons** — must be set before widget is shown, or call `unpolish/polish` cycle after `setProperty`:
```python
btn.setProperty("role", "primary")
btn.style().unpolish(btn)
btn.style().polish(btn)
```

**Collapsible Advanced section**: simplest implementation — `QGroupBox` with `setCheckable(True)` + `setChecked(False)`. The group box greys out unchecked children automatically; read values even when collapsed.

Keep the outer layout as: `QVBoxLayout(self)` → `QScrollArea` (stretches) + `QWidget` action bar (fixed height). This ensures action buttons are always visible.

### Verification

- [ ] `from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel` imports without error
- [ ] App still starts (old panels not yet replaced — this file is new, not yet wired)
- [ ] `uv run pytest tests/ -q` still passes

---

## Task 6: Enhance LogWidget with Filter Bar

**Files to modify**:
- `src/ollama_llm_bench/ui/widgets/panels/result/log_widget.py`

**Depends on**: None

### Context

The current `LogWidget` has a plain "Clean" button and no filtering. The design requires a filter bar with verbosity selector and free-text search so the user can control log density during long benchmark runs.

### Requirements

1. Add a filter bar at the top of the widget layout (above the text edit), containing:
   - `QLabel("Verbosity:")` 
   - `_verbosity_combo: QComboBox` with items: `"Minimal"`, `"Normal"` (default), `"Verbose"`
   - `QLabel("Search:")` 
   - `_search_edit: QLineEdit` with placeholder `"Filter log…"` and clear button (`setClearButtonEnabled(True)`)
   - `_clean_button: QPushButton("🗑 Clear")` (keep existing clean button, move it to filter bar)
2. Add `_verbosity_level: int` instance variable (0=Minimal, 1=Normal, 2=Verbose). Default: 1.
3. Verbosity filtering applied at emit time (not by replaying buffer):
   - `Minimal` (0): show only `_on_task_completed` and `_on_judge_completed` entries; suppress streaming chunks and `_on_benchmark_started/finished/stopped` entries.
   - `Normal` (1): current behavior — show everything (default).
   - `Verbose` (2): same as Normal for now (reserved for future per-request detail).
4. Connect `_verbosity_combo.currentIndexChanged` to `_on_verbosity_changed(index: int)` which sets `_verbosity_level = index`.
5. Search filter: connect `_search_edit.textChanged` to `_on_search_changed(text: str)` which stores `_search_text: str`. When appending HTML, if `_search_text` is non-empty and the raw text of the entry does NOT contain `_search_text` (case-insensitive), skip the `_append_html` call. Note: streaming chunks bypass search filter (they are buffered tokens, not searchable entries).
6. Layout order: filter bar (`QHBoxLayout`) → `_text_edit` (stretch=1) → jump row (`QHBoxLayout`).

### Existing Code Reference

- `src/ollama_llm_bench/ui/widgets/panels/result/log_widget.py` lines 55–79 — `_create_widgets`, `_configure_widgets`, `_build_layout` to modify
- `src/ollama_llm_bench/ui/widgets/panels/result/log_widget.py` lines 128–153 — event handlers; add verbosity check at top of `_on_streaming_chunk`, `_on_benchmark_started`, `_on_benchmark_finished`, `_on_benchmark_stopped`

### Implementation Guidance

Add guard to `_on_streaming_chunk`:
```python
def _on_streaming_chunk(self, event: StreamingChunkEvent) -> None:
    if self._verbosity_level < 1:  # Minimal — suppress streaming
        return
    self._chunk_buffer.append(event.chunk_text)
```

Add search guard to `_on_task_completed` and `_on_judge_completed`:
```python
if self._search_text and self._search_text.lower() not in f"{event.model.model_name} {event.task_id}".lower():
    return
```

### Verification

- [ ] `uv run pytest tests/ -q` still passes (no broken imports)
- [ ] App starts and the log widget shows a filter bar (visual check after Task 9)

---

## Task 7: Build CenterPanel (Progress + Log)

**Files to create**:
- `src/ollama_llm_bench/ui/widgets/panels/center_panel.py`

**Files to modify**: None

**Depends on**: Tasks 2, 6

### Context

The center panel houses the `ProgressPanelWidget` (already implemented) at the top and the `LogWidget` (enhanced in Task 6) below. Moving the log from the right panel into the center creates the three-panel layout intended by the V2 design.

### Requirements

1. Class signature:
   ```python
   class CenterPanel(QWidget):
       def __init__(self, *, event_bus: EventBus, app_settings: AppSettingsServiceApi, parent: QWidget | None = None) -> None
   ```
2. Layout: `QVBoxLayout` with no margins (0,0,0,0):
   - `ProgressPanelWidget(event_bus=event_bus)` — fixed: `setMaximumHeight(200)`, `setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)`
   - A 1px horizontal line separator (`QFrame` with `HLine` shape and `Sunken` shadow)
   - `LogWidget(event_bus=event_bus, app_settings=app_settings)` — stretch=1 (fills remaining)
3. Both child widgets are created in `__init__` and stored as `self._progress_panel` and `self._log_widget`.
4. No other logic — just composition.

### Existing Code Reference

- `src/ollama_llm_bench/ui/widgets/panels/progress_panel_widget.py` — `ProgressPanelWidget.__init__` signature: `(*, event_bus: EventBus, parent: QWidget | None = None)`
- `src/ollama_llm_bench/ui/widgets/panels/result/log_widget.py` — `LogWidget.__init__` signature: `(*, event_bus: EventBus, app_settings: AppSettingsServiceApi)`

### Implementation Guidance

```python
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget
from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, EventBus
from ollama_llm_bench.ui.widgets.panels.progress_panel_widget import ProgressPanelWidget
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget

class CenterPanel(QWidget):
    def __init__(self, *, event_bus: EventBus, app_settings: AppSettingsServiceApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress_panel = ProgressPanelWidget(event_bus=event_bus)
        self._progress_panel.setMaximumHeight(200)
        self._progress_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self._log_widget = LogWidget(event_bus=event_bus, app_settings=app_settings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._progress_panel)
        layout.addWidget(separator)
        layout.addWidget(self._log_widget, 1)
```

### Verification

- [ ] `from ollama_llm_bench.ui.widgets.panels.center_panel import CenterPanel` imports without error
- [ ] `uv run pytest tests/ -q` still passes

---

## Task 8: Update Result Models and ResultWidget with V2 Columns

**Files to modify**:
- `src/ollama_llm_bench/backend/core/models.py`
- `src/ollama_llm_bench/backend/services/app_result_api.py`
- `src/ollama_llm_bench/ui/widgets/panels/result/result_widget.py`
- `src/ollama_llm_bench/ui/widgets/panels/results_panel.py`

**Depends on**: None (but must be complete before Task 9)

### Context

The V2 evaluation pipeline stores TTFT, cosine scores, and resolution layer in `BenchmarkResult`. The summary and detailed tables need to expose these. `AvgSummaryTableItem` and `SummaryTableItem` are extended, `AppResultApi` is updated to populate them, and `ResultWidget` displays the new columns.

The `results_panel.py` currently wraps `ResultTabWidget` (which has Log + Results tabs). Since the log moves to CenterPanel, the results panel will directly contain `ResultWidget`.

### Requirements

1. Extend `AvgSummaryTableItem` in `models.py` (line 331):
   ```python
   @dataclass(frozen=True)
   class AvgSummaryTableItem:
       model_name: str = ""
       avg_time_ms: float = 0.0
       avg_tokens_per_second: float = 0.0
       avg_score: float = 0.0
       avg_ttft_ms: float | None = None      # None when not streaming
       pass_rate: float = 0.0                # 0.0–1.0
   ```
2. Extend `SummaryTableItem` in `models.py` (line 341):
   ```python
   @dataclass(frozen=True)
   class SummaryTableItem:
       model_name: str = ""
       task_id: str = ""
       task_status: str = ""
       time_ms: int = 0
       tokens: int = 0
       tokens_per_second: float = 0.0
       score: float = 0.0
       score_reason: str = ""
       cosine_similarity: float | None = None    # None when layer 3 not run
       resolution_layer: str = ""                # e.g. "L1:rules", "L4:judge"
   ```
3. Update `AppResultApi` to compute new fields:
   - `pass_rate`: count results with `final_verdict == EvalVerdict.PASS` / total for model
   - `avg_ttft_ms`: average of `ttft_ms` values where not None
   - `cosine_similarity`: from `BenchmarkResult.cosine_gauge_score` field (or the actual cosine field name — read the full `BenchmarkResult` definition)
   - `resolution_layer`: from `BenchmarkResult.resolution_layer` — format as `"L1:rules"`, `"L2:keywords"`, `"L3:cosine"`, `"L4:judge"` based on `EvalLayer` enum value. If None/empty, use `""`.
   - Before implementing, read the full `BenchmarkResult` definition in `models.py` to confirm actual field names for ttft, cosine, verdict, and resolution layer.
4. Update `SUMMARY_TABLE_CONFIG` in `result_widget.py`:
   - New headers: `["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE", "PASS%", "AVG. TTFT (ms)"]`
   - 6 columns; numeric_columns: `[1, 2, 3, 4, 5]`
5. Update `DETAILED_TABLE_CONFIG` in `result_widget.py`:
   - New headers: `["MODEL", "TASK", "STATUS", "TIME (ms)", "TOKENS", "TOKENS/s", "SCORE", "COSINE", "LAYER", "REASON"]`
   - 10 columns; numeric_columns: `[3, 4, 5, 6, 7]`
6. Update `_on_summary_data_changed` row formatter:
   ```python
   [
       item.model_name,
       f"{item.avg_time_ms / 1000:.2f}",
       f"{item.avg_tokens_per_second:.2f}",
       f"{item.avg_score:.2f}",
       f"{item.pass_rate * 100:.1f}%",
       f"{item.avg_ttft_ms:.0f}" if item.avg_ttft_ms is not None else "N/A",
   ]
   ```
7. Update `_on_detailed_data_changed` row formatter to include `cosine_similarity` (formatted as `f"{item.cosine_similarity:.2f}"` or `"N/A"` if None) and `resolution_layer`.
8. Update `results_panel.py`:
   - Remove import of `ResultTabWidget`
   - Import `ResultWidget` and `ResultWidgetControllerApi` directly
   - Change `__init__` to accept `controller: ResultWidgetControllerApi` instead of `ctx: AppContext`
   - Create `ResultWidget(controller)` directly; no tab wrapper

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` lines 331–351 — current `AvgSummaryTableItem` and `SummaryTableItem`
- `src/ollama_llm_bench/backend/services/app_result_api.py` — `compute_summary()` method; read full file to understand current aggregation
- `src/ollama_llm_bench/ui/widgets/panels/result/result_widget.py` lines 64–74 — `SUMMARY_TABLE_CONFIG` and `DETAILED_TABLE_CONFIG` to update
- `src/ollama_llm_bench/ui/widgets/panels/result/result_widget.py` lines 303–345 — data handlers to update

### Implementation Guidance

Map `EvalLayer` enum to label strings in `app_result_api.py`:
```python
_LAYER_LABELS: dict[str, str] = {
    EvalLayer.RULE_BASED.value: "L1:rules",
    EvalLayer.KEYWORD.value: "L2:keywords",
    EvalLayer.COSINE.value: "L3:cosine",
    EvalLayer.LLM_JUDGE.value: "L4:judge",
}
```

For `results_panel.py`, the constructor change to accept `controller` (not `ctx`) means Task 9 must pass the controller explicitly when creating `ResultsPanel`.

### Verification

- [ ] `uv run pytest tests/ -q` passes with no regressions
- [ ] `from ollama_llm_bench.ui.widgets.panels.results_panel import ResultsPanel` imports without error
- [ ] `ResultsPanel` no longer imports `ResultTabWidget`

---

## Task 9: Final Wiring — 3-Panel Layout, MainWindow, Theme, app_context.py

**Files to modify**:
- `src/ollama_llm_bench/ui/widgets/central_widget.py`
- `src/ollama_llm_bench/ui/main_window.py`
- `src/ollama_llm_bench/main.py`
- `src/ollama_llm_bench/app_context.py`

**Depends on**: Tasks 1, 4, 5, 7, 8

### Context

This is the integration task that connects all new panels to the running application. `CentralWidget` switches from 2-panel to 3-panel, `MainWindow` sets minimum size and updates title, `main.py` applies the QSS theme, and `app_context.py` wires `RunConfigController` into `ApplicationContext`.

### Requirements

1. **`central_widget.py`** — replace 2-panel with 3-panel:
   - Import `RunConfigPanel`, `CenterPanel`, `ResultsPanel`
   - Remove imports of `ControlPanel`
   - Constructor: accept `ctx: AppContext` (unchanged)
   - Create three panels:
     ```python
     self._run_config_panel = RunConfigPanel(controller=ctx.get_run_config_controller())
     self._center_panel = CenterPanel(event_bus=ctx.get_event_bus(), app_settings=ctx.get_app_settings_service())
     self._results_panel = ResultsPanel(controller=ctx.get_result_widget_controller_api())
     ```
   - `_setup_layout`: `QSplitter(Qt.Orientation.Horizontal)` with all 3 panels; sizes `[280, 600, 440]`; min widths via `setMinimumWidth` on each panel (`250`, `320`, `380`)
   - Update constants: `_LEFT_DEFAULT_WIDTH = 280`, `_CENTER_DEFAULT_WIDTH = 600`, `_RIGHT_DEFAULT_WIDTH = 440`
2. **`main_window.py`**:
   - Change `_WINDOW_TITLE` to `"Ollama LLM Bench v2.0"`
   - Add `self.setMinimumSize(1200, 700)` in `_setup_ui()`
   - Keep all other logic unchanged
3. **`main.py`**:
   - After `app = QApplication(sys.argv)` and before `ContextProvider.initialize(...)`, add:
     ```python
     from ollama_llm_bench.ui.style.theme_loader import apply_theme
     apply_theme(app, "dark")
     ```
   - After context is initialized, re-read the saved theme and reapply if different:
     ```python
     saved_theme = ctx.get_app_settings_service().get_setting("ui.theme") or "dark"
     apply_theme(app, saved_theme)
     ```
4. **`app_context.py`** — add `RunConfigController`:
   - Import `RunConfigController` from `ui/controllers/run_config_controller.py`
   - Import `RunConfigControllerApi` from `backend/core/ui_controllers.py`
   - Add `_run_config_controller` to `ApplicationContext.__slots__`
   - Add `run_config_controller: RunConfigControllerApi` parameter to `ApplicationContext.__init__`
   - Add `@override def get_run_config_controller(self) -> RunConfigControllerApi: return self._run_config_controller`
   - In `_create_app_context()`: instantiate `RunConfigController(data_api=data_api, provider_registry=registry, benchmark_flow_api=benchmark_flow_api, event_bus=event_bus, task_file_loader=task_loader)` and pass to `ApplicationContext(run_config_controller=...)`
   - Keep old `NewRunWidgetController`, `PreviousRunWidgetController` wiring in place — they are removed in Task 10

### Existing Code Reference

- `src/ollama_llm_bench/ui/widgets/central_widget.py` lines 1–89 — full file to replace
- `src/ollama_llm_bench/ui/main_window.py` lines 13–14 — title constant; lines 40–42 — `_setup_ui` to add `setMinimumSize`
- `src/ollama_llm_bench/main.py` lines 146–155 — `QApplication` creation and context init; add theme calls
- `src/ollama_llm_bench/app_context.py` lines 80–100 — `__slots__`; lines 102–143 — `__init__`; lines 388–546 — `_create_app_context()`

### Implementation Guidance

For `central_widget.py`, set minimum widths on the panels themselves before adding to splitter:
```python
self._run_config_panel.setMinimumWidth(250)
self._center_panel.setMinimumWidth(320)
self._results_panel.setMinimumWidth(380)
splitter.addWidget(self._run_config_panel)
splitter.addWidget(self._center_panel)
splitter.addWidget(self._results_panel)
splitter.setSizes([280, 600, 440])
```

For `app_context.py`, `AppSettingsServiceApi.get_setting(key)` returns `str | None`. Use:
```python
saved_theme = ctx.get_app_settings_service().get_setting("ui.theme") or "dark"
```

### Verification

- [ ] `uv run ollama_llm_bench` starts and shows 3-panel layout
- [ ] Left panel has mode selector, judge section, test models, task files, action buttons
- [ ] Center panel has progress widget (top) and log (bottom)
- [ ] Right panel has result tables directly (no tab bar)
- [ ] QSS dark theme is applied (dark background, teal accents)
- [ ] `uv run pytest tests/ -q` passes

---

## Task 10: Remove Replaced UI Files and Old Controller Wiring

**Files to delete**:
- `src/ollama_llm_bench/ui/widgets/panels/control_panel.py`
- `src/ollama_llm_bench/ui/widgets/panels/control/control_tab_widget.py`
- `src/ollama_llm_bench/ui/widgets/panels/control/new_run_widget.py`
- `src/ollama_llm_bench/ui/widgets/panels/control/previous_run_widget.py`
- `src/ollama_llm_bench/ui/widgets/panels/result/result_tab_widget.py`
- `src/ollama_llm_bench/ui/controllers/new_run_widget_controller.py`
- `src/ollama_llm_bench/ui/controllers/previous_run_widget_controller.py`

**Files to modify**:
- `src/ollama_llm_bench/backend/core/ui_controllers.py`
- `src/ollama_llm_bench/backend/core/interfaces.py`
- `src/ollama_llm_bench/app_context.py`
- Any test files that import the deleted controllers or widgets

**Depends on**: Task 9

### Context

After Task 9, the old panels and controllers are unreferenced dead code. This task removes them and cleans up the core layer interfaces, reducing maintenance burden and preventing confusion.

### Requirements

1. Delete the 7 files listed above.
2. Remove from `ui_controllers.py`:
   - `NewRunWidgetControllerApi` class definition
   - `PreviousRunWidgetControllerApi` class definition
   - `NewRunWidgetStartEvent` import (it can stay in `models.py` for backward compatibility, or also be removed)
3. Remove from `interfaces.py` `AppContext` ABC:
   - `get_new_run_widget_controller_api()` abstract method
   - `get_previous_run_widget_controller_api()` abstract method
   - Imports of `NewRunWidgetControllerApi`, `PreviousRunWidgetControllerApi` from `ui_controllers`
4. Remove from `app_context.py`:
   - `_new_run_widget_controller_api` and `_previous_run_widget_controller_api` from `__slots__`
   - Their constructor parameters and assignment in `__init__`
   - Their getter methods `get_new_run_widget_controller_api()`, `get_previous_run_widget_controller_api()`
   - Their instantiation in `_create_app_context()`
   - Their passing to `ApplicationContext(...)`
   - Imports of `NewRunWidgetController`, `PreviousRunWidgetController`
5. Update or delete any tests in `tests/` that import deleted controllers, widgets, or ABCs. If tests cover behavior that still exists (model validation logic, etc.), migrate them to test `RunConfigController` instead.
6. Verify no remaining references via: `grep -r "NewRunWidgetController\|PreviousRunWidgetController\|ControlTabWidget\|ControlPanel\|ResultTabWidget\|NewRunWidget\|PreviousRunWidget" src/ tests/`

### Existing Code Reference

- `src/ollama_llm_bench/app_context.py` lines 491–524 — old controller instantiation to remove
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 44–50 — controller imports; search for `get_new_run_widget_controller_api` and `get_previous_run_widget_controller_api` method definitions

### Implementation Guidance

Run `grep -r "NewRunWidgetController\|PreviousRunWidgetController\|ControlTabWidget\|ResultTabWidget" src/ tests/` before starting to find all references. Fix each reference before deleting the files.

After deletion, run `uv run ruff check src/ tests/` to catch unused imports introduced by the removals.

### Verification

- [ ] `grep -r "NewRunWidgetController\|PreviousRunWidgetController\|ControlPanel\|ResultTabWidget" src/` returns no results
- [ ] `uv run ollama_llm_bench` still starts correctly
- [ ] `uv run pytest tests/ -q` passes
- [ ] `uv run ruff check src/ tests/` passes with no F401 errors

---

## Final Verification Checklist

When ALL tasks are complete, verify end-to-end:

- [ ] All tests pass: `uv run pytest tests/ -q --tb=short`
- [ ] No type errors: `uv run mypy src/`
- [ ] No lint errors: `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`
- [ ] App starts without errors: `uv run ollama_llm_bench`
- [ ] 3-panel layout visible at 1200 × 800 window size
- [ ] Dark theme applied on startup (dark background, teal accents)
- [ ] Panels are resizable via splitter handles
- [ ] Left panel: mode radio buttons, provider combos, model checklist, task files list, Start/Pause/Stop buttons, Previous Runs section
- [ ] Center panel: progress badge + bar + ETA at top; filter bar + log text area below
- [ ] Right panel: summary table with TTFT and Pass% columns; detailed table with Cosine and Layer columns
- [ ] Settings dialog still accessible via File → Settings menu
- [ ] No hardcoded hex colors remain in any new/modified file (grep for `#[0-9A-Fa-f]{6}` in `ui/widgets/`)
- [ ] No Qt imports in `backend/core/` or `backend/services/`
- [ ] All new classes use constructor DI with keyword-only args
- [ ] Type annotations on all public methods
- [ ] `CLAUDE.md` Architecture section updated to reflect 3-panel layout and new panel names
