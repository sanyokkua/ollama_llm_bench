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

| When you need…                                        | Read                                              |
|-------------------------------------------------------|---------------------------------------------------|
| Component architecture (View + Presenter + Model)     | `references/component-architecture.md`            |
| Backend ↔ UI boundary, adapters, swappable layers     | `references/backend-ui-boundary.md`               |
| Qt item-models, sort/filter, fetch-more, perf         | `references/model-view-adapters.md`               |
| Refactor a legacy widget into an MVP component        | `references/refactoring-playbook.md`              |
| Testing with `pytest-qt`, `qtbot`, `qtmodeltester`    | `references/testing-pyside.md`                    |
| Complete QSS template with all selectors + tokens     | `references/qss-theme-template.md`                |
| Design tokens (full DARK/LIGHT/SHARED dicts)          | `references/design-tokens.md`                     |
| Widget construction patterns with code                | `references/widget-patterns.md`                   |
| PySide6 threading: QRunnable, moveToThread, qasync    | `references/threading-guide.md`                   |

Read the relevant reference file before writing code in that area. The references contain exact code, exact selectors, and exact token values — don't guess.

> **Companion skill:** [python-developer](../python-developer/SKILL.md) covers backend (Domain / Application / Infrastructure), use-cases, repositories, and project-wide Python rules. They share architectural vocabulary; this skill assumes that vocabulary.

---

## 1. Architecture Layer Rules

PySide6 projects following this pattern use a strict layered architecture with a **Clean Architecture** role mapping. Violating these boundaries creates coupling bugs that are painful to fix later. The full architectural contract lives in [../python-developer/architecture.md](../python-developer/architecture.md); the version below is the UI-facing subset.

**Layer dependency direction** (arrows = "is allowed to import"):

```
ui/widgets/  →  ui/controllers/  →  qt_classes/  →  services/  →  core/
   (View)      (Controller / Presenter)  (UI Adapter)  (App+Infra)  (Domain)
                                                                      ↑
                                                                    utils/
```

**Clean Architecture role mapping:**

| Folder | Role | What it owns | What it MUST NOT contain |
|---|---|---|---|
| `backend/core/` | **Domain** | Frozen dataclasses, enums, ABCs / Protocols, invariants | Qt imports, I/O, SDK calls |
| `backend/services/` | **Application + Infrastructure** | Use-cases, repositories, provider clients | `PySide6.QtWidgets`. (`PySide6.QtCore` only where existing ABCs require it.) |
| `backend/utils/` | **Cross-cutting helpers** | Pure, generic, ≥ 3-consumer functions | State, I/O, Qt, domain types |
| `ui/qt_classes/` | **UI Adapter** (the boundary) | `QRunnable`, `QThreadPool`, `QtEventBus`, `MetaQObjectABC` | Business logic, widget code |
| `ui/controllers/` | **Presentation** | Controllers / Presenters mediating user input ↔ use-cases | Widget rendering, persistence, SDK calls |
| `ui/widgets/` | **View** | `QWidget` subclasses, layouts, paint code | Business logic, service instantiation, repository / SDK calls |

**Hard constraints:**

- **`core/`** — Pure Python. No `PySide6`, no `ollama`, no `yaml`. Only dataclasses, enums, ABCs, SQL strings, prompt templates, constants. This layer defines what the app *is* without saying how it renders or communicates.
- **`services/`** — No `PySide6.QtWidgets`. Concrete implementations (API clients, data access, task loading) live here. Must be unit-testable without a `QApplication` running.
- **`qt_classes/`** — The *only* place that creates `QRunnable` or `QThreadPool`. All threaded work lives here. This is the **adapter** between backend and Qt.
- **`ui/controllers/`** — Mediate between widgets and services. Widgets never instantiate a service or touch SQLite directly.
- **`ui/widgets/`** — Rendering only. Talk to backend through controllers / presenters. Update only via signal/slot from `QtEventBus`.
- **All background-to-UI communication flows through signals** (`QtEventBus`). No `QMetaObject.invokeMethod`, no direct widget mutation from worker threads.
- **All dependencies injected via constructor** (keyword-only args). No internal instantiation of collaborators. No `ContextProvider.get_context()` from inside widgets.
- **Absolute imports only**: `from ollama_llm_bench.backend.core.models import BenchmarkRun`

