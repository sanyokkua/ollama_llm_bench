---
name: pyside6-ui
description: |
  PySide6 desktop UI development — styling, theming, custom widgets, layouts, threading, signals/slots, QSS, and Model/View.
  Use this skill whenever implementing, modifying, or reviewing PySide6 user interface code. Triggers include: any PySide6 widget work,
  QSS stylesheet creation or editing, Qt theming or design tokens, custom widget painting, QThreadPool threading, signal/slot wiring,
  Model/View table implementation, dialog construction, layout composition, or any desktop UI task involving Qt Widgets.
  Also use when the user mentions "Qt styling", "dark/light theme", "QSS", "widget states", "PySide layout", "QTableView",
  "QSplitter", "progress bar styling", "custom QPainter widget", or any PySide6 UI-adjacent term — even if they don't
  explicitly say "use the PySide6 skill". If a task touches `.qss` files, `tokens.py`, or any file under `ui/` in a PySide6 project, use this skill.
---

# PySide6 UI Development — Best Practices & Design System

This skill covers everything needed to build professional, themeable PySide6 desktop applications: architecture constraints, QSS theming via design tokens, widget construction patterns, threading safety, signal/slot wiring, and Model/View tables.

## How This Skill Is Organized

The SKILL.md you're reading now contains the core rules and patterns — the things you need in context for every PySide6 UI task. Deeper reference material lives in `references/`:

| When you need…                                        | Read                                |
|-------------------------------------------------------|-------------------------------------|
| Complete QSS template with all selectors + tokens     | `references/qss-theme-template.md`  |
| Design tokens (full DARK/LIGHT/SHARED dicts)          | `references/design-tokens.md`       |
| Widget construction patterns with code                | `references/widget-patterns.md`     |
| PySide6 threading rules and QRunnable pattern         | `references/threading-guide.md`     |

Read the relevant reference file before writing code in that area. The references contain exact code, exact selectors, and exact token values — don't guess.

---

## 1. Architecture Layer Rules

PySide6 projects following this pattern use a strict layered architecture. Violating these boundaries creates coupling bugs that are painful to fix later.

**Layer dependency direction** (arrows = "is allowed to import"):

```
ui/widgets/ → ui/controllers/ → qt_classes/ → services/ → core/
                                                            ↑
                                                          utils/
```

**Hard constraints:**

- **`core/`** — Pure Python. No `PySide6`, no `ollama`, no `yaml`. Only dataclasses, enums, ABCs, SQL strings, prompt templates, constants. This layer defines what the app *is* without saying how it renders or communicates.
- **`services/`** — No Qt imports. Concrete implementations (API clients, data access, task loading) live here. Must be unit-testable without a `QApplication` running.
- **`qt_classes/`** — The *only* place that creates `QRunnable` or `QThreadPool`. All threaded work lives here.
- **`ui/controllers/`** — Mediate between widgets and services. Widgets never instantiate a service or touch SQLite directly.
- **`ui/widgets/`** — Rendering only. Talk to backend through controllers. Update only via signal/slot from `QtEventBus`.
- **All background-to-UI communication flows through signals** (`QtEventBus`). No `QMetaObject.invokeMethod`, no direct widget mutation from worker threads.
- **All dependencies injected via constructor** (keyword-only args). No internal instantiation of collaborators.
- **Absolute imports only**: `from ollama_llm_bench.core.models import BenchmarkRun`

---

## 2. QSS Theming System

PySide6 uses Qt Style Sheets (QSS) — a CSS-like language with important limitations. Getting this wrong means your app looks broken on some platforms or your styles silently don't apply.

### What QSS Supports

Supported properties: `background`, `background-color`, `color`, `border`, `border-radius`, `padding`, `margin`, `font-size`, `font-weight`, `font-family`, `min-height`, `min-width`, `max-height`, `max-width`.

Supported sub-controls: `::drop-down`, `::down-arrow`, `::chunk`, `::handle`, `::indicator`, `::tab`, `::pane`, `::section`, `::add-line`, `::sub-line`.

Supported pseudo-states: `:hover`, `:pressed`, `:disabled`, `:focus`, `:checked`, `:unchecked`, `:selected`, `:!selected`.

### What QSS Does NOT Support

These are browser-CSS features that silently fail in PySide6 — never use them:

