# Resource Limits

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, arch
**Last Updated:** 2026-06-06
**Cross-references:** 10_Domain_and_Data/07_FILE_LAYOUT.md, 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md, 12_Quality_and_NFRs/03_OBSERVABILITY.md, 16_Engineering_Standards/06_LOGGING_STANDARD.md, 08_Cross_Cutting/08-I_edge_cases.md

This document fixes the resource limits of Ollama LLM Bench: the bounds on database growth, log file size, in-memory buffers, and run-log retention. Every limit names the resource, the cap, what happens when the cap is reached, and the enforcement mechanism. The application is a long-lived desktop tool that may run for years against a single data directory; these limits exist so that nothing — a log, a buffer, a backup folder — can grow without bound and exhaust the user's disk or memory.

---

## Table of Contents

1. Resource-limit principles
2. Database size expectations
3. Log file limits
4. In-memory buffer caps
5. Run-log and backup retention
6. Concurrency and connection limits
7. Resource limits summary

---

## 1. Resource-limit principles

- **Every unbounded-growth source has a cap.** A log, a buffer, a backup directory, or a queue that can grow during normal operation has an explicit limit.
- **Reaching a cap degrades gracefully.** Hitting a limit triggers a defined behaviour — rotation, oldest-first pruning, rolling drop, or a clear error — never a crash and never silent data loss of something the user needs.
- **Caps are bounded; most are fixed, a few are configurable within hard bounds.** Most limits below are constants in the application. Three are exposed as user settings — the run-log panel display buffer (`ui.run_log_max_lines`) and the two app-log size limits (`logging.app_log_max_file_mb`, `logging.app_log_max_total_mb`) — because they trade off convenience (how much history to show, how much disk the diagnostic log may use) against resource use, and the right value is user- and machine-specific. Every such setting has a **hard minimum and maximum** and any out-of-range value is clamped to the nearest bound. No setting can disable a cap or raise a resource past its hard maximum, so a misconfiguration can only adjust the protection within a safe range, never remove it.
- **The user's own artifacts are not capped by the application.** Exported files, once created, are user-owned; the application does not delete them. Caps apply to what the application generates and retains on the user's behalf.

## 2. Database size expectations

The SQLite database `ollama_llm_bench.db` is the primary store. It is not artificially capped — capping it would mean refusing to record a run, which is the application's core purpose — but its growth is bounded in practice and is predictable.

| Aspect | Expectation |
|---|---|
| Per-run footprint | Dominated by the `benchmark_results` rows and their child rows. A row stores the prompts sent and the raw and sanitized responses as text; a typical run of tens of models over a couple hundred tasks is on the order of a few megabytes to low tens of megabytes. |
| Steady-state size | A user who keeps a few hundred runs has a database in the low hundreds of megabytes — well within comfortable SQLite territory. |
| Growth control | The user controls database size directly by deleting runs they no longer need; a run deletion cascades to all eight descendant tables and reclaims the space on the next checkpoint. The application provides no automatic run deletion — a benchmark run is data the user chose to create, and the application never discards it silently. |
| WAL sidecar size | The `-wal` file grows between checkpoints and is bounded by the WAL auto-checkpoint threshold; it is reclaimed on a clean shutdown. It is a normal, transient part of the on-disk state. |
| Hard ceiling | The application does not impose a hard byte ceiling on the database. SQLite's own architectural limits are far beyond any realistic desktop-benchmarking dataset and are never approached in practice. |

A disk-full condition while writing to the database surfaces as a `DatabaseDiskFullError` — a permanent error in the taxonomy of 16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md — which is reported to the user; the application does not silently drop the write.

## 3. Log file limits

The two log streams have different limit models because they have different lifetimes (see 12_Quality_and_NFRs/03_OBSERVABILITY.md and 10_Domain_and_Data/07_FILE_LAYOUT.md §8).

### 3.1 Application log

| Parameter | Value | Behaviour at the limit |
|---|---|---|
| Rotation trigger | `logging.app_log_max_file_mb` per file — default 10 MB, configurable 1–50 MB | `app.log` is rotated to `app.log.1`, each backup shifts up by one |
| Backups retained | Derived: `floor(app_log_max_total_mb / app_log_max_file_mb)` total files (current plus backups) — at the defaults, 5 backups | The oldest backup beyond the derived count is deleted |
| Total disk ceiling | `logging.app_log_max_total_mb` — default 60 MB, configurable up to a 200 MB hard maximum | A hard ceiling enforced by the derived backup count; the application log can never exceed `app_log_max_total_mb`, and that value can never exceed 200 MB |

### 3.2 Per-run benchmark log

| Parameter | Value | Behaviour at the limit |
|---|---|---|
| Per-file size | Not rotated; bounded by the run's task count | A run of a few hundred tasks produces a log well under a few megabytes |
| File count | At most 200 run logs retained | The oldest beyond 200 are deleted at startup |
| Age | A run log whose run finished more than 90 days ago is deleted at startup | Pruned by the startup cleanup |
| Event line cap per run-log file | A single run-log file holds one line per pipeline event; the number of events is bounded by the run's task count multiplied by the per-task event kinds. There is no per-line truncation of the file beyond the 4000-character redaction cap applied to each individual line. | The file is naturally bounded; no rolling drop is applied to the durable run-log file |

The run-log file always records every event at full verbosity, even when the on-screen panel is set to a lower verbosity (see EC-LOG-3 in 08_Cross_Cutting/08-I_edge_cases.md). The durable file is never the place detail is lost.

