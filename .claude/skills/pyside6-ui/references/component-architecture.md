# PySide6 Component Architecture — MVP Passive View

Concrete template for a feature component: a `QWidget`, a `QObject` presenter, an optional `QAbstractTableModel` adapter, and tests. Use this when introducing a new feature component or refactoring a legacy `*Widget` + `*Controller` pair.

See also:
- [../SKILL.md §1.5 "Component Architecture"](../SKILL.md) for the rules.
- [backend-ui-boundary.md](backend-ui-boundary.md) for how the component talks to the backend.
- [refactoring-playbook.md](refactoring-playbook.md) for the legacy → MVP migration plan.

---

## 1. Why MVP (Passive View) for QWidgets

QWidgets do not have built-in two-way data binding. Forcing MVVM via `Q_PROPERTY` and signals works mechanically but is verbose and fragile in Python. **MVP Passive View** is a clean fit:

- **View** is "passive" — it has setters and signals; it has no logic.
- **Presenter** pulls data from the backend, pushes it into the view via the setters, and consumes the view's signals.

Result: presenter is testable as a `QObject` (no widgets needed); view is testable with `pytest-qt`'s `qtbot`; the underlying use-case is testable as plain Python.

(For QML use MVVM — but this project uses QWidgets only.)

---

## 2. Component folder template

```
ui/widgets/<feature_name>/
    __init__.py
    view.py
    presenter.py
    model.py             # optional, when the component shows tables/lists
    state.py             # optional, frozen dataclass for view state
    _ui_helpers.py       # optional, private widget construction helpers
    tests/
        __init__.py
        test_presenter.py
        test_view.py
```

### `__init__.py` — public API

```python
from ollama_llm_bench.ui.widgets.new_run.presenter import NewRunPresenter
from ollama_llm_bench.ui.widgets.new_run.view import NewRunView

__all__ = ["NewRunPresenter", "NewRunView"]
```

Anything not in `__all__` is internal to the component. Sibling features may import only these names.

---

## 3. View — `QWidget` (passive)

The view exposes:

- **Signals** for user-intent events (`save_requested`, `model_selected`, `start_clicked`).
- **Setter methods** the presenter calls to push display state (`set_models`, `show_error`, `set_loading`).
- **No business logic.** No domain validation. No service calls.

```python
# ui/widgets/new_run/view.py
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
)

from ollama_llm_bench.ui.widgets.new_run.state import NewRunViewState


class NewRunView(QWidget):
    """Passive view for the New Run panel.

    The view emits intent signals upward and exposes setters for the
    presenter to push state. It contains no business logic.
    """

    # User-intent signals (architectural meaning, not button-level)
    start_requested = Signal(object)   # emits NewRunFormData
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._wire_widget_signals()

    # ---- Setters the presenter calls --------------------------------

    def apply_state(self, state: NewRunViewState) -> None:
        """Apply the full view state in one call."""
        self._model_list.set_items(state.available_models)
        self._start_btn.setEnabled(state.can_start)
        self._status_label.setText(state.status_text)

    def set_loading(self, *, is_loading: bool) -> None:
        self._start_btn.setEnabled(not is_loading)
        # ...

    def show_error(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setProperty("role", "error")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    # ---- Private --------------------------------------------------

    def _build_ui(self) -> None:
        # Construct widgets; layout them; no signal-to-domain wiring here.
        layout = QVBoxLayout(self)
        self._model_list = ModelSelector()
        self._start_btn = QPushButton("Start")
        self._status_label = QLabel("")
        layout.addWidget(self._model_list)
        layout.addWidget(self._start_btn)
        layout.addWidget(self._status_label)

    def _wire_widget_signals(self) -> None:
        # Translate widget-level signals into architectural signals
        self._start_btn.clicked.connect(self._on_start_clicked)

    def _on_start_clicked(self) -> None:
        form = self._collect_form_state()
        self.start_requested.emit(form)

    def _collect_form_state(self) -> NewRunFormData:
        return NewRunFormData(
            selected_models=self._model_list.get_selected(),
        )
```

### View Protocol — for presenter testing

If the presenter needs the view's surface to be testable, declare a `Protocol` matching the view's public API. The presenter depends on the Protocol, not the concrete view:

