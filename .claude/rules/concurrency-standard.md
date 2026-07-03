---
paths:
  - "src/ollama_llm_bench/backend/**"
  - "src/ollama_llm_bench/adapters/qt_runnables/**"
---

# Concurrency Standard

Source of truth: `docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` and
`docs/v3_specification/11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`. The model is a
**synchronous, framework-agnostic backend driven by an adapter-owned thread-pool runner**.

> **Why (D-R-01).** A synchronous backend is the only design in which the "task runner" is a
> swappable adapter concern: the Qt app runs it on a `QThreadPool`; a headless CLI runs it on a
> `concurrent.futures.ThreadPoolExecutor`; a test runs it inline — all against the same backend
> code, which never imports Qt or `asyncio`.

## The backend is Qt-free and asyncio-free

The backend (pipeline, provider clients, evaluators, stores) is written as ordinary
**blocking** Python with no knowledge of Qt and no knowledge of `asyncio`. **`asyncio` is NOT
used anywhere in the application, and `anyio` is NOT a dependency** (D-R-01) — this supersedes
any earlier asyncio/qasync draft. The concurrency stack is the standard library (`threading`,
`concurrent.futures`) plus Qt's `QThreadPool`/`QRunnable` (adapter layer only) plus the
application-defined `CancellationToken` and `TaskRunner`.

## The TaskRunner port

The backend defines a `TaskRunner` Protocol; it does not know how work is scheduled:

```python
class TaskRunner(Protocol):
    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Schedule a blocking unit of backend work; return a handle to its result."""
```

- **Qt frontend**: `adapters/qt_runnables/` implements it with `QThreadPool` + `QRunnable`
  wrappers. The runnable's `run()` executes the backend callable in `try/except` and completes
  the unit by calling `future.set_result(value)` / `future.set_exception(exc)` **directly on
  the worker thread**.
- **Headless/CLI**: a `concurrent.futures.ThreadPoolExecutor`-backed runner.
- **Tests**: an inline runner executing the callable synchronously — no threads, no Qt.
- The composition root constructs exactly **one** `TaskRunner`. No service constructs a runner
  inline; no backend module imports `QThreadPool`.
- The pool size is **fixed at `maxThreadCount = 4`** (DD-40), configured once at compose time.

## The two serial domains (DD-40) — and nothing else

1. **The benchmark run** — tasks are picked up one-by-one, stage-by-stage (D-R-16); no
   parallel task execution inside a run.
2. **LLM inference, globally** — at most one inference-class call (chat, judge, embedding,
   test inference) is in flight anywhere in the application at any moment, regardless of which
   feature triggered it. The single-inference gate (`InferenceActivityStore`) enforces this
   across activity classes.

Everything else is **unrestricted** and may run concurrently on the worker pool: network
reachability handshakes, model-list fetches (no model compute, NOT inferences), CPU-bound
computations (chart aggregation, CSV/export assembly), file I/O. The readiness probe's
concurrent per-provider handshakes are the canonical example of unrestricted pool work.

## Serial execution for a run (D-R-16)

A run executes its work units **strictly serially**: the dispatcher submits **one** unit,
awaits its `Future`, persists the result, then submits the next. There is at most one in-flight
unit across the whole application at any moment, and **no `max_parallel_units` /
`phase_concurrency` setting** exists — local providers queue concurrent requests anyway, and
parallel calls would distort the latency/throughput the tool measures.

```python
def run_phase(self, batch, token, runner):
    for u in batch:
        token.raise_if_cancelled()                     # safe checkpoint before each unit
        result = runner.submit(lambda: self._evaluate_one(u, token), token=token).result()
        self._persist(result)                          # funnelled to the single DB writer
```

A worker exception is captured on its `Future` and re-raised when read on the owning thread,
then classified per `error-handling-standard.md`.

## The dispatcher thread (DD-38) — the only sanctioned standalone thread

The serial loop runs on a single, dedicated, long-lived **dispatcher thread** named
`pipeline-dispatcher`, created by the composition root, owned by the adapter layer, and
**joined at shutdown**.