- `box-shadow` — no shadow support at all
- `transition` or `animation` — no CSS transitions
- `opacity` property — use RGBA colors or QPainter alpha instead
- CSS gradients with color-stops (`linear-gradient(...)`) — use `qlineargradient()` syntax instead
- `:hover` on non-interactive widgets (QLabel, QFrame) — hover only works on buttons, inputs, etc.
- `transform`, `filter`, `backdrop-filter`
- CSS Grid or Flexbox — use Qt layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`)
- CSS variables (`var(--name)`) — use Python string replacement with `{token}` placeholders

### Design Token Architecture

Instead of hardcoding hex colors, use a token-based system:

1. **`tokens.py`** defines Python dicts (`DARK`, `LIGHT`, `SHARED`) mapping token names to values
2. **`.qss` template files** use `{token_name}` placeholders in place of literal values
3. **`theme_loader.py`** reads the QSS template, merges the selected theme dict with SHARED, calls `.format(**merged)`, and applies to `QApplication`

This means theme switching is a single operation: load a different dict, re-format the QSS, re-apply.

```python
# theme_loader.py pattern
def apply_theme(app: QApplication, theme: str = "dark") -> None:
    tokens = {**SHARED, **(DARK if theme == "dark" else LIGHT)}
    qss_path = Path(__file__).parent / f"theme_{theme}.qss"
    template = qss_path.read_text()
    app.setStyleSheet(template.format(**tokens))
```

See `references/design-tokens.md` for the complete token dicts and `references/qss-theme-template.md` for the full QSS template.

### Property-Based Styling

Use `setProperty()` + QSS attribute selectors to give widgets different visual roles without subclassing:

```python
button.setProperty("role", "primary")    # → QPushButton[role="primary"]
button.setProperty("role", "danger")     # → QPushButton[role="danger"]
label.setProperty("role", "heading")     # → QLabel[role="heading"]
label.setProperty("verdict", "pass")     # → QLabel[verdict="pass"]
dot.setProperty("health", "live")        # → QLabel[health="live"]
button.setProperty("size", "small")      # → QPushButton[size="small"]
```

**After changing a property at runtime, you must re-polish the widget** or the QSS won't update:

```python
widget.setProperty("verdict", "fail")
widget.style().unpolish(widget)
widget.style().polish(widget)
```

This is a common source of bugs — if your property-based style doesn't apply, check that you're calling unpolish/polish.

### Color Rules

1. **Never hardcode hex colors in widget Python code.** Always reference tokens. If you need a color in Python (e.g., for QPainter), read it from the token dict.
2. **PASS = success color**, FAIL = failure color. Consistent everywhere.
3. **Scores display as 0.00–1.00** (never 0–100). Format is controlled by a user setting.
4. **Chart color cycle**: primary → accent → failure (for ranking visualizations).
5. **Resolution layer colors**: L1 = failure, L2 = warning, L3 = accent, L4 = primary.

---

## 3. Layout Patterns

### The Three-Panel Splitter

The main app uses a horizontal `QSplitter` with three panes:

- **Left panel** (config): 280px default, 250px minimum
- **Center panel** (progress + log): flexible, expands to fill
- **Right panel** (results): 440px default, 380px minimum
- **Minimum window size**: 1200 × 700 px

```python
splitter = QSplitter(Qt.Orientation.Horizontal)
splitter.addWidget(left_panel)
splitter.addWidget(center_panel)
splitter.addWidget(right_panel)
splitter.setSizes([280, 480, 440])  # initial sizes
splitter.setStretchFactor(0, 0)     # left: don't stretch
splitter.setStretchFactor(1, 1)     # center: stretch
splitter.setStretchFactor(2, 0)     # right: don't stretch
```

### Spacing Constants

Use these consistently — don't invent new values:

| Token | Value | Use for |
|-------|-------|---------|
| `spacing_xs` | 4px | Inline gaps, icon padding |
| `spacing_sm` | 8px | List item gaps, checkbox-label gap |
| `spacing_md` | 12px | Widget padding, group gaps |
| `spacing_lg` | 16px | Section padding, panel padding |
| `spacing_xl` | 24px | Section margins, dialog padding |

| Radius | Value | Use for |
|--------|-------|---------|
| `radius_sm` | 4px | Checkboxes, small badges, tooltips |
| `radius_md` | 6px | Buttons, inputs, combo boxes, cards |
| `radius_lg` | 8px | Dialogs, group boxes, panels |
| pill | 10px | Progress bar, pill badges |

### Layout Best Practices

- Set margins explicitly: `layout.setContentsMargins(16, 16, 16, 16)`
- Set spacing explicitly: `layout.setSpacing(8)`
- **Panel padding**: 16px on all sides
- **Section gaps**: 16px between sections, 8px between widgets within a section
- **All scrollable areas**: Use `QScrollArea` with 8px-wide styled scrollbar
- **Splitter handle**: 5px wide, border color normally, primary color on hover
- Nest layouts freely: `outer_layout.addLayout(inner_layout)`
- Use `QStackedLayout` or `QTabWidget` for multi-page views

---

## 4. Typography

| Element | Font | Size | Weight | QSS Target |
|---------|------|------|--------|-----------|
| Window title | Sans | 15px | 700 | `QLabel[role="title"]` |
| Section heading | Sans | 11px uppercase | 700 | `QLabel[role="heading"]` |
| Body text | Sans | 13px | 400 | `QLabel` |
| Secondary text | Sans | 12px | 400 | `QLabel[role="secondary"]` |
| Button text | Sans | 13px | 600 | `QPushButton` |
| Small button | Sans | 11px | 600 | `QPushButton[size="small"]` |
| Table header | Sans | 11px uppercase | 600 | `QHeaderView::section` |
| Table cell | Sans | 12px | 400 | `QTableView` |
| Mono cell | Mono | 11px | 400 | `QTableView` (font-family on cell) |
| Log response | Mono | 12px | 400 | `QTextEdit[role="log"]` |
| Badge text | Sans | 11px | 700 | `QLabel[role="badge"]` |
| Progress % | Sans | 11px | 600 | `QProgressBar` text |

Font stacks:
- **Sans**: `"Segoe UI", "SF Pro Display", Ubuntu, "Noto Sans", sans-serif`
- **Mono**: `"JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace`