```python
# ui/widgets/new_run/view.py (or a separate _view_protocol.py)
class NewRunViewProtocol(Protocol):
    """Surface the presenter sees. The QWidget view satisfies this implicitly."""
    start_requested: Signal
    cancel_requested: Signal
    def apply_state(self, state: NewRunViewState) -> None: ...
    def set_loading(self, *, is_loading: bool) -> None: ...
    def show_error(self, message: str) -> None: ...
```

In tests, a `Mock(spec=NewRunViewProtocol)` substitutes for the view — no `QApplication` needed for presenter tests.

### What the view must NOT do

- ❌ Import a service, repository, or backend SDK
- ❌ Import `QtEventBus`
- ❌ Run business validation (form-level "is this email valid" stays in the view; "is this customer allowed to buy this" lives in the use-case)
- ❌ Call `ContextProvider.get_context()`
- ❌ Subscribe directly to backend events

---

## 4. Presenter — `QObject` (no widgets)

The presenter:

- Holds the view via the View Protocol (so it can be tested without widgets).
- Subscribes to `QtEventBus` for cross-feature events.
- Calls use-cases (constructor-injected ABCs).
- Pushes state to the view via setters.

```python
# ui/widgets/new_run/presenter.py
from __future__ import annotations

import logging
from typing import override

from PySide6.QtCore import QObject, Signal, Slot

from ollama_llm_bench.backend.core.interfaces import (
    EventBus, StartBenchmarkRunUseCase, ListProvidersUseCase,
)
from ollama_llm_bench.ui.widgets.new_run.state import NewRunViewState
from ollama_llm_bench.ui.widgets.new_run.view import NewRunViewProtocol

logger = logging.getLogger(__name__)


class NewRunPresenter(QObject):
    """Presenter for the New Run feature. Owns no widget code."""

    # Architectural signals the presenter exposes upward
    run_started = Signal(object)  # BenchmarkRun
    error = Signal(str)

    def __init__(
        self,
        *,
        view: NewRunViewProtocol,
        start_run_uc: StartBenchmarkRunUseCase,
        list_providers_uc: ListProvidersUseCase,
        event_bus: EventBus,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._start_run_uc = start_run_uc
        self._list_providers_uc = list_providers_uc
        self._event_bus = event_bus

        self._state = NewRunViewState.initial()
        self._wire_view_signals()
        self._subscribe_to_event_bus()
        self._refresh_models()

    # ---- Wiring -----------------------------------------------------

    def _wire_view_signals(self) -> None:
        self._view.start_requested.connect(self._on_start_requested)
        self._view.cancel_requested.connect(self._on_cancel_requested)

    def _subscribe_to_event_bus(self) -> None:
        self._event_bus.subscribe_to_models_changed(self._on_models_changed)

    # ---- Slots -----------------------------------------------------

    @Slot(object)
    def _on_start_requested(self, form: NewRunFormData) -> None:
        if not form.selected_models:
            self._view.show_error("Select at least one model.")
            return
        try:
            run = self._start_run_uc.execute(
                models=form.selected_models,
                dataset_path=self._state.dataset_path,
            )
        except Exception as e:
            logger.error("Failed to start run: %s", e, exc_info=True)
            self._view.show_error(str(e))
            self.error.emit(str(e))
            return
        self.run_started.emit(run)

    @Slot()
    def _on_cancel_requested(self) -> None:
        # ...
        pass

    def _on_models_changed(self, models: list[str]) -> None:
        self._state = self._state.with_models(models)
        self._view.apply_state(self._state)

    # ---- Private --------------------------------------------------

    def _refresh_models(self) -> None:
        models = self._list_providers_uc.execute()
        self._state = self._state.with_models(models)
        self._view.apply_state(self._state)
```

### What the presenter must NOT do

- ❌ Import any `QWidget`, `QPushButton`, `QLabel`, etc.
- ❌ Call `self._view.findChild(...)` or any widget-tree introspection
- ❌ Talk to a Repository directly (always through a use-case)
- ❌ Hold references to other presenters except via mediator pattern (parent presenter)
- ❌ Mutate widget state from non-main threads (presenters live on the main thread; if you need background work, route it through the UI adapter)

---

## 5. Optional: view state dataclass

For non-trivial views, gather the state into a frozen dataclass. The presenter computes a new state, passes it to `view.apply_state(...)`, the view applies it.

