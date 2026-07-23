# ADR-0010 — Structure the Phase-11 composition root, entry point, and launch/quit sequencing

**Status:** accepted
**Date:** 2026-07-23
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** DD-01, DD-41, DD-53, D-R-01

## Context and problem statement

Phase 11 is the final integration phase: the composition root (`src/ollama_llm_bench/compose.py`),
the process entry point (`src/ollama_llm_bench/__main__.py`), and the headless e2e smoke tier.
Every `make_*` factory already exists; Phase 11 is wiring plus a small number of genuinely new
pieces. Four questions must be settled before the Phase-11 stories can be implemented, because the
specification either does not fix them or fixes them in a way that is internally inconsistent:

1. **When is the `QApplication` created, relative to opening the database?** `08-M_app_lifecycle.md`
   §2 orders the launch steps as logging (3) → app-data dir (4) → open DB + schema check (5) →
   seed (6) → **create `QApplication` (7)** → build the object graph (8). But every launch-abort
   path in §2–§3 (app-data permission failure EC-M-1, schema mismatch EC-M-2, corrupt DB EC-M-3,
   and the "already running" second-instance modal in `05_CONCURRENCY_GUARANTEES.md` §6) is required
   to show a **modal dialog** — which needs a live `QApplication`. Taken literally, step order 5–6
   would have to render a Qt modal on failure before the `QApplication` of step 7 exists.

1. **What is `AppHandle`?** `01_MODULE_INVENTORY.md` §7 states `build_app(*, app, loop) -> AppHandle`
   and `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` §7 shows an illustrative
   `AppHandle(window=..., pipeline=..., loop=...)`, but no document defines `AppHandle` as a typed
   structure.

1. **Where does the single-instance advisory lock live?** No helper exists anywhere in the codebase.
   Its behaviour is fully spec-defined (`05_CONCURRENCY_GUARANTEES.md` §5–§6), but no module owns it.

1. **How is the `ExportFilenameHelper` seam bridged?** The UI export gateways declare
   `compose_filename(*, run, kind: str, ext: str) -> str` (`ui/results`, `ui/resume_benchmark`), but
   the backend exposes `compose_export_filename(*, run_name, run_id, kind: ExportKind, ext) -> str`
   (`backend/csv_export`). The signatures do not match, so a bridge is needed.

`compose.py` and `__main__.py` are also not extractable as `modules:` front-matter values — the
traceability tooling only recognises `backend/…`, `adapters/…`, and `ui/…` package paths — so the
Phase-11 stories must cite the backend/adapters/ui modules they wire or extend, not the two
composition-root files themselves.

## Decision drivers

- The lifecycle contract in `08-M_app_lifecycle.md` is authoritative for *what* each launch/quit
  step does and *in what causal order*; a failure modal that cannot render is not an acceptable
  reading.
- `01_MODULE_INVENTORY.md` §7 fixes the `build_app(*, app, loop) -> AppHandle` public signature and
  the 50–200-line budget; deviating from the signature would contradict the inventory.
- CLAUDE.md architecture invariants: `msgspec.Struct(frozen=True, kw_only=True, gc=False)` for any
  cross-boundary structure; the single `TaskRunner`, single write connection, and single synchronous
  HTTP client constructed once in the composition root (D-R-01, DD-41); no `asyncio`.
- The module inventory lists no module for the single-instance lock; `backend/infra/` is the
  Qt-free home for cross-cutting infrastructure (Clock, logging, concurrency primitives, OS path
  resolver), so it is the natural owner of an OS-level advisory-lock helper.
- Adding a module the inventory does not list would fail `just trace-check`.

## Considered options

- **Option A — Follow `08-M` §2 step order literally:** open the DB and check the schema before
  constructing the `QApplication`, and render abort modals some other way (bare-Qt widget without a
  `QApplication`, or standard-error only).
- **Option B — Construct the `QApplication` early (in `__main__.py`), then run the DB/schema/seed and
  graph-wiring steps inside `build_app`:** keep the inventory's `build_app(*, app, loop)` signature;
  the pure, side-effect-free steps (argument parsing, platform detection) run before the
  `QApplication`; every step that can abort with a modal runs after it.

## Decision outcome

Chosen option: **Option B**, with the following four settlements.