---

## 5. Signal/Slot & Event Patterns

### Fundamentals

- Connect signals to slots in `__init__`, after all widgets are created
- One signal can connect to multiple slots; one slot can receive from multiple signals
- Signals are thread-safe — they're the bridge between worker threads and the GUI
- Events bubble up the widget hierarchy. Call `e.accept()` to stop bubbling, `e.ignore()` to let it continue

### Custom Signals

Define on `QObject` subclasses (not on `QRunnable`):

```python
class WorkerSignals(QObject):
    finished = Signal(int)
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(tuple)
```

### Event Bus Pattern

All background-to-UI communication goes through a centralized event bus using typed event dataclasses:

```python
# In a worker (background thread):
self.signals.progress.emit((event_type, event_data))

# In a controller (main thread, connected to signal):
def _on_progress(self, payload: tuple) -> None:
    event_type, data = payload
    if event_type == "task_completed":
        self._widget.update_progress(data)
```

Widgets never subscribe directly to worker signals — controllers mediate.

### State Management

- Store application state in Python instance variables, not just widget state
- `self.is_running = False` — explicit flag, not derived from widget enabled state
- Widget enabled/disabled states are *effects* of state changes, not the source of truth

---

## 6. Interaction Rules

These behavioral patterns keep the UI consistent:

1. **During benchmark run**: Left panel controls are disabled (QSS `:disabled`). Only Pause and Stop buttons stay active.
2. **Pause button**: Toggle text between "Pause" ↔ "Resume". Color switches to warning when paused.
3. **Table row selection**: Clicking a row in the summary table filters the detailed table below. Use `selection-background-color` token.
4. **Log auto-scroll**: Enabled by default. Disable when user scrolls up manually. Show a "Jump to bottom" button (fixed `QPushButton` at log bottom edge).
5. **Drag-and-drop**: Border changes to primary color (dashed 2px). Background tints with primary at low alpha.
6. **Streaming text**: Append to `QTextEdit` at max 20 Hz. **Never call `append()` per token** — buffer and batch updates with a `QTimer`.
7. **Theme switching**: Re-apply QSS via `theme_loader.apply_theme()`. No widget recreation needed.

---

## 7. Dialog Patterns

```python
# Standard dialog construction
dlg = QDialog(parent=self)  # parent for centering
dlg.setWindowTitle("Confirm Action")
dlg.setMinimumWidth(400)

layout = QVBoxLayout(dlg)
layout.setContentsMargins(24, 24, 24, 24)
layout.setSpacing(16)

# Content
msg = QLabel("Are you sure?")
layout.addWidget(msg)

# Button box
buttons = QDialogButtonBox(
    QDialogButtonBox.Ok | QDialogButtonBox.Cancel
)
buttons.accepted.connect(dlg.accept)
buttons.rejected.connect(dlg.reject)
layout.addWidget(buttons)

if dlg.exec():
    # User confirmed
```