A run-log write failure (disk full, permission denied) is recorded to the application log **once**, not once per line, and a small toolbar indicator appears; the in-memory run-log panel keeps working (see EC-LOG-1).

## 4. In-memory buffer caps

Several in-memory buffers absorb high-rate producers so the UI stays responsive. Each is bounded.

| Buffer | Cap | Behaviour at the cap |
|---|---|---|
| On-screen run-log panel buffer | `ui.run_log_max_lines` most-recent events — default 100,000, configurable 1,000–500,000 (one line per event, so events and lines are 1:1) | Rolling drop — the oldest event is discarded to admit the newest. The run-log *file* is unaffected and keeps every event (see EC-PERF-3). The hard maximum keeps the panel's memory bounded by `cap × per-line memory`, each line itself bounded by the 4000-character redaction cap. |
| Database single writer (DD-41) | One write connection + one lock; no queue | Writes run synchronously on the calling thread, one at a time; nothing accumulates, so there is no buffer to bound and no back-pressure mode. |
| Logging non-blocking queue | A bounded queue | Application-log records are enqueued and drained by the background writer. Under an extreme burst the queue applies back-pressure so a logging spike cannot exhaust memory. |
| UI repaint coalescing | One pending update per surface | High-frequency progress and result events are coalesced; at most one repaint per surface is pending per frame, so the repaint queue cannot grow (see EC-PERF-3). |
| Provider readiness-probe in-flight set | One probe per provider | A second probe request for a provider with a probe already in flight is coalesced into it; concurrent duplicate probes cannot accumulate (see EC-PERF-2). |

The rolling-drop behaviour of the run-log panel buffer is deliberate: the panel is a live, scrolling view, and an unbounded panel buffer in a multi-hour run would grow the application's memory steadily. The durable record is the file; the panel is a bounded window onto it.

## 5. Run-log and backup retention

Retention limits keep the data directory from accumulating stale generated files over a long installed life.

| Generated artifact | Retention limit | Pruned when |
|---|---|---|
| Per-run log files (`logs/run/*.log`) | At most 200 files; none older than 90 days; no orphan (a log whose run was deleted) | At startup, after the recovery sweep. The age rule and the count rule are both applied; whichever removes more files governs. |
| Settings backups (`backups/settings_*.yaml`) | At most 20 files | At startup; the oldest beyond 20 are deleted |
| Exported files (`exports/*`) | Not auto-pruned | Never — exports are user-owned artifacts |
| Temp folder (`temp/*`) | Emptied entirely | At every startup, before any subsystem uses the folder |

Settings backups are capped at 20 because a backup is written before every settings import and every reset; an active user could otherwise accumulate hundreds. Twenty is enough to undo a recent mistake and small enough to never matter for disk space.

## 6. Concurrency and connection limits

| Resource | Limit |
|---|---|
| Operating-system processes | One — the application is single-process (see 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md) |
| Event loops | One Qt event loop on the GUI thread; there is no asyncio loop (D-R-01) |
| Worker thread pool (`QThreadPool` `TaskRunner`) | Fixed `maxThreadCount = 4` (DD-40); the benchmark runs serially (one in-flight unit at a time — D-R-16, no fan-out), so a run uses one worker at a time, while non-inference work (readiness handshakes, CPU aggregation) may use the remaining workers concurrently; a burst of work cannot spawn unbounded threads |
| SQLite WAL file (`-wal`) | Bounded by `journal_size_limit = 64 MB` plus PASSIVE `wal_autocheckpoint` (~4 MB) and short-lived reader transactions; the writer issues `wal_checkpoint(TRUNCATE)` at run end and clean shutdown, so the WAL never grows without bound during a long run (SPEC-039, `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §2/§2.1) |
| HTTP client instances | One synchronous client, shared across worker threads, bound to the process lifetime |
| Database connections | Exactly one write connection (guarded by the single writer lock — DD-41) plus a small fixed number of read-only connections |
| In-flight provider requests per run | Exactly one (D-R-16 serial execution); there is no concurrency setting and no fan-out of provider calls |

## 7. Resource limits summary

| Resource | Cap | Behaviour at the cap | Enforcement |
|---|---|---|---|
| Application log | ≤ `app_log_max_total_mb` (default 60 MB; configurable, hard max 200 MB), in files of `app_log_max_file_mb` (default 10 MB; range 1–50 MB) | Rotate; drop the oldest backup; total never exceeds the configured ceiling | Rotating-file handler with derived backup count |
| Per-run log file | Bounded by task count; not rotated | Naturally bounded | By design |
| Run-log file retention | ≤ 200 files, ≤ 90 days, no orphans | Oldest-first / age-based prune at startup | Startup cleanup; integration test |
| Run-log panel buffer | `ui.run_log_max_lines` events (default 100,000; range 1,000–500,000) | Rolling drop of the oldest | Bounded buffer (file keeps everything) |
| Logging queue | Bounded | Back-pressure on the submitter | Bounded queue |
| DB writer (DD-41) | One write connection + one lock | Callers serialize; a write is committed when its call returns | Synchronous write lock |
| Settings backups | ≤ 20 files | Oldest-first prune at startup | Startup cleanup |
| Temp folder | Emptied each startup | Full delete before use | Startup routine |
| Executor threads | Small fixed maximum | Requests queue on the pool | Fixed-size pool |
| Database file | No hard cap | User deletes runs to reclaim space; disk-full surfaces as a reported error | By design |
