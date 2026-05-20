# PySide6 Threading Guide

Threading in PySide6 has one inviolable rule: **never touch widgets from a background thread**. Everything else follows from this.

## Why Threading Matters

PySide6 runs a single-threaded event loop. Any operation that takes more than ~50ms blocks the UI — the window freezes, buttons don't respond, progress bars don't update. Network calls, database queries, LLM inference, file I/O — all of these must happen off the main thread.

## Decision: Which Threading Pattern?

PySide6 provides multiple threading mechanisms. Pick **exactly one** per code path and don't mix.

| Pattern | Use for | Project default? |
|---|---|---|
| `QThreadPool` + `QRunnable` | Fire-and-forget jobs; one-shot use-case calls; short streams | ✅ **Default** |
| `QThread` + worker `QObject` + `moveToThread` | Long-lived background workers needing their own event loop; persistent subscribers | When a worker needs to live across many operations |
| `qasync` + `@asyncSlot` | I/O-bound async work (HTTP, websockets, async DB drivers) | Consider for new async-native features |
| `concurrent.futures.ThreadPoolExecutor` | Pure-Python parallelism with no Qt awareness | Rare — only inside backend code that has no Qt dep |

**Anti-patterns — never use these:**

- ❌ `QThread` **subclassing** with logic inside `run()` (Qt's docs explicitly warn against it; slots invoked on the QThread instance run on the *creator* thread, not the new thread).
- ❌ `threading.Thread` directly (no Qt signal integration).
- ❌ `QApplication.processEvents()` in a loop to "keep UI responsive" (re-entrant, corrupts state).
- ❌ Calling `time.sleep()` on the main thread.

## The QThreadPool + QRunnable Pattern

This is the **default** for PySide6 background work. Use it for any backend call that is one-shot or short-stream and doesn't need a long-lived event loop.

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

---

## The `QThread.moveToThread()` Pattern (for long-lived workers)

When a worker should live across many operations (a long-running subscriber, a persistent connection handler, a background service), use the **worker + `moveToThread`** pattern instead of `QRunnable`.

### Why not subclass `QThread`?

Qt's documentation explicitly warns against this:

> "It is important to remember that a `QThread` instance lives in the old thread that instantiated it, not in the new thread that calls `run()`. This means that all of `QThread`'s queued slots and invoked methods will execute in the old thread. Thus, a developer who wishes to invoke slots in the new thread must use the worker-object approach; new slots should not be implemented directly into a subclassed `QThread`."

Subclassing `QThread` and putting logic in `run()` is the most common Qt threading mistake. **Don't.**

### The correct pattern

```python
from PySide6.QtCore import QObject, QThread, Signal, Slot


class IngestWorker(QObject):
    """Long-lived worker living on its own thread."""

    progress = Signal(int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, *, ingest_uc: IngestUseCase) -> None:
        super().__init__()
        self._ingest_uc = ingest_uc

    @Slot(Path)
    def ingest(self, source: Path) -> None:
        """Process one source. May be called many times."""
        try:
            for pct, payload in self._ingest_uc.execute(source):
                self.progress.emit(pct)
            self.done.emit(payload)
        except Exception as e:
            self.failed.emit(str(e))


# In the presenter:
class IngestPresenter(QObject):
    def __init__(self, *, ingest_uc: IngestUseCase, ...) -> None:
        super().__init__()
        self._thread = QThread(self)
        self._worker = IngestWorker(ingest_uc=ingest_uc)
        self._worker.moveToThread(self._thread)

        # Connect signals BEFORE starting the thread
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self._on_progress)

        # Wire cleanup
        self._thread.finished.connect(self._worker.deleteLater)

        self._thread.start()

    def request_ingest(self, source: Path) -> None:
        # Call worker.ingest via queued signal (cross-thread safe)
        QMetaObject.invokeMethod(
            self._worker, "ingest", Qt.QueuedConnection,
            Q_ARG(Path, source),
        )

    def shutdown(self) -> None:
        """Always stop the worker before the app exits."""
        self._thread.quit()
        if not self._thread.wait(3000):
            logger.warning("Worker thread did not stop cleanly")
```

### Rules

- **Decorate cross-thread slots with `@Slot(...)`** — this is required for queued connections to dispatch correctly.
- **Connect all signals BEFORE `thread.start()`** — connections after start are still valid but easier to forget.
- **`thread.quit() + thread.wait(timeout_ms)` in `closeEvent` / shutdown.** Skipping this hangs the app on exit.
- **Use `deleteLater()` for cleanup** — direct `del worker` from the main thread while it's still on its own thread can crash.
- **The worker is a `QObject`, not a `QThread` subclass.** The `QThread` is just a thread-with-event-loop the worker lives on.

### When `moveToThread` vs `QRunnable`?

```
Operation runs once and finishes?                  →  QRunnable
Operation processes a queue / serves many requests? →  moveToThread
Need a persistent event loop / timers on the bg thread? →  moveToThread
Fire-and-forget?                                   →  QRunnable
```

For this project, **`QRunnable` covers ~90% of cases.** Reach for `moveToThread` only when an existing `QRunnable`-based design needs to grow into a long-lived service.

---

## The `qasync` Pattern (for async I/O)

When your backend is async-native (uses `httpx.AsyncClient`, `aiohttp`, async DB drivers, websockets), use **`qasync`** to integrate the asyncio loop into Qt's loop. From the qasync README: *"qasync allows coroutines to be used in PyQt/PySide applications by providing an implementation of the PEP 3156 event loop."*

### Setup

```toml
# pyproject.toml
dependencies = [
    "qasync>=0.27",
]
```

```python
# main.py
import asyncio
import sys

import qasync
from PySide6.QtWidgets import QApplication


def main() -> None:
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow(...)
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
```

### Async slots

```python
from qasync import asyncSlot


class SearchPresenter(QObject):
    results = Signal(list)
    error = Signal(str)

    def __init__(self, *, search_uc: SearchUseCase) -> None:
        super().__init__()
        self._search_uc = search_uc

    @asyncSlot(str)
    async def search(self, query: str) -> None:
        try:
            items = await self._search_uc.execute(query)
        except Exception as e:
            self.error.emit(str(e))
            return
        self.results.emit(items)
```

The view connects to `presenter.search` like any other slot:

```python
self._search_input.returnPressed.connect(
    lambda: presenter.search(self._search_input.text())
)
```

### Rules

- **Only use `qasync` if your backend is genuinely async.** Don't introduce it just to look modern — `QRunnable` is simpler for synchronous backends.
- **CPU-bound work on the asyncio loop will still block.** Wrap CPU-heavy code in `loop.run_in_executor()`.
- **Don't mix `qasync` and `QtAsyncio` (PySide6's built-in).** As of 2025, `QtAsyncio` is incomplete (no full networking support per Qt Forum reports). Prefer `qasync` for production until QtAsyncio matures.
- **Caveat for this project:** the backend today is synchronous (the `openai` / `anthropic` / `google-genai` clients are synchronous in the chosen usage). `qasync` is **not adopted**. Document this decision; revisit only if the backend migrates to async clients.

