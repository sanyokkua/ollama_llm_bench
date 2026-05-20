---
description: "PySide6 application development rules — Qt event loop, signals/slots, widgets, threading, Model/View"
globs: "src/ollama_llm_bench/ui/qt_classes/**/*.py,src/ollama_llm_bench/ui/**/*.py"
alwaysApply: false
---

# PySide6 Application Development

> PySide6 only. The codebase uses `from PySide6.QtCore import Signal, Slot` and `MetaQObjectABC` consistently.

## Critical Rules

- MUST run the Qt event loop on the main thread — MUST NOT execute any operation exceeding 50ms on the main thread
- MUST NOT call `QApplication.processEvents()` in a loop as a workaround for UI freezing
- MUST NOT modify any `QWidget` from a background thread — communicate results exclusively via Qt signals
- MUST create exactly one `QApplication` instance per process, before any other Qt object
- MUST pass `sys.argv` to `QApplication()` — MUST NOT pass an empty list
- MUST guard `QApplication` instantiation and `app.exec()` inside `if __name__ == "__main__":`
- MUST wrap `app.exec()` with `sys.exit()` to propagate exit code

## Application Entry Point

```python
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("My App")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

- MUST subclass `QMainWindow` for primary windows — MUST NOT use bare `QWidget` when menus/toolbars/status bar are needed
- MUST set central widget via `self.setCentralWidget(widget)` — MUST NOT call `.setLayout()` on `QMainWindow`

## Signals, Slots & Events

- MUST use `signal.connect(slot)` syntax — MUST NOT use string-based or legacy connections
- MUST ensure slot functions accept all arguments emitted by connected signal
- MUST use `functools.partial` or lambda with default-argument binding for extra slot data
- MUST NOT capture mutable loop variables directly in a lambda without binding:

```python
# GOOD
for i, btn in enumerate(buttons):
    btn.clicked.connect(partial(self.handle_click, i))

# BAD — all buttons use LAST value of i
for i, btn in enumerate(buttons):
    btn.clicked.connect(lambda: self.handle_click(i))
```

## EventBus Subscription Ownership

- MUST pass `parent=self` on every `subscribe_to_*` call made from inside a `QWidget` subclass.
  Omitting `parent` from a transient widget (e.g. a dialog tab) leaves a zombie subscription
  that fires on a half-destroyed C++ object, causing `libshiboken` crashes.
- Controller-internal subscriptions (non-QObject classes) MUST NOT pass `parent=` — they have
  no `destroyed` signal.
- When adding a new EventBus `subscribe_to_*` method, MUST add the corresponding `parent`
  parameter to both the ABC in `interfaces.py` and the concrete `QtEventBus` implementation.

## Widgets

- MUST use typed accessor methods (`.isChecked()`, `.value()`, `.text()`, `.currentText()`)
- PREFER populating `QComboBox` from data structures using `.addItems()`
- MUST set `.setRange()` on ranged widgets BEFORE calling `.setValue()`

## Layouts

- MUST use Qt layout managers (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, `QStackedLayout`) — MUST NOT use absolute pixel positioning
- PREFER nesting layouts via `.addLayout()` over complex `QGridLayout` span rules

## Dialogs

- MUST use `QMessageBox` static methods for standard prompts (`.information()`, `.warning()`, `.critical()`, `.question()`)
- MUST pass parent window as first argument when creating any dialog
- MUST use `QDialogButtonBox` for OK/Cancel buttons in custom dialogs

## Multithreading & Concurrency

- MUST use `QRunnable` + `QThreadPool` for offloading work from the main thread
- MUST decorate `QRunnable.run()` with `@Slot()`
- MUST define custom worker signals on a separate `QObject` subclass — `QRunnable` does not inherit `QObject`
- MUST NOT call any `QWidget` method from a background thread
- MUST NOT use `threading.Thread` for background work in GUI code

```python
from PySide6.QtCore import QRunnable, Slot, Signal, QObject, QThreadPool

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.signals.error.emit(str(e))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
```

## Model/View Architecture

- MUST subclass `QAbstractListModel`/`QAbstractTableModel` for dynamic data — MUST NOT populate list widgets by adding strings directly
- MUST emit `layoutChanged` after add/remove/reorder, `dataChanged` for value changes
- MUST handle distinct `Qt.ItemDataRole` values in `data()` and return `None` for unhandled roles

## Widget Construction Phase Separation

- PREFER separating widget construction, signal wiring, and layout composition into distinct phases in `__init__`
- MUST NOT interleave widget creation, signal connections, and layout additions arbitrarily

## Resources & File Paths

- PREFER accessing package assets via `importlib.resources`
- MUST NOT use bare relative path strings like `"icons/app.png"`