### Backend ↔ UI Boundary (summary)

The UI must talk to the backend **only through ABCs / Protocols declared in `backend/core/interfaces.py`** — never through concrete classes from `backend/services/`. The composition root (`app_context.py`) is the one place that wires concretes to abstracts.

**Why this matters:** if either side needs to be replaced (different UI toolkit, different LLM SDK, different DB), only the layer being swapped changes. See [references/backend-ui-boundary.md](references/backend-ui-boundary.md) for the full contract, the adapter pattern, and the `psygnal` migration plan.

---

## 1.5. Component Architecture (MVP for QWidgets)

PySide6's "Model/View" is **not** application MVC — it's a widget-level pattern for `QTableView`/`QTreeView`/`QListView`. For the rest of the app, the correct pattern is **MVP (Passive View)**:

- **View** — `QWidget` subclass. Renders state, emits user-intent signals. No business logic. No service calls. No domain knowledge beyond the dataclass types it displays.
- **Presenter** — `QObject` subclass. Owns interaction logic, holds the view as a "Passive View Protocol," subscribes to backend events via `QtEventBus`, calls use-cases. **No widget imports.**
- **Model adapter** (when displaying lists/tables) — `QAbstractTableModel` / `QAbstractListModel` subclass that wraps domain objects for a Qt view. **Not the domain model itself.**

```
┌──────────────────────────────────────────────────────────────┐
│            Component (one feature, one screen)                │
│                                                              │
│   ┌──────────────┐  user input  ┌──────────────┐             │
│   │   View       │  ──────────► │  Presenter   │             │
│   │   (QWidget)  │              │  (QObject)   │             │
│   │              │ ◄────────────│              │             │
│   └──────────────┘  state update└──────┬───────┘             │
│         ▲ uses                         │ calls               │
│         │                              ▼                     │
│   ┌──────────────┐              ┌──────────────┐             │
│   │  Item Model  │ ◄────────────│  Use-Case    │             │
│   │  (adapter)   │   results    │  (backend)   │             │
│   └──────────────┘              └──────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

### Naming policy (Controller vs Presenter)

- **Existing code:** keep the name `*Controller` (NewRunWidgetController, ResultWidgetController, etc.). Don't rename mid-refactor.
- **New components and refactored components:** use the name `*Presenter` (`NewRunPresenter`, `ResultPresenter`). Different name → different responsibility (Passive View Protocol, no widget imports).
- Both live in `ui/controllers/` for now. Once enough components have migrated, consider moving each component's presenter into the component folder (`ui/widgets/new_run/presenter.py`).

### Component folder template

A refactored feature component groups its parts together:

```
ui/widgets/new_run/
    __init__.py              # exports NewRunComponent factory
    view.py                  # NewRunView(QWidget) — passive view
    presenter.py             # NewRunPresenter(QObject) — no widget imports
    model.py                 # optional: NewRunModelsTableModel (QAbstractTableModel)
    state.py                 # optional: @dataclass(frozen=True) NewRunViewState
    _ui_helpers.py           # widget construction helpers, component-private
    tests/
        test_presenter.py    # plain pytest, no qtbot needed
        test_view.py         # pytest-qt with qtbot