1. **Launch sequencing.** `__main__.py` parses arguments and runs the platform detector (pure, no
   modal needed; an invalid argument aborts on standard error per `08-M` §2 step 1), constructs the
   single `QApplication`, installs the exception hooks (settlement 2 below), then calls
   `build_app(*, app, loop)`. `build_app` performs the remaining ordered launch steps internally —
   configure logging (3), ensure the app-data directory (4), acquire the single-instance lock (4b),
   open the one write connection with the `03_PERSISTENCE_SCHEMA.md` §2 pragmas + schema-version
   check (5), seed defaults + run the crash-recovery sweep (6), wire the object graph (8), apply the
   theme (9), and build the main window (10) — and every abort path renders its modal on the live
   `QApplication`. `app.exec()` (step 11) remains the only event loop; there is no `asyncio`/`qasync`
   loop (D-R-01). This resolves the §2-vs-modal contradiction in favour of the lifecycle contract's
   *behaviour* (every abort is a modal) over its *literal step numbering*.

1. **`AppHandle`.** `AppHandle` is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)` declared
   on `compose.py`'s public surface, carrying at minimum the main window and a **shutdown handle**
   that encapsulates the ordered shutdown of `05_CONCURRENCY_GUARANTEES.md` §8 (hard-cancel the run,
   drain the `TaskRunner` pool and join the dispatcher thread, close the one HTTP client,
   `PRAGMA wal_checkpoint(TRUNCATE)` + close the DB, release the instance lock). It is not a
   `backend/domain` DTO because it references the PySide6 main window; it lives with `build_app`.

1. **Single-instance advisory lock.** A new Qt-free helper in `backend/infra/` owns the advisory lock
   on `<app-data>/.instance.lock` (write owning PID + start timestamp, stale-PID liveness reclaim per
   `05_CONCURRENCY_GUARANTEES.md` §5). The helper returns an acquire/refuse result and a release
   handle; the "already running" / permission / schema modals are rendered by the composition root
   using Qt, never by `backend/infra` (which must stay Qt-free).

1. **Export-filename bridge.** `compose.py` defines a tiny adapter that satisfies the UI
   `compose_filename(*, run, kind, ext)` Protocol by delegating to `backend/csv_export`'s
   `compose_export_filename(*, run_name, run_id, kind: ExportKind, ext)` — deriving the run's
   effective name and id from the `BenchmarkRun` and mapping the `kind` string to the `ExportKind`
   enum. It is injected into the `ui/results` and `ui/resume_benchmark` gateways.

### Consequences

- Positive — The inventory's `build_app(*, app, loop) -> AppHandle` signature and 50–200-line budget
  are preserved; every launch-abort path can render its required modal; the single lock, HTTP client,
  and write connection are each constructed once; no module is added to the inventory (the lock lives
  in the existing `backend/infra/`).
- Negative — The database open, schema check, and seed occur slightly later than `08-M` §2's literal
  numbering (after the `QApplication` object exists, before `app.exec()`); a reader comparing code to
  §2 must consult this ADR for the reconciliation.
- Neutral — Phase-11 stories cite the backend/adapters/ui modules they wire/extend, since `compose.py`
  and `__main__.py` are not extractable `modules:` values; the new lock code is citeable via
  `backend/infra/`.

## Pros and cons of the options

### Option A — Literal `08-M` §2 order (DB before `QApplication`)

- Good — Matches the step numbering verbatim.
- Bad — A modal abort in steps 4–6 has no `QApplication` to render on, contradicting the same
  document's requirement that each abort shows a modal dialog; forces an unnatural bare-Qt or
  stderr-only failure surface that the spec does not describe.

### Option B — `QApplication` early, launch steps inside `build_app`

- Good — Preserves the inventory signature and budget; every abort modal renders; the only event loop
  is `app.exec()`.
- Bad — The DB/schema/seed steps run after the `QApplication` object is constructed, a controlled
  departure from §2's literal ordering that this ADR records.

## Links

- Spec clauses: `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations`,
  `08_Cross_Cutting/08-M_app_lifecycle.md#3-the-schema-check-and-the-no-migration-rule`,
  `08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence`,
  `08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy`,
  `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#5-file-lock-policy`,
  `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#8-shutdown-ordering-guarantees`,
  `14_Process_and_Traceability/01_MODULE_INVENTORY.md#7-the-composition-root`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root`
- Stories: STORY-076, STORY-077, STORY-078, STORY-079, STORY-080, STORY-081 (apply this decision)