```python
# ui/widgets/new_run/state.py
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class NewRunViewState:
    available_models: tuple[str, ...]
    selected_model_ids: tuple[str, ...]
    can_start: bool
    status_text: str
    dataset_path: Path

    @classmethod
    def initial(cls) -> NewRunViewState:
        return cls(
            available_models=(),
            selected_model_ids=(),
            can_start=False,
            status_text="Loading…",
            dataset_path=Path(),
        )

    def with_models(self, models: list[str]) -> NewRunViewState:
        return replace(self, available_models=tuple(models))
```

Benefits:
- The view's apply method is one call; no risk of partial updates.
- Easy to snapshot in tests: `assert presenter._state == expected_state`.
- Forces explicit thinking about derived state (`can_start` is computed; the view doesn't compute it).

---

## 6. Optional: item-model adapter

If the component displays a table/list, the model adapter goes in the same folder. See [model-view-adapters.md](model-view-adapters.md) for full rules.

```python
# ui/widgets/result/model.py
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ollama_llm_bench.backend.core.models import BenchmarkResult


class ResultsTableModel(QAbstractTableModel):
    HEADERS = ("Model", "Task", "Verdict", "Score")

    def __init__(self, results: list[BenchmarkResult] | None = None) -> None:
        super().__init__()
        self._results: list[BenchmarkResult] = list(results or [])

    # ... rowCount, columnCount, data, headerData, replace_all
```

The presenter owns the model instance and calls `replace_all` when the use-case returns new results.

---

## 7. Wiring in the composition root

```python
# app_context.py — composition root
def _create_app_context(...) -> ApplicationContext:
    # backend
    runs_repo = SqliteRunsRepository(db_path=...)
    list_providers_uc = ListProvidersUseCase(provider_registry=...)
    start_run_uc = StartBenchmarkRunUseCase(runs_repo=runs_repo, ...)
    event_bus = QtEventBus()

    # component
    new_run_view = NewRunView()
    new_run_presenter = NewRunPresenter(
        view=new_run_view,
        start_run_uc=start_run_uc,
        list_providers_uc=list_providers_uc,
        event_bus=event_bus,
    )

    # ... pass new_run_view to MainWindow's central layout
    return ApplicationContext(
        new_run_view=new_run_view,
        new_run_presenter=new_run_presenter,
        event_bus=event_bus,
        ...
    )
```

The presenter is created **after** the view (so it can be passed the view reference) but **before** the window shows. The presenter and view share lifetime.

---

## 8. Tests

See [testing-pyside.md](testing-pyside.md) for the full setup. The short version:

```python
# tests/unit/widgets/new_run/test_presenter.py
def test_start_requested_with_no_models_shows_error(mocker: MockerFixture) -> None:
    # Arrange
    view = mocker.Mock(spec=NewRunViewProtocol)
    start_uc = mocker.Mock(spec=StartBenchmarkRunUseCase)
    event_bus = mocker.Mock(spec=EventBus)
    presenter = NewRunPresenter(
        view=view,
        start_run_uc=start_uc,
        list_providers_uc=mocker.Mock(),
        event_bus=event_bus,
    )

    # Act
    presenter._on_start_requested(NewRunFormData(selected_models=[]))

    # Assert
    view.show_error.assert_called_once_with("Select at least one model.")
    start_uc.execute.assert_not_called()
```

No `QApplication` needed because the view is a Mock. This is the payoff of MVP.

For testing the actual `QWidget` view, use `pytest-qt`'s `qtbot`. See [testing-pyside.md](testing-pyside.md).

---

## 9. Anti-patterns specific to components

| Pattern | Why it's wrong | Fix |
|---|---|---|
| Presenter holds `QWidget` directly typed | Presenter can't be tested without widgets | Hold a `View Protocol` |
| View calls `self._presenter.do_thing()` | View knows about Presenter; tight coupling | View emits signal; presenter connects to it |
| Two components communicate via `event_bus` for in-component events | Bus polluted with leaf events | Use the parent presenter as mediator |
| Component folder has a `utils.py` | Generic dumping ground | Name file by purpose: `_ui_helpers.py`, `_form_validation.py` |
| `presenter.py` imports anything from `PySide6.QtWidgets` | Layer leak | Move widget concerns to `view.py` |
| View runs business validation (e.g., "an order must have ≥ 1 line item") | Logic in view layer | Move to use-case; view does only form validation ("the email field looks like an email") |
| Presenter creates widgets in `__init__` | Inverted ownership | View creates widgets; presenter is given the view |
| Tests of presenter require `qtbot` | View is being instantiated for real | Replace view with `Mock(spec=ViewProtocol)` |
