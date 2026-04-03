---
name: pyside6
description: PySide6 threading, signals/slots, widget construction, MetaQObjectABC, and EventBus patterns for Ollama LLM Bench UI. Use when writing or reviewing any PySide6/Qt code in qt_classes/ or ui/.
paths: src/ollama_llm_bench/qt_classes/**/*.py, src/ollama_llm_bench/ui/**/*.py
allowed-tools: Read, Grep, Glob
---

# PySide6 Desktop Development — Ollama LLM Bench

> **Migration note**: Existing code uses PyQt6 imports (`PyQt6.QtCore`, `pyqtSignal`, etc.). New code MUST use PySide6 equivalents (`PySide6.QtCore`, `Signal`, etc.). When touching existing files, migrate imports opportunistically.

## Import Migration Reference

| PyQt6 | PySide6 |
|-------|---------|
| `from PyQt6.QtCore import pyqtSignal` | `from PySide6.QtCore import Signal` |
| `from PyQt6.QtCore import pyqtSlot` | `from PySide6.QtCore import Slot` |
| `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| `from PyQt6.QtCore import QMutex, QMutexLocker` | `from PySide6.QtCore import QMutex, QMutexLocker` |

---

## Critical Rules

- MUST execute all widget reads and writes exclusively on the main (GUI) thread
- MUST use `QThreadPool` + `QRunnable` for all operations exceeding 100 ms — never block the main thread
- MUST use `MetaQObjectABC` metaclass when combining `QObject` with `ABC` (see `qt_classes/meta_class.py`)
- MUST install a global `sys.excepthook` during startup for crash logging
- MUST NOT use `threading.Thread` or `concurrent.futures` for Qt-integrated work — use Qt's threading model
- MUST NOT import Tkinter, wxPython, or other GUI frameworks

---

## Architecture Overview

```
core/interfaces.py    → EventBus ABC (no Qt dependency)
qt_classes/meta_class.py → MetaQObjectABC (QObject + ABCMeta)
qt_classes/qt_event_bus.py → QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC)
qt_classes/qt_benchmark_execution_task.py → BenchmarkExecutionTask(QRunnable)
ui/controllers/       → Controllers subscribing to EventBus signals
ui/widgets/            → PySide6 widgets rendering data
```

---

## MetaQObjectABC Pattern

Required when a class must be both a `QObject` (for signals/slots) and an `ABC` (for interface enforcement):

```python
from abc import ABCMeta
from PySide6.QtCore import QObject

class MetaQObjectABC(type(QObject), ABCMeta):
    """Metaclass combining QObject and ABCMeta."""

# Usage:
class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
    _run_id_changed = Signal(int)
    # ... signal definitions and implementations
```

MUST NOT attempt multiple inheritance of `QObject` + `ABC` without this metaclass — it causes `TypeError`.

---

## Threading & Concurrency

- **Main thread**: all widget operations, `Signal` emissions, `ObservableList`-equivalent mutations
- **Background**: `QThreadPool` with `QRunnable` subclasses (see `BenchmarkExecutionTask`)
- **Signal bridge**: `QRunnable` holds a nested `Signals(QObject)` class to emit typed signals

```python
class BenchmarkExecutionTask(QRunnable):
    class Signals(QObject):
        status_changed = Signal(bool)
        log_message = Signal(str)
        progress = Signal(ReporterStatusMsg)

    def __init__(self, *, run_id: int, data_api: DataApi) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._stop_requested = False
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            self.signals.status_changed.emit(True)
            self._do_work()
        finally:
            self.signals.status_changed.emit(False)
```

**Thread pool configuration:**
```python
thread_pool = QThreadPool()
thread_pool.setMaxThreadCount(1)  # Serial execution
thread_pool.start(task)
```

---

## EventBus Pattern

The `QtEventBus` decouples components using typed signals:

1. **Define** ABC methods in `core/interfaces.py` (`subscribe_to_*`, `emit_*`)
2. **Implement** with `Signal` in `QtEventBus` — each event has a private signal
3. **Subscribe** in controllers/widgets via `event_bus.subscribe_to_*(callback)`
4. **Emit** from services/controllers via `event_bus.emit_*(value)`

```python
# In controller __init__:
event_bus.subscribe_to_run_id_changed(self._on_run_id_changed)

# Callback:
def _on_run_id_changed(self, run_id: int) -> None:
    if run_id < 0:
        return  # -1 means no selection
    self._current_run_id = run_id
    self._refresh_data()
```

**Adding a new event requires:**
1. `subscribe_to_*` and `emit_*` abstract methods in `EventBus` ABC
2. Private `Signal` in `QtEventBus`
3. Implementations connecting signal to callback / emitting signal

---

## Widget Construction

- Set `self` as parent for child widgets to ensure proper Qt object tree cleanup
- Use layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`) — never absolute positioning
- Connect signals in `__init__` or dedicated `_setup_connections()` method

```python
class MyWidget(QWidget):
    def __init__(self, *, controller: MyControllerApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._label = QLabel("Status:", self)
        self._button = QPushButton("Run", self)
        layout.addWidget(self._label)
        layout.addWidget(self._button)

    def _setup_connections(self) -> None:
        self._button.clicked.connect(self._on_run_clicked)
```

---

## Cancellation Pattern

Background tasks must support cooperative cancellation:

```python
def stop(self) -> None:
    self._stop_requested = True

def run(self) -> None:
    for item in items:
        if self._stop_requested:
            logger.info("Task cancelled by user")
            return
        self._process(item)
```

MUST check `_stop_requested` at every loop iteration and before expensive operations.

---

## Enforcement Checklist

- [ ] No widget mutations from background threads
- [ ] `QRunnable` tasks use nested `Signals(QObject)` for communication
- [ ] `MetaQObjectABC` used when combining `QObject` + `ABC`
- [ ] No `threading.Thread` for Qt-integrated work
- [ ] `setAutoDelete(True)` on `QRunnable` instances
- [ ] Stop/cancel support in all background tasks
- [ ] No PyQt6 imports in new files — use PySide6