- **Command handoff.** `BenchmarkFlowApi.start(...)` / `resume(...)` are fast-synchronous on
  the GUI thread: validate, enqueue a run command to the dispatcher thread, return promptly.
  Pause/Stop are *not* commands — they route through the `CancellationToken`.
- **What runs on the dispatcher thread.** The `run_phase` loop: per-unit token and
  circuit-breaker checks, the adaptive-timeout budget, submitting the unit, **blocking on the
  unit's `Future.result()`**, classifying the outcome, persisting through the single DB writer,
  reporting to `AdaptiveTimeoutService`/`ProviderCircuitBreaker`, emitting run-domain events.
  These two services are touched **only** on this thread — that is what makes their lock-free
  single-owner design safe.
- **The dispatcher is the only sanctioned block-on-futures orchestrator (DD-40).** Any backend
  operation that fans work out to the `TaskRunner` and must wait — the benchmark run loop and
  the readiness `probe_all` batch — runs its orchestration on the dispatcher thread. Leaf units
  on the pool never submit-and-wait, so pool starvation is impossible by construction. The
  single-inference gate already guarantees a probe batch and a benchmark run never overlap.
- **Three execution contexts, exactly:**
  1. **GUI thread** — UI events and marshalled results only; never blocks.
  2. **Dispatcher thread** — the only thread that blocks awaiting a unit's `Future`.
  3. **Pool worker threads** — run individual blocking units; a pool worker must **never**
     submit work to the `TaskRunner` and block awaiting its `Future` (the pool-starvation
     deadlock).
- An architecture test asserts the breaker, the adaptive-timeout service, result persistence,
  and run-domain event emission are reachable only from the dispatcher thread, and that no
  `Future.result()` call occurs on the GUI thread or inside a pool worker.

## The CancellationToken — two levels, monotonic

Cooperative, explicit, backed by `threading.Event` (NOT `asyncio.Event`). One token per run,
threaded through every work unit — never global, never reused across runs. Levels are
monotonic: `NONE -> SOFT -> HARD`, never downgraded (DD-39).

- **Soft** (`hard=False`; Pause, automatic pauses) — the in-flight unit **finishes and is
  saved**; the halt happens at the next safe checkpoint. Pause exists to preserve work.
- **Hard** (`hard=True`; Stop, Shutdown) — the in-flight call is **aborted promptly**: the LLM
  client polls `is_hard_cancelled` at chunk boundaries, and the token's hard-cancel abort hook
  closes the in-flight stream. Nothing partial is persisted; the unit's row stays `PENDING`.
  Bounded by `provider.hard_cancel_max_ms` (default 2000 ms).

```python
class CancellationToken:
    def cancel(self, *, reason: CancelReason, hard: bool = False) -> None: ...
    @property
    def is_cancelled(self) -> bool: ...
    @property
    def is_hard_cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...          # raises TaskCancelledError
    def wait(self, timeout: float | None = None) -> bool: ...
    def snapshot(self) -> tuple[CancelLevel, CancelReason | None]: ...
    def add_hard_cancel_hook(self, hook: Callable[[], None]) -> None: ...
    def remove_hard_cancel_hook(self, hook: Callable[[], None]) -> None: ...
```

Worker code calls `raise_if_cancelled()` at **safe checkpoints** — before starting a unit and
after it completes — never mid non-atomic operation. The reason is a closed enum
(`CancelReason`: `USER_PAUSE`, `AUTO_PAUSE`, `USER_STOP`, `APP_SHUTDOWN`), not free text
(DD-42), set under the token's single internal lock together with the level.

## Thread-boundary rules

- **Never touch a widget from a worker thread.** Widget state changes only on the GUI thread.
  A worker result reaches the UI as a `Future` value or a typed event; the adapter marshals it
  onto the GUI thread via a **queued** signal/slot connection.
- **The backend never imports Qt.** `QThreadPool`, `QRunnable`, `QObject`, `Signal` exist only
  in the adapter and UI layers. Shared contracts (Protocols, DTOs, enums, event payloads,
  `CancellationToken`, `TaskRunner`) depend only on the standard library and `msgspec`.
