# Concurrency Guarantees

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, arch
**Last Updated:** 2026-06-06
**Cross-references:** 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md, 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md, 12_Quality_and_NFRs/06_DATA_INTEGRITY.md, 12_Quality_and_NFRs/04_ERROR_RECOVERY.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md, 08_Cross_Cutting/08-I_edge_cases.md

This document states the concurrency guarantees Ollama LLM Bench makes as non-functional requirements: the application is single-process; the backend is synchronous and Qt-free and runs its work on a single bounded worker-thread pool owned by the adapter (a `QThreadPool`-backed `TaskRunner`); cross-thread shared state is a tiny, explicitly-locked surface; the database file is governed by a file-lock and single-writer discipline; a second instance pointed at the same data directory is detected and handled; and the GUI thread is never blocked. The implementation mechanics are fixed in 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md (the authoritative concurrency standard, per D-R-01); this document is the contract of guarantees that standard delivers, expressed so a test can assert each one.

---

## Table of Contents

1. The single-process model
2. The single execution-runner guarantee
3. The state-ownership and locked-surface guarantee
4. The worker-pool and GUI-thread guarantees
5. File-lock policy
6. Multi-instance handling
7. Worker-thread guarantees
8. Shutdown ordering guarantees
9. Concurrency guarantees summary

---

## 1. The single-process model

Ollama LLM Bench is a single-process desktop application. One launch is one operating-system process; there is no helper process, no daemon, no background service, and no fork. Every subsystem — the UI, the benchmark pipeline, persistence, logging, provider clients — lives in that one process.

The consequence is that all coordination is in-process. There is no inter-process communication, no shared-memory segment between processes, and no socket the application listens on. The only concurrency that exists is the in-process concurrency of the GUI thread plus a single bounded worker-thread pool, both described below.

## 2. The single execution-runner guarantee

There is **no event loop**. The backend is synchronous and imports neither Qt nor `asyncio`. All background work is dispatched through exactly **one** `TaskRunner` — a bounded `QThreadPool` of worker threads owned by the adapter — installed exactly once, in the composition root, before any run starts (D-R-01).

Guarantees:

