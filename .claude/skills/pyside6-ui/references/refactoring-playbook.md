# PySide6 Refactoring Playbook — Legacy Widget → MVP Component

Step-by-step migration plan from a legacy `*Widget` + `*Controller` pair into a properly layered MVP component (`view.py` + `presenter.py` + optional `model.py` + tests).

Apply this when:

- A widget's `__init__` exceeds ~200 lines.
- A widget calls services / repositories / SDKs directly.
- A widget's slot methods contain business logic.
- A controller has > 15 methods or > 500 lines.
- Domain types leak through widget code in ways that prevent reuse.
- Tests for a widget's logic require `qtbot` / `QApplication`.

See also:
- [../SKILL.md §1.5 Component Architecture](../SKILL.md) for the target pattern.
- [component-architecture.md](component-architecture.md) for the template.
- [../../python-developer/refactoring-guide.md](../../python-developer/refactoring-guide.md) for the backend half.

> **Trigger phrases that should activate this playbook:**
> - "refactor `<WidgetName>` to the new architecture"
> - "extract a presenter from `<WidgetName>`"
> - "make `<WidgetName>` testable without `qtbot`"
> - "split `<ControllerName>` into use-cases and a presenter"
> - "the controller is doing too much"

---

## 1. Before You Touch Code

1. **Snapshot current behavior with tests.** If the widget has no test, write a `pytest-qt` smoke test that exercises its key flows. The refactor must not change behavior.
2. **Identify the feature boundary.** What does this widget *let the user do*? List 1–5 user operations. Those become use-cases.
3. **List external dependencies.** Repositories, providers, event bus, helper services. Each becomes a constructor-injected dependency on the new presenter.
4. **Don't rename existing classes mid-refactor.** Add new files (`NewRunPresenter`, `NewRunView`) alongside the legacy `NewRunWidget` and `NewRunWidgetController`. Migrate consumers incrementally.

---

## 2. The 10-Step Migration

Apply these in order. Each step is small, reversible, and ends with a green `./scripts/ai-check.sh`.

### Step 1 — Lock current behavior with a `pytest-qt` smoke test

Add a test that drives the widget end-to-end with `qtbot`. It should:

- Instantiate the widget (with its current controller and DI).
- Trigger a happy-path action via `qtbot.mouseClick` or signal injection.
- Assert the visible result.

This test is your safety net. If a future step breaks it, you know the behavior diverged.

```python
def test_new_run_widget_start_happy_path(qtbot, mocker):
    # Arrange (use real or mocked services per fixture)
    widget = NewRunWidget(controller=fake_controller, ...)
    qtbot.addWidget(widget)

    # Act
    qtbot.mouseClick(widget._start_btn, Qt.LeftButton)

    # Assert
    assert widget._status_label.text() == "Running…"
```

### Step 2 — Pull domain types out of widget code

Search for any computation on domain types inside the widget:

```bash
grep -n "BenchmarkRun\|BenchmarkResult" src/ollama_llm_bench/ui/widgets/new_run_widget.py
```

For each occurrence, ask: "Does this logic belong on the domain dataclass?"

- "Compute pass rate of these results" → method on `BenchmarkRun` or function in `backend/core/`.
- "Format this score for display" → presenter/view code (UI concern).

Move domain logic to `backend/core/`; leave display formatting in the widget for now.

### Step 3 — Extract a `*View` from the widget (rename + slim)

Create the new component folder:

```
ui/widgets/new_run/
    __init__.py
    view.py        # NewRunView(QWidget)
    presenter.py   # placeholder; populated in Step 4
```

Copy `NewRunWidget` → `NewRunView` in `view.py`. Strip from `NewRunView`:

- Service / repository imports
- Controller imports
- Anything not directly building widgets or wiring widget-level signals

What remains in the view:

- Widget construction (`_build_ui`)
- Widget-level signal wiring (translate `clicked` to a domain-shaped `*_requested` signal)
- Setter methods (`apply_state`, `show_error`, `set_loading`) — initially empty stubs

Add a `*ViewProtocol` (in the same file) that lists the public surface the presenter will use.

### Step 4 — Create the `*Presenter`

In `presenter.py`, write the skeleton:

```python
class NewRunPresenter(QObject):
    def __init__(
        self,
        *,
        view: NewRunViewProtocol,
        # ... use-cases / services / event_bus
    ) -> None:
        super().__init__()
        self._view = view
        # ...
        self._wire_view_signals()
        self._subscribe_to_event_bus()

    def _wire_view_signals(self) -> None:
        self._view.start_requested.connect(self._on_start_requested)

    def _subscribe_to_event_bus(self) -> None:
        ...

    @Slot(object)
    def _on_start_requested(self, form: NewRunFormData) -> None:
        # initially: delegate to the legacy controller method
        ...
```