- **Shared mutable state is a tiny, explicitly-locked surface — exactly two objects:**
  - the **inference-activity gate** (`InferenceActivityStore`) — acquired/released around each
    inference activity;
  - the **single DB writer** (DD-41) — one write connection guarded by one `threading.Lock`.
    Every SQLite write acquires the lock and runs its transaction (`BEGIN IMMEDIATE`)
    synchronously on the calling thread. During a run, run-domain writes are issued only by the
    dispatcher thread; worker units never write. Readers use separate read-only connections.
  Every other store and view-model is owned by exactly one thread and needs no lock.
- **Blocking is expected on workers, forbidden on the GUI thread.** Synchronous HTTP,
  `time.sleep`, file I/O run on worker threads only.

## CPU-bound work

Chart aggregation and CSV/export assembly run on the **same `TaskRunner`** as I/O work — they
are submitted as ordinary backend callables and execute on a `QThreadPool` worker, off the GUI
thread. CPU-bound backend functions are pure: inputs as arguments, return a value, touch no Qt
object, touch no shared mutable state. Code **must not** spawn raw `threading.Thread` objects
for state-bearing work.

## UI-update coalescing

A backend emitter MAY produce progress at a fixed cadence (a >= 1 Hz heartbeat); that emission
cadence is a backend concern, while the **repaint** cadence (<= 1 per frame) is owned by the
adapter/controller. High-frequency UI updates are coalesced at the controller/adapter boundary.
Backend services never decide repaint timing and never import a Qt timer.

## The critical anti-pattern: never complete a unit via a queued Qt signal

The dispatcher blocks in `Future.result()` with **no Qt event loop running on that thread**.
If `QRunnable.run()` tried to complete the unit via a queued Qt signal aimed at the dispatcher,
the signal would never be delivered and the dispatcher would hang forever. `QRunnable.run()`
must set the unit's thread-safe `Future` result/exception **directly on the worker thread**
(`concurrent.futures.Future` is thread-safe; a waiter blocked in `.result()` wakes via the
Future's internal condition variable). Qt's role in the completion path is the thread pool
only — the UI learns about progress and terminal states exclusively through the event bus,
never from a unit-completion signal.

## Anti-patterns

| Anti-pattern | Why it is wrong | Correct approach |
|---|---|---|
| Importing Qt or `asyncio` in the backend | Breaks backend independence and the swappable-runner contract | Backend is plain blocking Python; scheduling lives behind `TaskRunner` |
| Spawning a raw `threading.Thread` for a work unit | Unmanaged lifetime; no clean shutdown | Submit through `TaskRunner`; the only sanctioned standalone thread is the dispatcher (DD-38) |
| Blocking on a unit's `Future` from the GUI thread or a pool worker | Frozen UI; pool-starvation deadlock | Only the dispatcher thread blocks on unit `Future`s |
| Parallel / fan-out provider calls in a run | Distorts the measured latency/throughput; overruns local providers | Serial execution — exactly one in-flight unit at a time (D-R-16) |
| A blocking call on the GUI thread | Freezes the UI | Run all blocking work on a worker via `TaskRunner` |
| Touching a widget from a worker thread | Undefined Qt behaviour, crashes | Return a value or publish an event; the adapter marshals to the GUI thread |
| `asyncio.Event` (or any loop-affine primitive) for cancellation | No loop exists | The `threading.Event`-backed `CancellationToken` |
| Per-feature cancellation booleans | Fragmented, unobservable cancellation | The single `CancellationToken` type |
| Interrupting a provider request mid-flight on a soft cancel (Pause) | Throws away the work the pause exists to preserve | Soft cancel finishes and saves the unit; only hard cancel aborts mid-stream |
| A worker unit writing to the database | Breaks dispatcher write-affinity and the persist-before-next durability point | Workers return data; the dispatcher persists; every write holds the single writer lock |
| Catching `BaseException` | Swallows the programmer-error type that must crash | Catch a specific category or leaf type |
| Missing `raise_if_cancelled()` between retry attempts | Cancellation ignored during backoff | Check the token inside every retry attempt |
| Completing a unit via a queued Qt signal | The dispatcher blocks with no Qt event loop — the signal is never delivered, dispatcher hangs forever | `QRunnable.run()` sets the `Future` result/exception directly on the worker thread |