```

The `__init__.py` exports only the public surface — typically a factory function or a `Component` class that the composition root instantiates.

See [references/component-architecture.md](references/component-architecture.md) for full templates, the View Protocol pattern, and a worked example.

### Controller / Presenter granularity rule

**One Controller / Presenter exists per:**

- Top-level window or main pane (MainWindow).
- Modal dialog with non-trivial logic (beyond OK/Cancel).
- Wizard / multi-step form.
- Composite "feature widget" (NewRunWidget, ResultWidget, LogWidget).
- Deeply reusable composite widget if and only if it has logic the parent shouldn't know about.

**No Controller / Presenter exists for:**

- Buttons, labels, line edits, simple form fields — they are leaf views; the parent presenter handles their events.
- Layout containers, splitters, tab widgets, dock widgets — these are pure layout.
- One-off widgets used in a single place — they're part of their parent's view.

The "one controller per QPushButton" idea (popular in tutorials) is **wrong** — it produces ceremony without benefit. Stay at the feature granularity.

### Anti-patterns

| Anti-pattern | Symptom | Fix |
|---|---|---|
| **God widget / fat MainWindow** | `__init__` 500+ lines; widget holds DB sessions, business logic | Extract presenter; widget calls `presenter.on_save()` in one line |
| **God controller** | One `MainController` orchestrates everything | Split per feature; use event bus / parent presenter to coordinate |
| **Presenter imports `QWidget`** | Presenter calls `self._save_btn.setEnabled(False)` | Presenter knows view only as a Protocol with `set_save_enabled(bool)` |
| **Widget calls a Repository** | `MyWidget.__init__: self._db = SqLiteDataApi(...)` | Inject controller/presenter; route through it |
| **Tightly coupled dialog** | `EditDialog(main_window)` reaches into parent for state | Pass only the data the dialog needs; emit result via signal or `exec()` |
| **Sibling widgets connecting directly** | Two child widgets call `connect()` on each other | Wire through the parent (mediator pattern, §1.7) |
| **`QStandardItemModel` everywhere** | Data lives in the item model, business logic in `setData` | Subclass `QAbstractTableModel`; store domain objects; mutate via presenter |
| **Service locator inside widget** | `ContextProvider.get_context()` in widget's `__init__` | Constructor-inject the controller/presenter |
| **Business logic in `clicked` slot** | Domain rules live inside button handlers | Slot is one line — `self._presenter.on_save_clicked()` |
| **Signal spaghetti** | Dozens of cross-feature `connect()` calls scattered | Restrict cross-feature signals to `QtEventBus`; keep widget-internal signals local |

---

## 1.6. Signals: Architectural vs Widget

Qt signals are an observer-pattern primitive — **not** an architectural pattern by themselves. A clean app distinguishes two kinds.

### Widget signals (private to view ↔ presenter pair)

Low-level "the user did X" events from `QPushButton`, `QLineEdit`, etc. **Stay inside the component.** The presenter consumes them and translates to domain operations.

```python
# view.py
self._save_btn.clicked.connect(self._on_save_clicked)
def _on_save_clicked(self) -> None:
    self.save_requested.emit(self._collect_form_state())  # emit domain-shaped signal
```

### Architectural signals (cross feature boundaries)

Domain-meaningful events: `run_started`, `task_completed`, `model_list_changed`. Live on `QtEventBus`. Other presenters subscribe.

```python
# presenter.py
class ResultPresenter(QObject):
    def __init__(self, *, event_bus: EventBus, ...) -> None:
        super().__init__()
        event_bus.subscribe_to_run_completed(self._on_run_completed)

    def _on_run_completed(self, run_id: int) -> None:
        # update view via Passive View Protocol
        self._view.show_results_for(run_id)