For simple confirmations, use `QMessageBox` convenience methods:
```python
QMessageBox.warning(self, "Delete Run?", "This cannot be undone.")
QMessageBox.information(self, "Done", "Export complete.")
```

Settings dialogs use `QTabWidget` for multi-section content. Pass the parent window so Qt centers the dialog correctly.

---

## 8. Model/View for Tables

Use `QAbstractTableModel` + `QTableView` instead of `QTableWidget` for any data-driven table. This separates data from presentation and handles large datasets efficiently.

```python
class ResultsModel(QAbstractTableModel):
    def __init__(self, results: list[BenchmarkResult]):
        super().__init__()
        self._results = results
        self._headers = ["Model", "Task", "Verdict", "Score", "Cosine", "Layer"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._results)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            row = self._results[index.row()]
            col = index.column()
            # Return appropriate field based on column
            ...
        if role == Qt.ForegroundRole:
            # Return QColor for verdict coloring
            ...

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
```

**Model update signals:**
- `layoutChanged.emit()` — when rows are added/removed (structural change)
- `dataChanged.emit(topLeft, bottomRight)` — when cell values change (more efficient)

Use `QSortFilterProxyModel` for filtering and sorting without modifying the underlying data.

---

## 9. Custom Widget Painting

For widgets that can't be styled with QSS alone (charts, gauges, custom indicators):

```python
class BarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.MinimumExpanding
        )

    def sizeHint(self):
        return QSize(200, 120)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw using token colors from Python dict
        # painter.fillRect(rect, QColor(tokens["primary"]))
        painter.end()  # ALWAYS call end()

    def update_data(self, data: list):
        self._data = data
        self.update()  # Queue repaint — not repaint()
```

**Key rules:**
- Call `self.update()` (async, batches repaints) not `self.repaint()` (sync, immediate)
- Always call `painter.end()` when done
- Read colors from the token dict, never hardcode hex in paint methods
- Set `setSizePolicy` and override `sizeHint` so layouts allocate space correctly

---

## 10. File Structure for UI Code

```
ui/
  main_window.py              # QMainWindow, top-level setup
  style/
    tokens.py                 # DARK, LIGHT, SHARED dicts
    theme_dark.qss            # QSS template with {token} placeholders
    theme_light.qss           # QSS template with {token} placeholders
    theme_loader.py           # Reads QSS, replaces tokens, applies to QApp
  controllers/
    new_run_controller.py     # Mediates between NewRunWidget and services
    result_controller.py      # Mediates between ResultWidget and DataApi
    log_controller.py         # Mediates between LogWidget and event bus
  widgets/
    panels/
      control_panel.py        # Left panel container
      results_panel.py        # Right panel container
      center_panel.py         # Center panel (progress + log)
    progress_widget.py        # Stage badge + bar + ETA + model/task
    log_widget.py             # Structured log with collapsible entries
    log_entry.py              # QFrame-based log entry card
    provider_card.py          # QFrame: health dot + name + url + buttons
    model_selector.py         # QListWidget with checkboxes + provider filter
    task_file_list.py         # QListWidget with remove buttons + drag-drop
    drop_zone_widget.py       # QLabel with drag-drop overlay styling
    chart_widget.py           # QPainter-based bar/line chart
    badge_label.py            # QLabel styled as badge (pass/fail/stage)
    health_dot.py             # QLabel fixed-size colored dot
```

---

## Quick Reference: Common Mistakes

| Mistake | Why it's wrong | Fix |
|---------|---------------|-----|
| Hardcoded `#14B8A6` in Python | Breaks theme switching | Read from `tokens[theme]["primary"]` |
| `box-shadow` in QSS | Silently ignored by Qt | Remove it; use border or QPainter if needed |
| `widget.repaint()` | Synchronous, can cause flickering | Use `widget.update()` |
| `QRunnable` in `ui/widgets/` | Violates layer architecture | Move to `qt_classes/` |
| Mutating widget from background thread | Crashes or undefined behavior | Emit signal, handle in main thread |
| Missing `painter.end()` | Resource leak, rendering bugs | Always call `painter.end()` |
| Property change without unpolish/polish | QSS doesn't re-evaluate | Call `style().unpolish()` then `polish()` |
| `QApplication.processEvents()` | Re-entrant event handling, breaks state | Use `QThreadPool` + signals |
| `append()` per streaming token | UI freezes with rapid updates | Buffer + `QTimer` at 20 Hz max |
| `transition:` in QSS | Not supported in Qt | Remove; Qt has no CSS transitions |
