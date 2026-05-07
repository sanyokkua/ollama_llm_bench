# PySide6 Threading Guide

Threading in PySide6 has one inviolable rule: **never touch widgets from a background thread**. Everything else follows from this.

## Why Threading Matters

PySide6 runs a single-threaded event loop. Any operation that takes more than ~50ms blocks the UI — the window freezes, buttons don't respond, progress bars don't update. Network calls, database queries, LLM inference, file I/O — all of these must happen off the main thread.

## The QThreadPool + QRunnable Pattern

This is the correct pattern for PySide6 background work. Don't use `threading.Thread` (no Qt integration), don't use `QThread` subclassing (error-prone), and absolutely don't use `QApplication.processEvents()` (re-entrant, breaks everything).

### Step 1: Define Signals on a QObject

`QRunnable` cannot have signals directly (it's not a QObject). Create a separate signals class:

```python
from PySide6.QtCore import QObject, Signal

class WorkerSignals(QObject):
    """Signals for background worker communication."""
    started = Signal()
    finished = Signal()
    error = Signal(str)           # error message
    result = Signal(object)       # any return value
    progress = Signal(int, int)   # completed, total
```

### Step 2: Create the Worker

```python
from PySide6.QtCore import QRunnable, Slot

class InferenceWorker(QRunnable):
    """Runs LLM inference in a background thread."""

    def __init__(self, *, provider, model: str, prompt: str):
        super().__init__()
        self.signals = WorkerSignals()
        self._provider = provider
        self._model = model
        self._prompt = prompt
        self.setAutoDelete(True)  # Qt cleans up after run()

    @Slot()
    def run(self) -> None:
        """Execute in background thread. Do NOT touch any widget here."""
        self.signals.started.emit()
        try:
            response = self._provider.generate(
                model=self._model, prompt=self._prompt
            )
            self.signals.result.emit(response)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
```

### Step 3: Launch from the Main Thread

```python
class BenchmarkController:
    def __init__(self, *, threadpool: QThreadPool):
        self._threadpool = threadpool

    def start_inference(self, provider, model: str, prompt: str) -> None:
        worker = InferenceWorker(
            provider=provider, model=model, prompt=prompt
        )
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        self._threadpool.start(worker)

    def _on_result(self, response: object) -> None:
        # This runs on the main thread — safe to update widgets
        self._widget.display_response(response)

    def _on_error(self, message: str) -> None:
        self._widget.show_error(message)
```

## Architecture Constraint

In this project's architecture, all `QRunnable` and `QThreadPool` usage lives exclusively in `qt_classes/`. Workers defined there. Controllers in `ui/controllers/` connect signals to widget updates. This separation means:

- `services/` has no Qt dependency and is unit-testable
- `qt_classes/` wraps service calls in workers
- `ui/controllers/` wires worker signals to widget updates
- `ui/widgets/` only receives signals and updates display

## Streaming Responses

For LLM streaming (token-by-token output), don't emit a signal per token — that floods the event loop. Instead, buffer tokens and flush on a timer:

```python
import time
from PySide6.QtCore import QRunnable, Slot

class StreamingWorker(QRunnable):
    """Streams tokens with buffered updates at ~20 Hz."""

    def __init__(self, *, provider, model: str, prompt: str):
        super().__init__()
        self.signals = WorkerSignals()
        self._provider = provider
        self._model = model
        self._prompt = prompt
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        buffer = []
        last_flush = time.monotonic()
        flush_interval = 0.05  # 20 Hz

        try:
            for chunk in self._provider.stream(
                model=self._model, prompt=self._prompt
            ):
                buffer.append(chunk)
                now = time.monotonic()
                if now - last_flush >= flush_interval:
                    self.signals.result.emit("".join(buffer))
                    buffer.clear()
                    last_flush = now

            # Flush remaining
            if buffer:
                self.signals.result.emit("".join(buffer))

        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
```

On the widget side, when receiving streamed text, use a similar batching approach. If the signal handler appends to a QTextEdit, the QTextEdit itself handles rendering efficiently — but only if you're not calling `append()` hundreds of times per second.

## Cancellation

Workers should check a cancellation flag periodically:

```python
import threading

class CancellableWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        for i in range(total_tasks):
            if self._cancelled.is_set():
                self.signals.error.emit("Cancelled by user")
                return
            # ... do work ...
            self.signals.progress.emit(i + 1, total_tasks)
        self.signals.finished.emit()
```

The controller calls `worker.cancel()` when the user clicks Stop. The worker checks the flag at each iteration boundary.

## Common Threading Mistakes

| Mistake | What Happens | Fix |
|---------|-------------|-----|
| Update widget from `run()` | Crash or corrupted state | Emit signal, handle in main thread |
| `QApplication.processEvents()` | Re-entrant bugs, state corruption | Use QThreadPool properly |
| `time.sleep()` in main thread | UI freezes | Move to worker thread |
| Signal per streaming token | Event queue floods, UI stutters | Buffer + flush at 20 Hz |
| `QThread` subclassing | Easy to misuse, lifecycle bugs | Use QRunnable + QThreadPool |
| No `setAutoDelete(True)` | Memory leak if not manually managed | Enable auto-delete |
| `threading.Thread` for Qt work | No signal/slot integration | Use QRunnable |
| Sharing mutable state between threads | Race conditions | Use signals or thread-safe containers |

## Thread Pool Configuration

```python
# In application setup
threadpool = QThreadPool.globalInstance()
threadpool.setMaxThreadCount(4)  # Limit concurrent workers
```

For benchmark runs where you want sequential model execution but parallel infrastructure (health checks, embedding calls), use separate thread pools or manage the queue in the controller.

## QTimer for Periodic UI Updates

When you need periodic updates (elapsed time, animation frames), use `QTimer` on the main thread:

```python
from PySide6.QtCore import QTimer

class BenchmarkWidget(QFrame):
    def __init__(self):
        super().__init__()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)  # 1 second
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    def start_timer(self) -> None:
        self._start_time = time.monotonic()
        self._elapsed_timer.start()

    def stop_timer(self) -> None:
        self._elapsed_timer.stop()

    def _update_elapsed(self) -> None:
        elapsed = time.monotonic() - self._start_time
        self._elapsed_label.setText(format_duration(elapsed))
```

`QTimer` fires on the main thread event loop, so it's safe to update widgets in its callback. Use it for anything that needs periodic UI refresh — elapsed time displays, animation, polling indicators.