The presenter at this stage may **delegate to the legacy controller**. That is the strangler-fig pattern — both old and new coexist while you migrate.

### Step 5 — Move slot logic from controller to presenter

Pick one slot at a time. Move its body from `NewRunWidgetController.on_start_clicked` into `NewRunPresenter._on_start_requested`. Update the legacy controller's method to forward to the presenter:

```python
class NewRunWidgetController:  # legacy
    def on_start_clicked(self, models: list[str]) -> None:
        # was: full body of logic
        # is now: delegate to the new presenter
        self._presenter.on_start_requested(NewRunFormData(selected_models=models))
```

Run tests. The smoke test from Step 1 should still pass.

### Step 6 — Extract a Use-Case from presenter slots

Inspect the presenter's slot methods. If any of them:

- Calls 2+ repositories / providers in sequence,
- Enforces a domain rule before/between calls,
- Returns a domain object,

…it's a use-case wearing presenter clothing. Extract it.

Create (or extend) `backend/services/<feature>/use_cases.py`:

```python
class StartBenchmarkRunUseCase:
    def __init__(self, *, runs_repo: RunsRepository, task_loader: TaskLoader) -> None:
        ...

    def execute(self, *, models: list[str], dataset_path: Path) -> BenchmarkRun:
        if not models:
            raise NoModelsSelected()
        tasks = self._task_loader.load(dataset_path)
        run = BenchmarkRun.new(models=models, tasks=tasks)
        self._runs_repo.save(run)
        return run
```

Update the presenter to depend on the use-case ABC, not concrete dependencies:

```python
class NewRunPresenter(QObject):
    def __init__(self, *, view, start_run_uc: StartBenchmarkRunUseCase, ...) -> None:
        self._start_run_uc = start_run_uc

    def _on_start_requested(self, form: NewRunFormData) -> None:
        try:
            run = self._start_run_uc.execute(
                models=form.selected_models,
                dataset_path=form.dataset_path,
            )
        except NoModelsSelected:
            self._view.show_error("Select at least one model.")
            return
        self.run_started.emit(run)
```

Run tests. Add a unit test for the use-case (no Qt needed).

### Step 7 — Replace `QListWidget` / `QTableWidget` with item-model adapter

If the view uses `QTableWidget` / `QListWidget` with hand-managed rows, and the data is more than ~20 rows, replace with `QAbstractTableModel`:

1. Create `ui/widgets/new_run/model.py` with `NewRunModelsTableModel` (see [model-view-adapters.md](model-view-adapters.md)).
2. Switch `QTableWidget` → `QTableView` in the view.
3. Presenter holds the model; pushes data via `model.replace_all(...)`.
4. Add a `qtmodeltester` test for the model.

### Step 8 — Move long-running operations to a worker

Find any synchronous slot that runs more than ~50 ms (LLM calls, file scans, HTTP). Move into a `QRunnable` adapter in `ui/qt_classes/`:

1. Create `ui/qt_classes/<operation>_task.py` with a `QRunnable` wrapping the use-case.
2. Presenter creates the task, connects signals, submits to `QThreadPool`.
3. Presenter's slots become non-blocking.

See [backend-ui-boundary.md §"Pattern B"](backend-ui-boundary.md) and [threading-guide.md](threading-guide.md).

### Step 9 — Switch cross-feature signals to `QtEventBus`

Search for `connect` calls between this widget and other features:

```bash
grep -n "connect" src/ollama_llm_bench/ui/widgets/new_run/
```

For each cross-feature wire:

1. If the source emits something other features care about (architectural signal) → route through `QtEventBus`.
2. If the source emits something only its presenter cares about (widget signal) → keep as direct connect inside the component.

Goal: no direct `connect()` between sibling features. All cross-feature traffic flows through `QtEventBus`.

### Step 10 — Decommission the legacy controller

Once the new presenter handles all slots and the legacy controller is just a thin delegator:

1. Update the composition root (`app_context.py`) to no longer create the legacy controller.
2. Wire consumers to use the new presenter directly.
3. Delete the legacy controller file.
4. Delete the legacy widget file (renamed to `view.py`).

Final check: presenter tests do NOT need `qtbot`. View tests DO use `qtbot`. Use-case tests are plain pytest with mocked repositories.

---

## 3. Mapping the Project's Widgets

The project has these widget feature areas today. The playbook applies to each in roughly the order shown. Pick the **smallest** widget first to build confidence in the process.

| Widget | Approximate complexity | Recommended order |
|---|---|---|
| `log_widget.py` / `LogWidgetController` | Small, mostly display | **Start here** — easy win, builds vocabulary |
| `result_widget.py` / `ResultWidgetController` | Medium, table-heavy | Second — exercises item-model adapter pattern |
| `previous_run_widget.py` / `PreviousRunWidgetController` | Medium | Third |
| `new_run_widget.py` / `NewRunWidgetController` | Largest, most logic | **Last** — apply lessons from earlier refactors |