---

## Threading Pattern Decision Summary

```
Is the operation expected to complete in < 50 ms on the main thread?
  └─ YES → Just call it directly from the slot (no threading)
  └─ NO ↓

Is the operation one-shot (start, complete, done)?
  ├─ YES → QRunnable + QThreadPool (the default)
  └─ NO → Does it need a persistent event loop / handles many requests over its lifetime?
       ├─ YES → QThread + worker QObject + moveToThread
       └─ NO → QRunnable + QThreadPool with cancellation flag

Is the backend natively async (async def / await)?
  └─ YES, AND the project is committed to async-everywhere → qasync + @asyncSlot
  └─ NO → Stick with QRunnable / moveToThread; this project is synchronous backend
```

---

## Where Threading Code Lives (Architecture Constraint)

Per [../SKILL.md §1 Architecture Layer Rules](../SKILL.md) and [backend-ui-boundary.md](backend-ui-boundary.md):

- **All `QRunnable` / `QThreadPool` / `moveToThread` / `qasync` integration lives in `ui/qt_classes/`.**
- `backend/services/` is synchronous and Qt-agnostic. It does not know it might be called from a worker thread.
- The composition root (`app_context.py`) constructs adapters in `ui/qt_classes/` and gives them references to backend use-cases.

If you find yourself writing `QRunnable` inside `backend/services/`, stop — the threading concern belongs in the UI adapter layer. The backend should keep its synchronous, Qt-free property so it remains testable as plain Python.