- **One runner, installed once.** No backend module constructs a `QThreadPool` or spawns a raw `threading.Thread`; all fan-out goes through the injected `TaskRunner` port. An architecture test asserts the backend imports no Qt symbol and no `asyncio`.
- **The runner is swappable.** Because the backend is synchronous behind the `TaskRunner` port, a headless/CLI frontend supplies a `ThreadPoolExecutor` runner and tests supply an inline runner — against the same backend code. This is the backend-independence guarantee of `08_Cross_Cutting/08-A_architecture_principles.md`.
- **Execution is serial (D-R-16).** The benchmark runs one inference at a time — at most one in-flight unit across the whole application (`11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` §6.2). The worker pool still has a small fixed maximum, but the pipeline submits a single unit, awaits it, then submits the next; there is no fan-out and no `phase_concurrency` setting. A burst of work cannot spawn unbounded threads.
- **Two serial domains, nothing else restricted (DD-40).** The serial restrictions apply to exactly two things: the benchmark run (tasks one-by-one, stage-by-stage — D-R-16) and LLM inference globally (at most one inference-class call in flight anywhere, enforced by the single-inference gate). Non-inference network handshakes, model-list fetches, CPU-bound computations, and file I/O are unrestricted and may run concurrently on the worker pool.
- **One dispatcher thread orchestrates the run (DD-38).** The serial loop runs on a single, dedicated, adapter-owned **dispatcher thread** (`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a) — the only thread that blocks awaiting a unit's `Future`. The application has exactly three execution contexts: the GUI thread (never blocks), the dispatcher thread, and the pool workers (which never submit-and-wait on the pool). The dispatcher thread is created in the composition root and joined at shutdown.
- **One HTTP client lifetime.** Exactly one synchronous HTTP client (e.g. `httpx.Client`) is created at composition time and disposed at shutdown; provider adapters use it from worker threads.

## 3. The state-ownership and locked-surface guarantee

Application state — the contents of every store, the view-models the UI renders, the run's in-memory progress — has exactly **one owner**. Almost all of it is owned by a single thread and is therefore lock-free; only two objects are reachable from more than one thread, and each is protected by exactly one `threading.Lock`.

Guarantees:

- **Single-owner state needs no lock.** A store or view-model owned by the GUI thread is mutated only on the GUI thread; a service's in-memory state used by one run unit at a time is mutated only by that unit. No mutex is needed for single-owner state.
- **Exactly two cross-thread objects, each with one lock.** The **inference-activity gate** (`InferenceActivityStore`, `08_Cross_Cutting/08-E_interfaces_contracts.md` §13) is read on the GUI thread and acquired/released on worker threads, so `try_acquire` is an atomic test-and-set under a single lock and `state` is a locked read. The **single DB writer** — one write connection guarded by one lock (DD-41) — serializes every SQLite write; each write runs synchronously on the calling thread and is committed when the call returns. No other shared mutable object exists; introducing one without a lock is a data race and is forbidden.
- **No widget is touched off the GUI thread.** A worker result reaches the UI as a `Future` value or as a typed event that the adapter marshals onto the GUI thread via a queued signal/slot connection. A direct cross-thread widget mutation is forbidden and is an architecture-tested rule (see EC-PERF-1 in 08_Cross_Cutting/08-I_edge_cases.md).
- **The event bus marshals cross-thread delivery.** Every backend→UI message passes through the Qt-free event bus; the adapter's Qt bridge re-emits it on the GUI thread. A subscriber always runs on the GUI thread regardless of which worker thread originated the message.
- **Database writes are serialised (DD-41).** The database is the one piece of durable shared state. Every write goes through the single DB writer — exactly one write connection guarded by one `threading.Lock`; the transaction (`BEGIN IMMEDIATE`) runs synchronously on the calling thread and is committed when the call returns. There is no write queue. During a run, run-domain writes are issued only by the dispatcher thread (DD-38); readers use separate read-only connections. Detailed in 12_Quality_and_NFRs/06_DATA_INTEGRITY.md §3 and matches EC-PERSIST-3.

## 4. The worker-pool and GUI-thread guarantees

Keeping all blocking work on worker threads and the GUI thread free is the foundation of the responsiveness model. The guarantees:

- **The GUI thread never blocks.** Synchronous HTTP, `sleep`, and file I/O run only on worker threads via the `TaskRunner`. The GUI thread handles UI events and marshalled results only; a blocking backend call directly on the GUI thread is forbidden and architecture-tested.
- **Execution is serial.** A run submits **one** unit at a time and awaits it before submitting the next (D-R-16); there is never more than one in-flight unit **of the run** (non-inference work — readiness handshakes, UI-initiated aggregation — may run concurrently on the pool, DD-40). A unit's typed failure is captured on its `Future` and re-raised on the dispatcher thread, so no failure is silently lost.
- **Cancellation is cooperative, two-level, and observable (DD-39).** A run is cancelled through one explicit `CancellationToken` (set on the GUI thread, observed on workers) checked at safe checkpoints. A **pause** (soft cancel) never abandons an in-flight unit of work mid-flight — the unit finishes and persists, then the dispatcher stops submitting. A **stop or shutdown** (hard cancel) aborts the in-flight unit promptly (chunk-boundary poll + abort hook, bounded by `provider.hard_cancel_max_ms`); nothing partial is persisted — the unit's row stays `PENDING`. Both paths give the clean-resumable-checkpoint guarantee that error recovery and data integrity depend on: Pause checkpoints by finishing the unit, Stop by discarding it whole.
- **Uncaught worker exceptions are not lost.** A programmer-error raised on a worker reaches the thread excepthook and the terminal crash path; every other uncaught exception is redacted and logged.
- **The live inference-progress event is coalesced at ≥ 1 Hz regardless of context.** Four user-visible LLM-call surfaces share a single emitter helper — the benchmark pipeline per-task main inference (`context=BENCHMARK_TASK`), the benchmark pipeline per-task judge call (`context=BENCHMARK_JUDGE`), the Run Analysis Service (`context=RUN_ANALYSIS`), and the `LLMClient.test_inference` flow (`context=PROVIDER_TEST`) — and each invocation emits `_inference_progress` (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.3, `08_Cross_Cutting/08-Q_event_payload_schemas.md` §4.1a) from the synchronous `emit_progress_during(...)` helper running on the call's own worker thread — **no ticker thread, no `QTimer`, no raw thread** (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9). The cadence is **chunk-driven**: the client's streaming read uses a sub-second per-read socket timeout, so during provider silence the iterator yields a heartbeat chunk (`content == ""`), waking the helper; it emits a snapshot whenever ≥ 1000 ms have elapsed since the last emission. Each emission carries the latest `(elapsed_ms, tokens_received, first_token_received)` snapshot plus the `InferenceContext` discriminator; intermediate snapshots are not produced. The cadence is **at least once per second** for the duration of every in-flight call and **at most once per second** per call by construction (one emission per ≥1000 ms window). An additional immediate-emit happens the instant the first content-bearing chunk arrives, so subscribers can transition from waiting to receiving sub-states without waiting for the next tick. Emission stops when the `chat_stream` iterator ends — on success, on failure, or on cancellation — because the helper returns; no event fires for a call that is no longer in flight (no background timer survives the call). The `InferenceActivityStore` gate (`08_Cross_Cutting/08-E_interfaces_contracts.md` §13) guarantees at most one inference-using activity class is in flight at any moment, so the four context streams **never overlap in time on the bus**; if a defensive race were to deliver two contexts to one subscriber, each event is still dispatched to its filtered subscriber (Progress widget Current-task controller for `BENCHMARK_TASK` + `BENCHMARK_JUDGE`, Generate Analysis dialog for `RUN_ANALYSIS`, Provider Edit inference-test panel for `PROVIDER_TEST`) and the others ignore it. Readiness probes never emit this event — they are invisible background checks (`11_Services_and_Algorithms/09_READINESS_PROBE.md`).

## 5. File-lock policy

The application data directory and, in particular, the SQLite database, must not be written by two processes at once. The file-lock policy:

- **A single-instance lock file.** On startup, after resolving the application data directory, the application acquires an exclusive advisory lock on a dedicated lock file inside `<app-data>/` (for example `<app-data>/.instance.lock`). The lock is held for the whole process lifetime and released — or, on a crash, dropped by the operating system — at exit.
- **The lock is the multi-instance gate.** Acquiring the lock succeeds for the first instance and fails for any later instance pointed at the same data directory. Section 6 specifies what a failed acquisition does.
- **SQLite's own locking remains in force.** Independently of the application lock, SQLite in WAL mode applies its own file locking per connection. The `busy_timeout` pragma (5000 ms) absorbs the brief contention windows between the application's own connections. The application lock prevents two *processes*; SQLite's locking coordinates connections within the one permitted process.
- **The WAL sidecar files are never hand-managed.** The `-wal` and `-shm` files are part of the database's locked state. They are never deleted or copied by the application while the database is open (see 10_Domain_and_Data/07_FILE_LAYOUT.md §3).
- **A stale lock from a crash is recoverable (SPEC-035).** The lock file records the **owning PID** (and a start timestamp). An advisory lock held by a dead process is released by the OS when it is reaped, but reaping/lock-visibility can lag (especially after `os._exit`); so on an apparently-held lock the application also **checks the recorded PID for liveness** — if no live process owns it, the lock is treated as stale and re-acquired rather than refusing to start. The application data directory **must be on a local filesystem**: advisory-lock semantics on a network filesystem are unreliable and are not supported. With these two guards a crash never leaves the directory permanently locked, and a fast relaunch does not spuriously report "already running".

## 6. Multi-instance handling

The application is single-instance **per data directory**. The intended and supported model is one running instance writing one application data directory.

When a second instance launches and finds the data directory's lock already held:

- The second instance does **not** open the database, does **not** start its pipeline, and does **not** mutate any file in the data directory.
- It shows a clear modal dialog stating that Ollama LLM Bench is already running and that a second copy cannot use the same data directory at the same time. It then exits.
- Where the operating system's window manager supports it, the second instance additionally asks the first instance to bring its main window to the front, so the user sees the running copy rather than nothing. This is a convenience; the binding behaviour is that the second instance refuses to run and exits cleanly.

Two instances pointed at *different* data directories are not in conflict and both run normally — each holds its own directory's lock. This is an unusual configuration but is not prevented, because the file-lock guarantee is per directory and is fully satisfied.

## 7. Worker-thread guarantees

Real parallelism exists only in the single bounded worker-thread pool behind the `TaskRunner`, used for both I/O-bound work (provider/judge/embedding calls) and CPU-bound pure functions (chart aggregation, export assembly).

Guarantees:

- **CPU-bound functions handed to a worker are pure.** A pure function dispatched to the pool takes its inputs as arguments, returns a value, touches no Qt object, and touches no shared mutable application state. This is an architecture-tested contract.
- **No Qt object is reachable from a worker.** A widget is never passed into a worker callable; a worker computes and returns, and the result is marshalled back on the GUI thread. (I/O work units do reach backend services and the locked gate/DB-writer surface of Section 3, but never a Qt object.)
- **No raw threads for state-bearing work.** State-bearing work is never moved to a hand-spawned `threading.Thread`. The pool's threads are owned by the adapter's `QThreadPool` and shut down cleanly with it.
- **The pool size is bounded.** The pool's maximum worker count is fixed at **4** (`maxThreadCount = 4`, DD-40), so a burst of work cannot spawn an unbounded number of threads.

## 8. Shutdown ordering guarantees

A clean shutdown follows a fixed order so no work is abandoned and no file is left half-written:

1. If a run is in progress, a **hard** cancellation is requested through the `CancellationToken` (DD-39); the in-flight unit aborts promptly (≤ `provider.hard_cancel_max_ms`, persisting nothing — its row stays `PENDING`), then the dispatcher halts. The whole stop is bounded by `app.shutdown_timeout_ms` — only if even the hard-abort path wedges does the application force-quit via `os._exit`, and the next launch's recovery sweep resets any non-terminal row (see 12_Quality_and_NFRs/04_ERROR_RECOVERY.md and EC-RUN-4).
2. The `TaskRunner`'s `QThreadPool` is drained (`QThreadPool.waitForDone(timeout)`), so no worker thread outlives the shutdown, and the pipeline dispatcher thread (DD-38) is joined.
3. The single synchronous HTTP client is closed.
4. The database connection is checkpointed and closed, releasing the `-wal` and `-shm` files.
5. The application data directory's instance lock is released.
6. The process exits.

Force-quit (`os._exit`) is **deliberately minimal**: it skips the HTTP-client close, the database checkpoint/close, and the instance-lock release, because doing work on a wedged process risks hanging or crashing the exit itself. Each skipped step is individually safe to skip: the database remains consistent at its last committed transaction and SQLite performs **automatic WAL recovery on the next open** — finding `-wal`/`-shm` files after a force-quit is expected, not a defect; the operating system releases the advisory instance lock at process death (the data directory is local, so this is immediate); the abandoned in-flight HTTP call dies with the process; and the next launch's recovery sweep resets any non-terminal row. Before exiting, the application makes one best-effort log write naming the step that wedged.

## 9. Concurrency guarantees summary

| Guarantee | Statement | Enforcement |
|---|---|---|
| Single process | One launch is one process; no helper process or daemon | By construction |
| No event loop / single runner | No `asyncio`; exactly one `TaskRunner` (bounded `QThreadPool`), installed once in the composition root | Architecture test (no asyncio/qasync import; backend imports no Qt) |
| Backend independence | The synchronous backend runs headless behind the `TaskRunner` port; the runner is swappable | Architecture test; headless run test |
| State ownership + locked surface | All state is single-owner except the inference gate and the DB writer, each with one lock | Architecture test on cross-thread widget access; gate concurrency test |
| Serialised DB writes (DD-41) | All writes run synchronously on the calling thread through one write connection + one lock; committed when the call returns; causally ordered per caller | Integration test; see 06_DATA_INTEGRITY.md |
| GUI thread never blocks | No synchronous sleep, HTTP, or hot-path file I/O on the GUI thread | Architecture test in 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md |
| Serial execution (D-R-16) | At most one inference unit in flight across the whole application; tasks and stages run one at a time, in order | Concurrency-model test |
| Two serial domains (DD-40) | Only the benchmark run and global inference are serial; non-inference handshakes, CPU work, and I/O run concurrently on the pool (`maxThreadCount = 4`) | Readiness-probe tests RP-18/RP-19; architecture test |
| Dispatcher-thread affinity (DD-38) | The run loop, breaker/adaptive-timeout access, result persistence, and run-domain event emission happen only on the dedicated dispatcher thread; only it blocks on a unit's `Future`; it is joined at shutdown | Architecture test (16_Engineering_Standards/04_CONCURRENCY_STANDARD.md §4a) |
| Clean cancellation (two-level, DD-39) | Pause (soft) finishes and saves the in-flight unit; Stop/Shutdown (hard) abort it within `provider.hard_cancel_max_ms` persisting nothing; a checkpoint is always consistent either way | Concurrency-standard tests |
| File-lock per data directory | An exclusive lock on the data directory is held for the process lifetime | Integration test |
| Single instance per data directory | A second instance on the same directory refuses to run and exits cleanly | Integration test |
| Pure CPU workers | CPU-bound functions on a worker are pure; no Qt object is reachable from a worker | Architecture test |
| Ordered shutdown | Shutdown stops the run, drains the pool, closes the HTTP client and database, releases the lock | Integration test |
| `_inference_progress` cadence | The event is emitted at ≥ 1 Hz (chunk-driven; one emission per ≥1000 ms window, no ticker thread) for the duration of every `chat_stream` call from any of four contexts (`BENCHMARK_TASK`, `BENCHMARK_JUDGE`, `RUN_ANALYSIS`, `PROVIDER_TEST`), is cancelled when the call ends, and is never emitted by readiness probes | Unit + integration test on the shared emitter helper |