After each widget is migrated, add the corresponding `import-linter` contract (see [../../python-developer/architecture.md §5](../../python-developer/architecture.md)) so the new boundary can't regress.

---

## 4. Worked Example: `LogWidget` → `LogComponent`

A sketch of what the playbook produces, end-to-end, for a small widget.

### Before

```python
# ui/widgets/log_widget.py (legacy)
class LogWidget(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ContextProvider.get_context()    # ❌ service locator
        self._data_api = self._ctx.data_api          # ❌ widget knows persistence
        self._event_bus = self._ctx.event_bus
        self._build_ui()
        self._event_bus.subscribe_to_log_message(self._append_log)  # ❌ widget on event bus

    def _on_filter_text_changed(self, text: str) -> None:
        # ❌ business rule in widget
        filtered = [e for e in self._all_entries if text in e.message]
        self._render(filtered)
```

### After

```
ui/widgets/log/
    __init__.py
    view.py        # LogView(QWidget) — only renders, only emits signals
    presenter.py   # LogPresenter(QObject) — owns filter logic, event-bus subscription
    state.py       # LogViewState
    tests/
        test_presenter.py
        test_view.py
```

```python
# ui/widgets/log/view.py
class LogView(QFrame):
    filter_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._filter_input.textChanged.connect(self.filter_changed)

    def apply_state(self, state: LogViewState) -> None:
        self._render_entries(state.visible_entries)


# ui/widgets/log/presenter.py
class LogPresenter(QObject):
    def __init__(self, *, view: LogViewProtocol, event_bus: EventBus) -> None:
        super().__init__()
        self._view = view
        self._event_bus = event_bus
        self._all_entries: list[LogEntry] = []
        self._filter_text: str = ""
        event_bus.subscribe_to_log_message(self._on_new_message)
        view.filter_changed.connect(self._on_filter_changed)

    def _on_new_message(self, entry: LogEntry) -> None:
        self._all_entries.append(entry)
        self._refresh()

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text.lower()
        self._refresh()

    def _refresh(self) -> None:
        visible = [e for e in self._all_entries if self._filter_text in e.message.lower()]
        self._view.apply_state(LogViewState(visible_entries=visible))
```

The presenter is testable without `QApplication`. The view is testable with `qtbot`.

---

## 5. Smells to Notice While Refactoring

When opening a widget to refactor, scan for these and address each at the appropriate step:

| Smell | Located in | Fix in step |
|---|---|---|
| `ContextProvider.get_context()` in `__init__` | Widget | Step 3 (extract view; constructor-inject) |
| `from ollama_llm_bench.backend.services import X` | Widget | Step 3 (presenter owns service deps) |
| `import sqlite3` or DB SQL strings in widget | Widget | Step 3 (move to repository) |
| Slot method > 30 lines | Widget or controller | Step 6 (extract use-case) |
| `QListWidget` / `QTableWidget` with > 20 rows | Widget | Step 7 (item-model adapter) |
| `time.sleep` or blocking I/O in slot | Widget or controller | Step 8 (move to worker) |
| `connect()` between widget and sibling widget | Widget or controller | Step 9 (route through `QtEventBus`) |
| Signal handler mutates global state | Anywhere | Move state into the presenter |
| Widget knows about another widget's children (`other_widget.button.setEnabled(...)`) | Widget | Mediator pattern via parent presenter |

---

## 6. Verifying the Refactor Is Complete

When all 10 steps are done for a component, verify:

- [ ] **No widget imports a service, repository, or backend SDK directly.**
- [ ] **No widget calls `ContextProvider.get_context()`.**
- [ ] **No widget subscribes to `QtEventBus` directly** (the presenter does).
- [ ] **Presenter has zero imports from `PySide6.QtWidgets`.**
- [ ] **At least one test for the presenter does NOT need `qtbot`.**
- [ ] **At least one test for the view DOES use `qtbot`.**
- [ ] **At least one test for each new use-case is plain pytest.**
- [ ] **No `# type: ignore` was added during the refactor.**
- [ ] **`./scripts/ai-check.sh` passes clean.**
- [ ] **The smoke test from Step 1 still passes.**

If every box is checked, the component has graduated.

---

## 7. After the Refactor

- **Update the composition root.** Inject the new presenter and view into `app_context.py`; remove the legacy controller wiring.
- **Add an `import-linter` contract** to lock the layering for this feature (e.g., `ui.widgets.log` may not import `backend.services`).
- **Delete dead code.** Legacy widget file (after rename), legacy controller, dead imports.
- **Document any new ABCs** added during the refactor.
- **Move on to the next widget** in the order from §3. Each refactor is faster than the last — the team's vocabulary and infrastructure are now in place.
