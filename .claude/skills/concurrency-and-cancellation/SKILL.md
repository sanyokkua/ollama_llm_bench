---
name: concurrency-and-cancellation
description: Use when touching backend/benchmark_pipeline, backend/concurrency, adapters/qt_runnables, or anything involving TaskRunner, CancellationToken, the dispatcher thread, or the single-inference gate. This is the highest-risk area in the codebase — a wrong change here causes real deadlocks, not just bugs.
---

# Concurrency Model and Cancellation

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (the algorithm) and `docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (the binding standard, authoritative per D-R-01). Read both before touching anything in this area — this skill summarizes the parts that cause real production deadlocks when misunderstood.

## The model in one paragraph

The backend is **synchronous and Qt-free** — no `asyncio`, no event loop, anywhere in the application (D-R-01). Backend work runs as ordinary blocking Python on `QThreadPool` worker threads dispatched through an adapter-owned `TaskRunner` port. A benchmark run's orchestration loop runs on exactly **one dedicated dispatcher thread** (DD-38) — the only thread in the whole application allowed to block on a work unit's `Future`. Cancellation is explicit and cooperative through a single, framework-agnostic, two-level `CancellationToken` (DD-39). Backend→UI notifications travel on a Qt-free event bus, marshalled onto the GUI thread by the adapter. There are exactly **three execution contexts**: the GUI thread (never blocks), the dispatcher thread (the only thread that blocks on a `Future`), and the pool worker threads (run individual blocking units, never submit-and-wait on the pool themselves).

## The `TaskRunner` port

```python
# shared contracts (Qt-free, asyncio-free)
class TaskRunner(Protocol):
    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Schedule a blocking unit of backend work; return a handle to its result."""
```

- The **Qt frontend** implements this with `QThreadPool` + `QRunnable` wrappers in `adapters/qt_runnables/`.
- A **headless/CLI** frontend implements it with `concurrent.futures.ThreadPoolExecutor`.
- A **test** implements it inline — the callable runs synchronously, on the test's own thread, so backend logic is unit-tested with zero threads and zero Qt.
- The pool size is **fixed at `maxThreadCount = 4`** (DD-40), set once at compose time. No backend module ever constructs a `QThreadPool` or a raw thread itself — it submits through the injected `TaskRunner` only.

## The single dedicated dispatcher thread (DD-38)

One dispatcher thread exists per process: created by the composition root, owned by the adapter layer, named `pipeline-dispatcher`, and **joined at shutdown**. `BenchmarkFlowApi.start(...)` / `resume(...)` are **fast-synchronous on the GUI thread** — they validate, enqueue a run command to the dispatcher thread, and return promptly. The dispatcher thread then runs the pipeline's blocking run loop.

Everything that blocks on a `Future` happens **only** on this thread: the per-unit `CancellationToken`/circuit-breaker checks, obtaining the adaptive-timeout budget, submitting the unit, **`Future.result()`**, classifying the outcome, persisting through the single DB writer, reporting to the `AdaptiveTimeoutService` and `ProviderCircuitBreaker`, and emitting run-domain events. A pool worker must **never** submit-and-wait on the pool — that is the pool-starvation deadlock.

```python
def run_phase(self, batch, token, runner):
    for u in batch:
        token.raise_if_cancelled()                     # safe checkpoint before each unit
        result = runner.submit(lambda: self._evaluate_one(u, token), token=token).result()
        # .result() re-raises a worker exception here for classification — only legal
        # on the dispatcher thread.
        self._persist(result)                          # funnelled to the single DB writer
```

## The critical anti-pattern: never complete a Future via a Qt signal

This is the single most important rule in this skill, stated as plainly as possible:

**A worker's `QRunnable.run()` must set the thread-safe `Future`'s result directly on the worker thread — `future.set_result(value)` / `future.set_exception(exc)` called inline, synchronously, from inside `run()`. It must NEVER complete that `Future` by emitting a Qt signal that some other slot then uses to set the result.**

Why this is a real deadlock, not a style preference: the dispatcher thread is blocked inside `Future.result()`, waiting on `concurrent.futures.Future`'s internal condition variable. That dispatcher thread is **not running a Qt event loop** — it has no `QEventLoop.exec()` anywhere on its call stack. A queued Qt signal is only ever delivered by a receiver's event loop processing its event queue. If the path from worker-thread-completion to dispatcher-thread-wakeup goes through a Qt signal, that signal is queued for delivery on a thread that never spins an event loop to deliver it — so it is **never delivered**, and the dispatcher hangs forever, holding the whole benchmark run hostage.

`concurrent.futures.Future` is thread-safe by itself; a waiter blocked in `.result()` wakes via the Future's own internal condition variable the moment `set_result`/`set_exception` is called from any thread — no Qt machinery is needed or wanted on that path. Qt's only role in this picture is supplying the thread pool. The UI learns about progress and terminal states exclusively through the **event bus** (a separate, independent channel) — never from a unit-completion signal.

```python
# WRONG — the dispatcher will never wake up
class _Runnable(QRunnable):
    completed = Signal(object)   # connecting THIS to set the Future is the deadlock

    def run(self) -> None:
        try:
            value = self._fn()
        except Exception as exc:
            self.completed.emit(("error", exc))     # queued — dispatcher has no event loop!
        else:
            self.completed.emit(("ok", value))
```

```python
# RIGHT — the worker thread completes the Future directly, no Qt signal involved
class _Runnable(QRunnable):
    def __init__(self, fn: Callable[[], T], future: Future[T]) -> None:
        super().__init__()
        self._fn = fn
        self._future = future

    @Slot()
    def run(self) -> None:
        try:
            value = self._fn()
        except BaseException as exc:          # captures the failure for the dispatcher
            self._future.set_exception(exc)    # thread-safe; wakes any .result() waiter
        else:
            self._future.set_result(value)     # thread-safe; wakes any .result() waiter
```

## The two-level `CancellationToken` (DD-39)

One `CancellationToken` per run, backed by `threading.Event` (never `asyncio.Event` — there is no loop). The level is **monotonic**: `NONE → SOFT → HARD`, never downgraded.

```python
class CancellationToken:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()         # set on ANY cancellation
        self._hard_event = threading.Event()    # set on HARD cancellation only
        self._reason: CancelReason | None = None

    def cancel(self, *, reason: CancelReason, hard: bool = False) -> None: ...
    def raise_if_cancelled(self) -> None: ...    # raises TaskCancelledError at safe checkpoints
    def snapshot(self) -> tuple[CancelLevel, CancelReason | None]: ...   # atomic, locked read
```

| Level | Used by | Behavior |
|---|---|---|
| **SOFT** | Pause (`USER_PAUSE`, `AUTO_PAUSE`) | The in-flight unit **finishes and is saved** — a provider request already issued is awaited to completion, not interrupted. The halt happens at the next safe checkpoint (`raise_if_cancelled()`), only after the result is durably persisted. |
| **HARD** | Stop (`USER_STOP`), Shutdown (`APP_SHUTDOWN`) | The in-flight call is **aborted promptly**: the client stops consuming at the next chunk boundary, and a registered abort hook closes the in-flight stream — bounded by `provider.hard_cancel_max_ms` (default 2000 ms). Nothing partial is persisted; the unit's row stays `PENDING`. |

Why the asymmetry is intentional: **Pause exists to preserve work** (its primary real-world use is swapping local models between groups), so interrupting its in-flight request would throw away exactly what the user is trying to keep. **Stop and Shutdown express exit intent** — the user wants out now — so they abort promptly instead, accepting that the aborted unit simply re-runs on resume. Either way a checkpoint is always consistent: Pause achieves it by finishing the unit, Stop by discarding it whole.

Worker code calls `raise_if_cancelled()` only at **safe checkpoints** — before starting a unit and after it completes — never mid-statement, because cancellation here is cooperative, not preemptive: a worker is never killed mid-call. This is why cleanup needs only ordinary `try`/`finally`, with no shield/scope primitive:

```python
def run_with_guaranteed_cleanup(token: CancellationToken, *, correlation_id: str) -> Outcome:
    resource = acquire_resource()
    try:
        token.raise_if_cancelled()          # safe checkpoint honours pause/stop
        result = do_blocking_work(resource, token)
        token.raise_if_cancelled()
        return result
    finally:
        # Runs even if raise_if_cancelled() raised TaskCancelledError above —
        # the worker is never interrupted mid-statement, so cleanup always completes.
        release_and_persist(resource, correlation_id)
```

A `Stop` clicked while a `Pause` is still draining **upgrades** the cancellation soft→hard (never the reverse); the draining call aborts promptly instead of being waited out, and the run settles `STOPPED` rather than parking `PAUSED`. The dispatcher derives the run's halt outcome from exactly **one atomic `token.snapshot()`** per halt — taken after the in-flight unit has settled and before any terminal status is persisted (DD-42) — so level and reason are never read as a torn pair.

## Serial execution (D-R-16) — there is no concurrency knob

A run executes its tasks **strictly serially**: the dispatcher submits exactly **one** unit, awaits its `Future`, persists, then submits the next. There is **no `phase_concurrency` / `max_parallel_units` setting and no fan-out** — those knobs do not exist, by deliberate design (D-R-16), not an oversight: local providers (Ollama, LM Studio, llama.cpp) queue concurrent requests anyway, and even providers that accept parallel calls split context/inference speed across them, which would distort the very latency and throughput numbers the tool exists to measure.

Within a phase, units are additionally grouped first by `provider_id`, then by `model_name` — no provider switch happens mid-phase within a model group, which keeps the adaptive-timeout statistics for a `(provider, model)` target dense and lets the circuit breaker skip a tripped provider's remaining groups cleanly.

## The single-inference gate (`InferenceActivityStore`)

Distinct from serial execution, and easy to conflate with it: across the **whole application**, at most **one inference-class call** is in flight at any moment, full stop — not just within a run. `InferenceActivity` enumerates the five activity classes that can hold this gate: `IDLE`, `BENCHMARK_RUN`, `JUDGE_ANALYSIS`, `PROVIDER_TEST`, `READINESS_PROBE`. This is a hard design invariant, not a tunable concurrency setting.

**Scope — what counts as an inference (DD-40).** The gate restricts inference-*class* calls only: a chat call, a per-task judge call, an embedding computation, a test inference — calls that make a model compute something. Plain network reachability handshakes, model-list fetches (`probe_health`, `list_models`), CPU-bound computation, and file I/O are **not** inferences and run unrestricted on the worker pool at any time — the readiness probe's concurrent per-provider handshakes are the canonical example of legitimate concurrency alongside a held gate.

```python
class InferenceActivityStore(Protocol):
    def try_acquire(self, activity: InferenceActivity) -> GateLease | None:
        """Atomic test-and-set under one threading.Lock. Returns a GateLease on
        success, None when already held. A failed acquire is data, not an
        exception."""
        ...

    def release(self, lease: GateLease) -> None:
        """Frees the gate ONLY when `lease` is the current holder. A stale
        lease (DD-50) is a logged no-op."""
        ...
```

**Why lease ownership matters (DD-50).** Each activity (except `BENCHMARK_RUN`, which owns its own lifecycle) has a watchdog timeout (`JUDGE_ANALYSIS`: 10 min, `PROVIDER_TEST`: 60 s, `READINESS_PROBE`: 30 s) that auto-releases a gate held too long. The watchdog **arms with the specific `GateLease` it observed and releases that exact lease** — so if the watchdog fires, a *new* activity acquires the gate, and only then does the *original* holder's late `finally release(lease)` call run, that late release is a no-op against the stale lease, and the new holder's gate is never accidentally stolen out from under it. This is the concrete bug this design prevents: without lease ownership, a slow original holder's delayed cleanup could silently release a successor's legitimate hold.

`BENCHMARK_RUN` has no watchdog: the pipeline owns its lifecycle structurally — every provider call carries a finite hard transport deadline, so the dispatcher always regains control within the attempt budget, and the user always has the hard-cancel escape (Stop/Quit, bounded by `provider.hard_cancel_max_ms`). A whole-run ceiling is deliberately rejected because a legitimate run can take many hours.

## The exactly two cross-thread locked objects

Per the standard's explicit enumeration, shared mutable state reachable from more than one thread is limited to exactly **two** objects, each guarded by one `threading.Lock` — everything else is single-owner and needs no lock:

1. **The inference-activity gate** (`InferenceActivityStore`) — acquired/released around each inference activity.
2. **The single DB writer** — one write connection guarded by one lock (DD-41). Every SQLite write acquires the lock and runs its transaction (`BEGIN IMMEDIATE`) synchronously on the calling thread; a write is committed when the call returns. During a run, run-domain writes are issued **only by the dispatcher thread** — worker units never write to the database themselves; they return data, and the dispatcher persists it.

The `AdaptiveTimeoutService` and `ProviderCircuitBreaker` are touched **only on the dispatcher thread**, which is precisely what makes their lock-free, single-owner design safe — do not add locking to them; instead, make sure any new call site that touches them is on the dispatcher thread.

## Anti-patterns — the project's own enumerated list

| Anti-pattern | Why it is wrong | Correct approach |
|---|---|---|
| Importing Qt or `asyncio` in the backend | Breaks backend independence and the swappable-runner contract | Backend is plain blocking Python behind the `TaskRunner` port |
| Spawning a raw `threading.Thread` for a work unit | Unmanaged lifetime, no clean shutdown | Submit through the `TaskRunner`; the dispatcher thread is the only sanctioned standalone thread |
| Blocking on a unit's `Future` from the GUI thread or a pool worker | Frozen UI, or pool-starvation deadlock | Only the dispatcher thread ever calls `.result()` |
| Parallel/fan-out provider calls in a run | Distorts the measured latency/throughput; overruns local providers that queue anyway | Serial execution — exactly one in-flight unit (D-R-16) |
| Touching a widget from a worker thread | Undefined Qt behavior, crashes | Return a value or publish an event; the adapter marshals to the GUI thread |
| `asyncio.Event` for cancellation | No event loop exists anywhere in this app | The `threading.Event`-backed `CancellationToken` |
| Interrupting a provider request mid-flight on a **soft** cancel | Throws away exactly the work Pause exists to preserve | Soft cancel finishes and saves the in-flight unit; only **hard** aborts mid-stream |
| A worker unit writing to the database | Breaks dispatcher write-affinity (DD-38/DD-41) | Workers return data; only the dispatcher persists, under the single writer lock |
| Completing a unit via a queued Qt signal | The dispatcher blocks in `Future.result()` with no event loop — never delivered, dispatcher hangs forever | `QRunnable.run()` sets the `Future`'s result/exception directly, inline, on the worker thread |
| Catching `BaseException` | Swallows the `ProgrammerError` type that must crash the process | Catch a specific category or leaf type |
| Missing `raise_if_cancelled()` between retry attempts | Cancellation silently ignored during backoff | Check the token inside every retry attempt's backoff loop |

## Quick checklist for any change in this area

- [ ] Does the dispatcher thread remain the *only* thread that calls `Future.result()`?
- [ ] Does every worker unit complete its `Future` directly (`set_result`/`set_exception`), never via a Qt signal?
- [ ] Does every long-running loop call `token.raise_if_cancelled()` at a safe checkpoint (before/after each unit, inside retry backoff)?
- [ ] Does a soft cancel still let the in-flight call finish and persist? Does a hard cancel still abort within `provider.hard_cancel_max_ms`?
- [ ] Does any new cross-thread mutable state actually need a lock — or does it belong as single-owner state instead (in which case, don't add a third lock)?
- [ ] Does a new inference-class call site acquire the single-inference gate, and release the *lease* it was given (not a bare "release()")?
- [ ] Does a worker ever write to the database directly? (It must not — only the dispatcher writes.)