```

### Rules

1. **Cross-feature `connect()` calls MUST go through `QtEventBus`** — never sibling-to-sibling.
2. **Widget-level signals stay local** to the view-presenter pair.
3. **Presenters expose domain-shaped signals** on themselves (`saved(BenchmarkRun)`, `error(str)`) — the view subscribes to those.
4. **Backend code MUST NOT emit Qt signals.** It returns values, raises domain exceptions, or (when adopted) emits `psygnal.Signal`. The UI adapter (`ui/qt_classes/`) is the only place that translates backend events into Qt signals.
5. **Use `@Slot(...)` decorators** on slot methods. Required for cross-thread queued connections; type-safe everywhere.
6. **Avoid lambdas in `connect()`** for production code. Use named methods so disconnection works and stack traces are readable.

---

## 1.7. Mediator Pattern for Composite Components

When a parent component contains multiple children that need to talk to each other, **the parent routes their communication**. Children never `connect()` to each other directly.

```python
class WorkbenchPresenter(QObject):
    def __init__(self, *, services: Services, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._explorer = ExplorerPresenter(fs=services.fs)
        self._editor   = EditorPresenter(docs=services.docs)
        self._console  = ConsolePresenter(runtime=services.runtime)
        # mediator wiring — children don't know about each other
        self._explorer.file_chosen.connect(self._editor.open_path)
        self._editor.run_requested.connect(self._console.execute)
```

**Why:** the children are decoupled; replacing one feature means editing only the parent's wiring; testing one child doesn't require the others.

**When NOT to use the mediator:** if a component is published-event-shaped (multiple unknown subscribers), use `QtEventBus`. Mediator is for 1:1 or 1:few coupling between siblings of the same parent.

---

## 1.8. State Management

Different state has different homes — putting it in the wrong place causes drift bugs.

| State category | Lives in | Example |
|---|---|---|
| **Local UI state** (form dirty? row selected?) | Presenter as plain Python attrs | `self._is_dirty = True` |
| **View display state** (label texts, button enabled flags) | Computed by presenter, applied to view via setters | `view.set_save_enabled(is_dirty)` |
| **Application state** (current run, selected provider, theme) | A central store published on `QtEventBus`; presenters subscribe | `event_bus.subscribe_to_run_id_changed(...)` |
| **Persistent / domain state** (runs in DB, settings on disk) | Backend repository | `runs_repo.save(run)` |

**Rules:**

- **Single source of truth** per piece of state. Views must not store data that diverges from the source — they show it, the source owns it.
- **Mutations on the main thread only.** Background workers compute results, emit them via queued signals; the main-thread slot mutates state.
- **Programmatic widget updates must use `QSignalBlocker`** when they could trigger circular slot chains. `editingFinished` → setText → editingFinished is the classic loop.

### Four classic state bugs

| Bug | Cause | Fix |
|---|---|---|
| Stale UI | View stores its own copy that diverges from source | Single source of truth; view only displays what the presenter pushes |
| Circular updates | Slot A → emits → slot B → emits → slot A | `QSignalBlocker` around programmatic updates |
| Concurrent updates | Background thread mutates state the UI reads | All mutation on main thread; workers emit results, main thread applies |
| Lost updates | Multiple writers, no synchronization | Single owner per piece of state; presenters are the only writers |

---

## 1.9. When to Step Up

Triggers that mean the current granularity is no longer enough:

| Symptom | What to introduce |
|---|---|
| Two developers can't merge without conflicting on the same widget class | Per-feature presenter (split god widget) |
| Adding a menu item requires editing 4 files | Command registry (out of scope today — note for future) |
| Cross-feature `connect()` count > ~5 | Move all of them to `QtEventBus` |
| Presenter test setup needs `QApplication` | Push logic into a Qt-free use-case |
| Same operation triggered from button, menu, and shortcut, duplicated 3 times | Extract the operation as a use-case; route all three triggers to it |

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

> **The cardinal rule:** `QAbstractItemModel` (and its subclasses) is **NOT your domain model** — it is an **adapter** between your domain objects and a Qt view. Domain validation goes in the domain layer; the item model just feeds rows × columns × roles to the view.
>
> Coupling them — e.g., putting business rules inside `setData()` — is the most common PySide architectural error. See [references/model-view-adapters.md](references/model-view-adapters.md) for the full pattern, `QSortFilterProxyModel`, `canFetchMore`/`fetchMore`, and performance rules for large datasets.

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

**Model update signals — pair these correctly:**
- `beginInsertRows(parent, first, last)` / `endInsertRows()` — when adding rows
- `beginRemoveRows(parent, first, last)` / `endRemoveRows()` — when removing rows
- `beginResetModel()` / `endResetModel()` — for bulk replacement
- `dataChanged.emit(topLeft, bottomRight, roles=[...])` — when existing cells change

MUST pair `beginX` with `endX`. Skipping `beginInsertRows` corrupts the view; views will desync and may crash. Verify with `QAbstractItemModelTester` (exposed via `pytest-qt`'s `qtmodeltester`) in tests — see [references/testing-pyside.md](references/testing-pyside.md).

**Use `QSortFilterProxyModel` for filtering and sorting** — never modify the source model's underlying data to sort/filter. Subclass and override `filterAcceptsRow` / `lessThan` for non-trivial behavior. The same source model can power multiple filtered/sorted views without duplicating data. See [references/model-view-adapters.md](references/model-view-adapters.md).

**For large datasets (> ~10K rows):**
- Cache `data()` results (Qt calls it very often during repaint and selection).
- Cap work in `flags()` — return a precomputed flag constant rather than reconstructing.
- Implement `canFetchMore` / `fetchMore` for paging from the repository instead of loading all rows.
- Do server-side fetches on a worker thread; mutate the model only on the main thread.

**Threading rule (non-negotiable):** the item model is a `QObject` — only the main thread may touch it. Workers produce plain Python data and emit via a queued signal; the main-thread slot updates the model.

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

The project currently uses flat `ui/widgets/` + `ui/controllers/`. The **target** layout for new and refactored components is **feature-folder under `ui/widgets/`** with each component owning its own view, presenter, optional model adapter, and tests.

### Current (legacy) layout — keep until refactored

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
    progress_widget.py
    log_widget.py
    log_entry.py
    provider_card.py
    model_selector.py
    task_file_list.py
    drop_zone_widget.py
    chart_widget.py
    badge_label.py            # leaf reusable widget (stays flat)
    health_dot.py             # leaf reusable widget (stays flat)
```

### Target layout — feature folders for non-leaf components

```
ui/
  main_window.py
  style/
    tokens.py
    theme_dark.qss
    theme_light.qss
    theme_loader.py
  qt_classes/
    qt_event_bus.py
    benchmark_execution_task.py
    backend_event_bridge.py    # psygnal → QtEventBus (when adopted)
  widgets/
    common/                    # leaf reusable widgets (no presenter)
      badge_label.py
      health_dot.py
      drop_zone_widget.py
      chart_widget.py
    new_run/                   # feature component
      __init__.py
      view.py                  # NewRunView(QWidget)
      presenter.py             # NewRunPresenter(QObject) — new code uses "Presenter"
      model.py                 # optional: model adapters
      state.py                 # optional: frozen view state dataclass
      _ui_helpers.py
      tests/
        test_presenter.py
        test_view.py
    result/                    # feature component
      view.py
      presenter.py
      ...
    log/                       # feature component
      view.py
      presenter.py
      ...
```

**Rules:**

- **Leaf widgets** (no presenter, no state, no business logic) live in `ui/widgets/common/`. They expose signals and setters; they have no awareness of any presenter or domain model.
- **Feature components** (with their own logic and state) live in their own folder under `ui/widgets/<feature>/`.
- **Component folder is a unit of locality** — when changing a feature, you touch one folder. `tests/` co-located so test code travels with implementation.
- **Internal helpers** use a leading underscore in the filename (`_ui_helpers.py`); they are NOT imported from outside the component folder.

See [references/component-architecture.md](references/component-architecture.md) for the full template and worked example.

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
