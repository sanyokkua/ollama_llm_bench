---
paths:
  - "src/ollama_llm_bench/ui/**/*.py"
  - "src/ollama_llm_bench/adapters/**/*.py"
---

# PySide6 Application Development

Source of truth: `docs/v3_specification/08_Cross_Cutting/08-D_color_palette_and_typography.md`
§16, `docs/v3_specification/08_Cross_Cutting/08-L_ui_standardization.md`, and the adapters
section of `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md`. Also see
`project-structure.md` for the layered import rules and `concurrency-standard.md` for the
threading model that governs every adapter in this tree.

## The theme module is the single styling authority

`src/ollama_llm_bench/ui/theme/` is the **only** place permitted to call `setStyleSheet()` or
assemble a stylesheet from raw design tokens — enforced by the architecture-test stack
(import-linter + a `pytest-archon` rule). It:

- holds two frozen token containers (Dark, Light) as typed Python objects
  (`msgspec.Struct(frozen=True, kw_only=True)` or equivalent), not `.qss` files on disk;
- builds the Qt stylesheet string and `QPalette` from the active container and applies them to
  the `QApplication` — this is the only code permitted to call `setStyleSheet()`;
- targets **dynamic-property roles**: per-widget appearance variants (primary button,
  destructive button, icon button, badge variants, context strip) are expressed as Qt dynamic
  properties on widgets; the application stylesheet selects on those properties. **Widget code
  sets the property; it never sets style.**
- implements theme switching (System/Dark/Light) and emits a theme-changed notification so
  custom-painted surfaces (charts, status dots, badges) re-read their colours and repaint.

A widget references a colour or font by **role name** (e.g. `"surface layer 2"`, `"primary"`,
`"error"`), never a literal. The theme module resolves the role for the active theme. The
architecture-test suite fails the build if any module outside `ui/theme/` references
`setStyleSheet`, embeds a colour literal in a widget, or imports a token container for direct
stylesheet assembly.

## The MVC-family per-widget module layout

Every `ui/*` feature module follows a fixed four-piece shape (see `project-structure.md`
Section 6):

```
src/ollama_llm_bench/ui/new_benchmark/
    __init__.py
    api.py                       # make_new_benchmark_widget(...) -> QWidget  (factory function)
    models.py                    # frozen ViewModel msgspec.Struct + UI event types
    _internal/
        view.py                  # QWidget subclass: rendering only — passive View
        controller.py             # store subscriptions + signal handlers
        view_model_select.py      # pure functions: store state -> ViewModel
    tests/
```

- **`api.py`** exposes a **factory function** that constructs and wires the widget, returning
  a `QWidget`. It receives its dependencies — the module's one Gateway and the shared
  `EventBus`/stores it is permitted to see — as keyword arguments, satisfying the ≤4-parameter
  rule via a dependency-bundle `msgspec.Struct` when collaborators exceed four (see
  `coding-style.md` Section "Function/class/complexity limits").
- **`view.py`** is **passive**: it renders a `ViewModel` and emits Qt signals on user
  interaction. It imports no adapter gateway, no reactive store, and no backend symbol — only
  UI primitives, its controller, and `models.py`. An architecture test (`test_view_is_passive`)
  enforces this.
- **`controller.py`** subscribes to store/event-bus changes, calls `view_model_select`
  functions to derive the `ViewModel`, pushes it to the view, and translates view signals into
  Gateway calls.
- **`view_model_select.py`** holds pure functions (store state -> `ViewModel`) with zero Qt
  involvement — directly unit-testable with no `QApplication`.

## The Gateway-only dependency rule (D-R-06)

A UI controller may hold **only its own per-widget Gateway Protocol** from the adapters layer
— it must never hold a backend Store/Service Protocol directly. Each top-level widget/dialog
has exactly one Gateway that wraps every backend Store/Service it needs:

| Widget           | Gateway               |
| ---------------- | --------------------- |
| Main Window      | `MainWindowGateway`   |
| New Benchmark    | `NewBenchmarkGateway` |
| Resume Benchmark | `ResumeGateway`       |
| Progress         | `ProgressGateway`     |
| Result           | `ResultGateway`       |
| Settings Dialog  | `SettingsGateway`     |
| Task Editor      | `TaskEditorGateway`   |

```python
from typing import Protocol


class ProgressGateway(Protocol):
    """Adapter gateway for the Progress widget (D-R-06)."""

    def pause_run(self) -> None:
        """Request a cooperative pause of the active run."""
        ...
```

A backend value that a widget needs but a service does not expose through its own call surface
(for example a contract-local enum used internally by a service) is carried **only through the
adapter** — on a progress-event payload or a `ViewModel` field — never read by the widget
calling the backend service directly.

## QRunnable completion — no Qt signal in the completion path

`adapters/qt_runnables/` implements the backend's `TaskRunner` Protocol with `QThreadPool` +
`QRunnable`. `QRunnable.run()` must set the unit's thread-safe `Future` result/exception
**directly on the worker thread**:

```python
class _BackendUnitRunnable(QRunnable):
    def __init__(self, fn: Callable[[], object], future: Future[object]) -> None:
        super().__init__()
        self._fn = fn
        self._future = future

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except BaseException as exc:  # noqa: BLE001  # allowlisted TaskRunner boundary
            self._future.set_exception(exc)
        else:
            self._future.set_result(result)
```

The dispatcher thread (`concurrency-standard.md`) blocks in `Future.result()` with no Qt event
loop running — a queued Qt signal aimed at it would never be delivered, hanging the dispatcher
forever. Qt's role in this path is the thread pool only; the UI learns about progress and
terminal states exclusively through the event bus, never a unit-completion signal.

## Owner-bound EventBus subscriptions

- Every `subscribe_to_*` call made from inside a `QWidget` subclass **must** pass `parent=self`.
  Omitting `parent` from a transient widget (e.g. a dialog tab) leaves a zombie subscription
  that fires on a half-destroyed C++ object, causing `libshiboken` crashes.
- Controller-internal subscriptions (non-`QObject` classes — e.g. a plain `controller.py`
  class) must **not** pass `parent=` — they have no `destroyed` signal.
- When adding a new `EventBus` `subscribe_to_*` method, add the corresponding `parent`
  parameter to both the backend Protocol and the concrete `QtEventBus` implementation.

```python
# GOOD — inside a QWidget subclass
self._bus.subscribe_to_run_progress(self._on_progress, parent=self)

# BAD — leaves a zombie subscription after the dialog closes
self._bus.subscribe_to_run_progress(self._on_progress)
```

## Signals, slots, and threading

- Use `signal.connect(slot)` syntax — never string-based or legacy connections.
- Use `functools.partial` or a default-argument-bound lambda for extra slot data; never
  capture a mutable loop variable directly in a lambda.
- `QRunnable.run()` is decorated `@Slot()`.
- Custom worker signals live on a separate `QObject` subclass — `QRunnable` does not inherit
  `QObject`.
- No `QWidget` method is ever called from a background thread; a worker result reaches the UI
  as a `Future` value or a typed event, marshalled onto the GUI thread via a queued
  signal/slot connection (`concurrency-standard.md`).
- **Never declare a method literally named `emit` on the same `QObject` that owns a `Signal`.**
  PySide6/Shiboken treats any attribute named `emit` — method, property, or instance attribute
  — on a `QObject` as an override of the legacy per-object `QObject.emit(signal, *args)`
  dispatch; once it exists, *every* `SignalInstance.emit()` call for *any* signal owned by that
  object is silently redirected through the override instead of performing real Qt signal
  activation (discovered in STORY-040 — `adapters/qt_event_bus/`). A `Protocol` requiring a
  method named `emit` (e.g. `backend.events.EventBus`) is implemented by giving the `QObject`
  a private helper `QObject` to hold the `Signal`, held as an instance attribute and never
  exposed — see `adapters/qt_event_bus/_internal/deliverer.py`'s `_RelayCarrier` for the
  pattern. This affects every future adapter connecting a Qt-free Protocol with an `emit`
  method to a real Qt signal (`qt_inference_activity_bridge`, `store_qt_bridge`).

## Widgets, layouts, and forms

- Use typed accessor methods (`.isChecked()`, `.value()`, `.text()`, `.currentText()`).
- Use Qt layout managers exclusively (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`,
  `QStackedLayout`) — never absolute pixel positioning.
- Every margin, padding, and gap is a spacing-token value passed into `setSpacing`/
  `setContentsMargins` — never an arbitrary pixel literal.
- A custom `QAbstractItemModel`/`QAbstractTableModel` subclass emits `layoutChanged` after
  add/remove/reorder and `dataChanged` for value changes, and is validated in tests with
  `QAbstractItemModelTester` (see `testing.md`).

## UI standardization — non-negotiable patterns

The full pattern catalogue is `08_Cross_Cutting/08-L_ui_standardization.md`; the binding rules
most relevant while writing widget code:

- **No placeholder UI.** A control that does not apply to the current state is **removed from
  the layout**, not shown greyed out. A transiently-disabled control (about to become
  actionable) is permitted but **must** carry a tooltip explaining why.
- **Dialog button ordering.** The right-most button is the primary/default action;
  lower-priority actions sit to its left; the escape/back-out action (Cancel/Discard/Close/
  Back) sits immediately to the left of the primary confirm. A multi-action footer splits into
  a left side-action cluster and a right back-out-then-primary cluster.
- **Verdict/status colour is never the sole channel** — always paired with a text label and/or
  glyph.
- **Mouse-only operation.** No custom keyboard shortcuts, accelerators, or required
  keyboard-navigation paths; only the host toolkit's incidental Enter/Esc dialog defaults are
  permitted (D-R-07).
- Every icon-only or transiently-disabled control ships a hover tooltip.

## Resources and platform fonts

- Access package assets via `importlib.resources` — never a bare relative path string like
  `"icons/app.png"`.
- The theme module selects fonts by **platform branching only** (`PlatformKind` from the
  Platform Detector, or `sys.platform`/`QSysInfo`) — it **never** probes `QFontDatabase` for
  per-family availability. The declared chain is handed to Qt, which resolves it to the first
  available family.
