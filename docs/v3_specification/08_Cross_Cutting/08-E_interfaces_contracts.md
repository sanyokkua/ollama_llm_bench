# Interfaces and Service Contracts

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`, `08_Cross_Cutting/08-A_architecture_principles.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-C_settings_hierarchy.md`, `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`

This document is the abstract service-contract layer of the backend. It defines every backend service as a Python `typing.Protocol` with fully typed method signatures — arguments, return types, and the error categories each method may raise — but no implementation bodies. Every data type named here (every DTO, enum, type alias, and constrained type) is defined authoritatively in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; this document references those names and never redefines them. The contracts here, together with the layered dependency rule, the error model, and the threading contract, are the binding boundary between the UI layer and the backend.

---

## Table of Contents

1. Scope and conventions
2. The layered dependency rule
3. The error model
4. The threading contract
5. Clock
6. Event Bus
7. Persistence Stores (§7.1 RunsStore, §7.2 TasksStore, §7.3 ResultsStore, §7.4 ProvidersStore, §7.4a Embedding selection — no store, §7.5 ModelCapabilitiesStore, §7.6 AppSettingsStore)
7b. UI Adapter Gateways (D-R-06) (§7b.1 MainWindowGateway, §7b.2 NewBenchmarkGateway, §7b.3 ResumeGateway, §7b.4 ProgressGateway, §7b.5 ResultGateway, §7b.6 SettingsGateway, §7b.7 TaskEditorGateway)
8. Settings Service (§8 SettingsService, §8a RunSnapshotBuilder)
9. Provider Registry
10. LLM Client
11. Benchmark Pipeline (Flow API)
12. Readiness Service
13. Inference Activity Store
14. Task File Loader
15. Task File Validator
16. YAML Formatter
17. Adaptive Timeout Service
18. Provider Circuit Breaker
19. Workspace Controller
20. Notification Service
21. OS Adapter Protocols (§21a NativePickers, §21b Clipboard, §21c FileSystemActions)
22. Redaction module
23. The application context
24. Where each contract is consumed

---

## 1. Scope and conventions

A **service contract** is a `typing.Protocol` class. A Protocol declares method names and signatures; it carries no state and no logic. A concrete implementation satisfies a Protocol structurally — it does not subclass it. This keeps the backend replaceable and lets every service be substituted by a test double.

Conventions used throughout this document:

- **Protocol declaration.** Every contract is `class Name(Protocol): ...`. Methods have full type annotations and an `...` body. No method here has an implementation.
- **DTO references.** Every record, enum, type alias, and constrained type named in a signature is defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. This document imports those names conceptually and never restates their fields. When a method needs a name not in that catalog, the name is a small, contract-local type and is declared inline in the section that introduces it.
- **Optionality.** A parameter or return value typed `X | None` may be absent; one typed `X` is always present.
- **Threading marker.** Methods are synchronous (`def`). A method marked *blocking* (network/pipeline work) may block and is invoked only on a `TaskRunner` worker thread; a method marked *fast-synchronous* returns quickly and may be called from the GUI thread. Section 4 states the full rule.
- **Error categories.** Each method documents the error categories it may raise. The categories are defined in Section 3 and are referenced by name. A method whose contract names no category does not raise to its caller for an expected failure; it returns a value or a status instead.
- **No implementation code.** This document defines structure, types, and behaviour at the contract level. Algorithms live in `11_Services_and_Algorithms/`.

---

## 2. The layered dependency rule

The full architectural rules are normative in `08_Cross_Cutting/08-A_architecture_principles.md`. This section states the dependency graph those rules enforce, because every contract below belongs to one layer of it.

```
+================ UI LAYER (PySide6) ==============================+
|  Views / Widgets         -- UI primitives only                   |
|        v                                                         |
|  Controllers / ViewModels -- orchestrate views and adapters      |
+================|=================================================+
                 v
+================ ADAPTER LAYER (frontend-side Qt glue) ===========+
|  Adapters                -- view-model conversion;               |
|                             command translation;                 |
|                             cross-thread marshalling             |
+================|=================================================+
                 v
+================ BACKEND LAYER (frontend-agnostic, headless) =====+
|  Services (this document) -- business logic; no UI imports       |
|        v                                                         |
|  Domain models + Data     -- pure value types + data access      |
+==================================================================+
```

Dependency rules:

- A View may depend on its Controller or ViewModel and on UI primitives.
- A Controller or ViewModel may depend on Adapter interfaces.
- An Adapter may depend on Service Protocols (this document) and on domain models.
- A Service may depend on other Service Protocols and on domain models.
- Domain models must not depend on anything mutable.
- Views must not depend on Services directly.
- Services must not import any UI primitive or anything in the UI layer.

The Adapter layer may be a thin pass-through in trivial cases, but the boundary itself is non-negotiable: the UI and the backend hold no dependency on each other in either direction, and the backend is never modified for a frontend's sake. The adapter is frontend-side glue by design — it is where every Qt-specific accommodation lives, and it is rewritten together with the UI if the toolkit ever changes. Every Protocol in this document is a **backend-layer** contract. The Adapter layer consumes them; the UI layer never imports them.

---

## 3. The error model

The application has one error taxonomy. Every service that raises does so with a category from this taxonomy. The full hierarchy and its leaf classes are specified in `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`; this section names the categories the contracts below reference.

| Category | Meaning | Typical raisers |
|---|---|---|
| `ConfigurationError` | A required configuration value is missing, malformed, or contradictory (for example an api-key env-var name whose variable is unset/empty, or a provider with no base URL). | Settings Service, Provider Registry |
| `PersistenceError` | A durable-storage operation failed (database locked beyond the busy timeout, constraint violation, corrupt file). | the six persistence stores (RunsStore, TasksStore, ResultsStore, ProvidersStore, ModelCapabilitiesStore, AppSettingsStore) |
| `ProviderError` | A provider rejected a request, was unreachable, or returned an unusable response. Each provider adapter wraps the provider SDK's own exceptions into this category. | LLM Client, Provider Registry |
| `TimeoutError` | An operation exceeded its time budget. Distinct from `ProviderError` so the pipeline can classify a result as `FAILED_TIMEOUT` rather than `FAILED_PROVIDER`. | LLM Client |
| `TaskFileError` | A task file could not be read or parsed at all (file missing, not valid YAML, wrong root shape). Per-task content problems are diagnostics, not exceptions — see the Task File Validator. | YAML Formatter, Task File Loader (only for unreadable files) |
| `ValidationError` | A domain value violated a declared constraint at construction time. This is a programmer error, never an expected runtime condition. | Domain model constructors |
| `OsAdapterError` | An operating-system integration call failed (clipboard unavailable, file manager could not be launched). | NativePickers, Clipboard, FileSystemActions |

Per-layer error policy:

| Layer | Policy |
|---|---|
| UI primitives | Never surface a raw exception. Show an inline validation strip or call the Notification Service. |
| Controllers / Adapters | Catch service exceptions, translate them into user-facing messages. |
| Services | May raise only the categories named in their contract. |
| Benchmark Pipeline | Never raises to its caller. It captures every failure into `BenchmarkResult.error_kind`, `BenchmarkResult.error_message`, and the result's `ResultStatus`; a catastrophic failure sets `RunStatus.FAILED`. |
| Domain model constructors | Raise `ValidationError` on an invalid argument (programmer error). |

Each provider adapter is responsible for the boundary translation: it catches whatever exception type the underlying provider SDK raises (an Anthropic SDK error, a Gemini `APIError`, an untyped `httpx` failure from an OpenAI-compatible endpoint, and so on) and re-raises it as `ProviderError` or `TimeoutError`. No provider SDK exception type ever escapes the LLM Client.

---

## 4. The threading contract

The backend is **synchronous and Qt-free**; there is no `asyncio` event loop. Long-running and blocking backend work runs on `QThreadPool` worker threads dispatched by the adapter-owned `TaskRunner`; the Qt GUI thread runs only UI events and marshalled results (see `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`, the authoritative standard per D-R-01). Every contract below obeys these rules:

- **Three execution contexts: the GUI thread, the pipeline dispatcher thread, and worker threads (DD-38).** UI controllers, the event-bus Qt bridge, and gating reads run on the Qt GUI thread. The benchmark pipeline's run loop runs on the single dedicated **dispatcher thread** (`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a) — the only thread that blocks awaiting a unit's `Future`. Provider/judge/embedding calls and CPU-bound aggregation run as blocking units on worker threads via the `TaskRunner`.
- **"Blocking" methods run on a worker (or on the dispatcher thread).** A method marked *blocking* (network calls, the pipeline run loop) is an ordinary synchronous `def` that may block; it is only ever invoked on a `TaskRunner` worker thread — or, for the pipeline run loop itself, on the dispatcher thread — never directly on the GUI thread. A method marked *fast-synchronous* returns quickly (memory or a fast SQLite read/write under WAL) and may be called from either context.
- **CPU-bound work runs on a worker too.** Embedding math, cosine computation, chart aggregation, and CSV generation are submitted to the same `TaskRunner` as I/O work; each is a pure function whose result is read from its `Future`.
- **Cancellation is cooperative.** Every long-running operation — a pipeline run above all — polls the `CancellationToken` (backed by `threading.Event`) at safe checkpoints. `stop()` and `pause()` set the token; they do not kill a worker mid-statement.
- **Cross-thread updates are marshalled by the adapter layer.** A worker thread never touches a Qt widget. It reports progress by publishing a typed Event Bus event; the adapter's Qt bridge re-emits it onto the GUI thread via a queued signal/slot connection, and the adapter converts the payload into a view-model update.
- **The Event Bus is the only cross-thread notification channel.** No service calls a UI object directly. The bus `emit` is safe to call from any thread; subscription handlers always run on the GUI thread.
- **Shared mutable cross-thread state is the gate and the DB writer only**, each protected by one `threading.Lock` (§13 and `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` §3). All other state is single-owner and lock-free.

Each method's own threading rule is restated in its contract section below.

---

## 5. Clock

A small, injectable time source. Making time a service lets tests run with a controllable clock and keeps every timestamp consistent.

```python
from typing import Protocol


class Clock(Protocol):
    """Injectable time source. Synchronous; never blocks; never raises."""

    def now_utc(self) -> Iso8601Utc:
        """Return the current instant as an ISO-8601 UTC string."""
        ...

    def monotonic_ms(self) -> int:
        """Return a monotonic millisecond counter for measuring durations.

        The value has no calendar meaning; only differences are meaningful.
        """
        ...
```

- **Threading.** Synchronous; callable from any thread.
- **Errors.** None.
- **DTOs.** `Iso8601Utc` (type alias) — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §2.

---

## 6. Event Bus

The publish/subscribe channel for every cross-component message. The full signal catalog and every payload Struct is in `08_Cross_Cutting/08-J_event_bus_catalog.md`; this contract defines only the bus surface.

```python
from typing import Protocol, Callable


class Subscription(Protocol):
    """A handle to one active subscription."""

    def cancel(self) -> None:
        """Cancel the subscription. Idempotent; safe to call after the owner is gone."""
        ...


class EventBus(Protocol):
    """The application-wide pub/sub channel."""

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Register `handler` for `signal_name`.

        When `owner` is given, the subscription auto-cancels when the owner is
        destroyed, so widgets never leak handlers. The handler always runs on
        the main thread. Returns a `Subscription` for explicit early cancel.
        """
        ...

    def emit(self, signal_name: str, payload: object) -> None:
        """Publish `payload` on `signal_name`.

        Safe to call from any thread. Delivery is queued onto the main thread;
        handlers run there. `payload` is one of the frozen event Structs from
        the event-bus catalog.
        """
        ...
```

- **Threading.** `emit` is callable from any thread and is the only cross-thread channel. `subscribe` is called on the main thread; handlers run on the main thread.
- **Errors.** The bus does not raise to the emitter. An exception thrown inside a handler is caught, logged, and isolated so one faulty subscriber cannot break delivery to others.
- **DTOs.** Payloads are the event Structs catalogued in `08_Cross_Cutting/08-J_event_bus_catalog.md`. `signal_name` values are drawn from that catalog.

---

## 7. Persistence Stores

The durable-state surface is split into **six focused Protocols**, one per aggregate root (RunsStore, TasksStore, ResultsStore, ProvidersStore, ModelCapabilitiesStore, AppSettingsStore — there is no `EmbeddingConfigStore`, D-R-13). There is no umbrella `Protocol` over the six: each store is constructed, injected, and consumed in its own right. All six share the same operating envelope so the rules are not lost in the split:

- **Single database.** Every store reads and writes the same SQLite database under the WAL configuration. The schema is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` and summarised in `08_Cross_Cutting/08-O_persistence_schema.md`.
- **Threading.** Fast-synchronous. SQLite under WAL is fast enough that these reads/writes return quickly. During a run, run-domain writes (result rows, the run header) are issued only by the dispatcher thread (DD-38/DD-41) — worker units never write. All writes go through the single DB writer — one write connection guarded by one lock — and run synchronously on the calling thread (`BEGIN IMMEDIATE`); a write is committed when the call returns. Reads use separate read-only connections under WAL.
- **Errors.** Every method raises `PersistenceError` on a storage failure. A lookup method (`get_run`, `get`, `get_by_name`, `get_setting`, `get_schema_version`) raises `PersistenceError` when the underlying row is missing where the contract requires one, and returns `None` where the contract explicitly permits absence. A duplicate-name insert / update on `ProvidersStore` raises `PersistenceError` (the friendly-error path is the caller's `get_by_name` pre-check).
- **Transactional guarantees.** Where a method spans more than one row or one table, the work happens in one transaction; the per-table rules are in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`.
- **Co-construction.** All six stores are constructed by the composition root over the same opened database connection (or connection pool, per `08_Cross_Cutting/08-O_persistence_schema.md`); they do not own each other.

Every record, patch, and identifier named below is defined authoritatively in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7.1 RunsStore

```python
from typing import Protocol


class RunsStore(Protocol):
    """Run headers and their three frozen snapshot child tables."""

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Insert a run header and its three frozen snapshot child tables
        (models, providers, settings) in one transaction. Return the new run id.
        Raises PersistenceError.
        """
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one run, fully assembled with its snapshot collections.
        Raises PersistenceError if the run does not exist.
        """
        ...

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first. Raises PersistenceError."""
        ...

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a partial update to a run header (status, counters, analysis,
        timestamps). Identity columns and the snapshot tables are immutable.
        Raises PersistenceError.
        """
        ...

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        """Set or clear the user-facing run name. `None` restores the generated
        name. Raises PersistenceError.
        """
        ...

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run; the cascade removes every dependent row.
        Raises PersistenceError.
        """
        ...
```

- **DTOs.** `BenchmarkRun`, `RunStatusPatch`, `RunId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7.2 TasksStore

```python
from typing import Protocol


class TasksStore(Protocol):
    """The per-run frozen task snapshot."""

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot and its keyword-term child rows
        in one transaction. Raises PersistenceError.
        """
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks in task order. Raises PersistenceError."""
        ...
```

- **DTOs.** `BenchmarkTask`, `RunId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7.3 ResultsStore

```python
from typing import Protocol


class ResultsStore(Protocol):
    """Per-task results, the resume/retry sets, and the crash-recovery sweep."""

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert the initial result rows for a run in one transaction.
        Raises PersistenceError.
        """
        ...

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result. When the patch carries `terms`
        or `attempts`, the child rows for that result are replaced wholesale.
        Identity columns are immutable. Raises PersistenceError.
        """
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return every result of a run, each assembled with its term and
        attempt child rows. Raises PersistenceError.

        **Bound.** A full assembly of every result plus its child rows can reach
        tens of MB for a large sweep; this eager call must therefore run on a
        `TaskRunner` worker thread (off the GUI thread), never synchronously on the
        UI loop. Above an implementation-defined row-count threshold (default 50k
        result rows) callers must use the paginated / streaming read path instead of
        materialising the whole set in memory. The UI model/view fetches visible rows
        on demand rather than holding the full assembly (see R-010).
        """
        ...

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume: rows in `PENDING`
        and rows in a retryable terminal-failure status. Raises PersistenceError.
        """
        ...

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to `ResultStatus.PENDING`,
        in one transaction. For each row, `status` is set to `PENDING` and the
        prior outcome is cleared: `verdict`, the per-phase verdicts
        (`keyword_verdict`, `cosine_verdict`, `judge_verdict`), `cosine_similarity`,
        `resolution_layer`, `error_kind`, `error_message`, the timing and token
        columns, and the response columns are nulled, and the row's term and
        attempt child rows are removed. Identity columns are untouched. A row
        already in `PENDING` is left unchanged. Return the number of rows reset.
        The Retry use case calls `reset_results_for_retry` (below) so a judge-only
        failure is not forced to re-run inference; crash recovery uses
        `recover_in_flight_results`. Raises PersistenceError.
        """
        ...

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Reset the named results for retry **from the failed stage** (DD-66),
        in one transaction. The resume point is derived per row from its status:

        - `FAILED_JUDGE_TIMEOUT`, or `ERRORED` whose `sanitized_response` is
          non-null (inference succeeded; the failure was in grading): set
          `status = AWAITING_JUDGE_CHECK`; clear only the judge outputs
          (`judge_verdict`, `judge_reasoning`, `judge_time_ms`,
          `judge_completion_tokens`), the combined `verdict`, `resolution_layer`,
          `error_kind`, `error_message`. **Preserve** `raw_response`,
          `sanitized_response`, the prompt columns, the timing/token metrics,
          `keyword_verdict`, `cosine_similarity`, `cosine_verdict`, and the term
          child rows. The pipeline resumes the row at the judge stage and
          re-judges the preserved `sanitized_response` — the same text, so the
          new verdict stays consistent with the recorded keyword/cosine outcomes.
        - Every other retryable status (`FAILED_INFERENCE`, `FAILED_PROVIDER`,
          `FAILED_TIMEOUT`, `ERRORED` with no response, or an in-pipeline
          `RUNNING_INFERENCE`/`AWAITING_*` row): full reset to `PENDING`, exactly
          as `reset_results` (the failed/indeterminate stage is inference, so the
          whole task re-runs).

        A row already in `PENDING` is left unchanged. Returns the number reset.
        (A crash after this reset but before the judge re-runs is safe: the
        startup sweep resets any `AWAITING_*` row to `PENDING`, falling back to a
        whole-task re-run.) Raises PersistenceError.
        """
        ...

    def recover_in_flight_results(self) -> int:
        """Run the crash-recovery sweep: reset every result left in a
        non-terminal in-flight status back to `PENDING` and clear its in-flight
        columns and child rows. Return the number of rows reset.
        See 08_Cross_Cutting/08-O_persistence_schema.md. Raises PersistenceError.
        """
        ...
```

- **DTOs.** `BenchmarkResult`, `ResultPatch`, `ResultId`, `RunId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7.4 ProvidersStore

The `ProvidersStore` is the durable surface for the provider catalog. Per DD-33 the store **owns identifier generation**: `add(draft)` accepts a `ProviderConfigDraft` (the field set of `ProviderConfig` minus the `provider_id`), generates a fresh UUID4 textual representation, commits the row inside one transaction, and returns the new `ProviderId`. The user never types the identifier. The `UNIQUE (name)` constraint on `providers.name` enforces global uniqueness of the user-entered display label; `get_by_name` is the duplicate-name lookup the Provider Edit sub-dialog uses for live validation and the importer uses for per-row duplicate detection (so the user sees a friendly error before the DB constraint fires).

```python
from typing import Protocol


class ProvidersStore(Protocol):
    """The provider catalog. Owns provider_id generation (DD-33)."""

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Return every configured provider in display order, each with its
        manual model list. Raises PersistenceError.
        """
        ...

    def get_by_name(self, name: str) -> ProviderConfig | None:
        """Return the provider whose `name` matches `name`, or `None` when no
        provider in the catalog has that name. Used by the Provider Edit
        sub-dialog and the importer to pre-check duplicate names before
        attempting `add` / `update`. Raises PersistenceError on a storage
        failure.
        """
        ...

    def add(self, draft: ProviderConfigDraft) -> ProviderId:
        """Insert a new provider. The store generates the `provider_id` UUID4
        on insert and returns it. The caller MUST pre-check duplicate names
        via `get_by_name(draft.name)`; if a row with that name already exists
        the store still raises a PersistenceError (the UNIQUE constraint is the
        backstop) so the pre-check is the friendly-error path, not the only
        path. Raises PersistenceError on duplicate name or storage failure.
        """
        ...

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        """Update an existing provider. The `provider_id` is immutable — the
        method updates every other column (including `name`) on the row whose
        `provider_id` matches. The caller MUST pre-check that
        `config.name == provider_with(provider_id).name` OR
        `get_by_name(config.name)` is `None`, so a friendly duplicate-name
        error reaches the dialog before the constraint fires. Raises
        PersistenceError when no such row exists, on duplicate name, or on
        storage failure.
        """
        ...

    def delete(self, provider_id: ProviderId) -> None:
        """Delete the provider with the given internal id. Cascades to its
        `provider_models` and `model_capabilities` rows. Run-history rows are
        unaffected (the `provider_id` link is logical, not a FK; the run keeps
        its snapshot per DD-33). Raises PersistenceError on storage failure.
        """
        ...

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically. Used by the Settings
        dialog's Save flow (which collects the full working set) and by the
        import flow. The implementation is responsible for honouring the
        UNIQUE-on-name invariant; the caller MUST present an internally
        non-duplicate set. Raises PersistenceError on duplicate name or
        storage failure.
        """
        ...
```

- **DTOs.** `ProviderConfig`, `ProviderConfigDraft`, `ProviderId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §5.1, §2. The `add(draft) -> ProviderId` signature is the canonical insertion pattern; both the dialog (for a new provider) and the importer (for each fresh row) use it. `replace_providers` is used only by the Settings Save and the full-replace import path; for those paths the caller assembles a tuple of `ProviderConfig` values whose `provider_id` is either a previously-stored UUID4 (for an unchanged or edited row) or a fresh UUID4 generated for a newly-added row.

### 7.4a Embedding selection — no dedicated store (D-R-13)

There is **no `EmbeddingConfigStore`** and no embedding-config catalog. Per D-R-13 the embedding feature is a single selected `(provider, embedding model)` stored as two `app_settings` keys — `embedding.selected_provider_name` (the stable provider name) and `embedding.selected_model_name` — read and written through **`AppSettingsStore`** (§7.6) like any other setting. Outside a run the pair is read live (Settings dialog, capability probe — `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` §6.6a); at run start it is resolved once and frozen into the run snapshot, and the pipeline thereafter reads only the frozen pair (§6.2 of the same document). The application therefore has the **six** persistence stores enumerated in §3 and the composition-root section; no seventh store exists. The per-provider embedding-model list shown in the Settings dialog is discovered dynamically and never persisted.

### 7.5 ModelCapabilitiesStore

```python
from typing import Protocol


class ModelCapabilitiesStore(Protocol):
    """Cached per-(provider, model) capability records."""

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return the cached capability records for one model.
        Raises PersistenceError.
        """
        ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Insert or update one capability record. Raises PersistenceError."""
        ...
```

- **DTOs.** `ModelCapabilityRecord`, `ProviderId`, `ModelName` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7.6 AppSettingsStore

```python
from typing import Protocol


class AppSettingsStore(Protocol):
    """The user-saved settings layer and the schema-version row."""

    def get_setting(self, key: SettingKey) -> str | None:
        """Return one user-saved setting value, or `None` if the user has not
        overridden the default. Raises PersistenceError.
        """
        ...

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Insert or update settings rows atomically. Raises PersistenceError."""
        ...

    def list_settings(self) -> dict[SettingKey, str]:
        """Return every user-saved setting. Raises PersistenceError."""
        ...

    def get_schema_version(self) -> int:
        """Return the schema version recorded in `app_meta`. Raises PersistenceError."""
        ...
```

- **DTOs.** `SettingKey` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 7b. UI Adapter Gateways (D-R-06)

Per D-R-06 and `08_Cross_Cutting/08-A_architecture_principles.md` §6, the UI layer never holds a backend Protocol. The adapter is the exclusive UI↔backend boundary: it holds the backend Protocols of §7–§22 and exposes, to each UI widget factory, exactly **one** UI-facing **gateway Protocol** per widget. Each gateway is a **method-only** `Protocol` — stdlib + `msgspec` types only, no `psygnal` and no Qt symbol — that the adapter implements over the backend Protocols (a direct call, a converted command record, or a derived read). The gateways carry only the **immediate query/command** surface a controller needs in place; push state still arrives separately as marshalled bus events (§6, the `08-J` catalog), never through a gateway return value.

**Why a gateway and not the store directly (SPEC-074).** The gateway's value is *not* hiding store names — it is being the single place where the Qt-specific concerns live: thread marshalling (a controller must never make a GIL-blocking backend call on the GUI thread), command-record construction, and view-model conversion. So a gateway is scoped to the methods its controller actually calls — it is a **purpose-built facade**, not a blanket one-for-one re-export of a store. Where a widget needs only a few of a store's methods, its gateway exposes only those. The module-inventory "Dependency Protocols" columns name the backend *capabilities* each widget needs; the widget itself depends only on its gateway, which the adapter implements over exactly those capabilities (the columns are read as "what the adapter wires behind this widget's gateway," never as "Protocols the widget holds").

### 7b.1 MainWindowGateway

Backs the Main Window (`01_Main_Window/implementation_structure.md`). Wraps `SettingsService` (window-shell persistence keys), `ReadinessService` (status-bar health dot), and `BenchmarkFlowApi` (the quit decision and graceful shutdown — the run-activity reads the shell needs in place, per 08-A §11 / D-R-05).

```python
from typing import Protocol


class MainWindowGateway(Protocol):
    """Adapter gateway for the Main Window shell (D-R-06)."""

    def get_window_geometry(self) -> str | None:
        """Read the persisted `ui.window_geometry` blob, or `None` if unset."""
        ...

    def set_window_geometry(self, value: str) -> None:
        """Persist the `ui.window_geometry` blob (debounced by the caller)."""
        ...

    def get_splitter_sizes(self) -> str | None:
        """Read the persisted `ui.splitter_sizes`, or `None` if unset."""
        ...

    def set_splitter_sizes(self, value: str) -> None:
        """Persist `ui.splitter_sizes`."""
        ...

    def get_active_workspace(self) -> str | None:
        """Read the persisted `ui.active_workspace` ("benchmark"/"task_editor")."""
        ...

    def set_active_workspace(self, value: str) -> None:
        """Persist `ui.active_workspace`."""
        ...

    def get_theme(self) -> str:
        """Read the resolved `ui.theme` setting."""
        ...

    def set_theme(self, value: str) -> None:
        """Persist `ui.theme`."""
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the status-bar dot."""
        ...

    def reprobe(self) -> None:
        """Trigger a readiness re-probe (on a worker thread) on a dot click."""
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently active (non-terminal) — the quit decision."""
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit (bounded wait)."""
        ...
```

- **DTOs.** `AppReadinessSnapshot` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7b.2 NewBenchmarkGateway

Backs the New Benchmark widget (`02_New_Benchmark_Widget/implementation_structure.md`). Wraps `SettingsStore` (Advanced-Options defaults, `benchmark.last_mode`, `embedding.hide_from_test_models`), `ProviderRegistry` (provider/model selection lists), `ReadinessService` (pre-run readiness), and the run-start command.

```python
from typing import Protocol


class NewBenchmarkGateway(Protocol):
    """Adapter gateway for the New Benchmark widget (D-R-06)."""

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a user-saved setting (Advanced-Options defaults,
        `benchmark.last_mode`, `embedding.hide_from_test_models`), or `None`."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a user-saved setting (e.g. `benchmark.last_mode`)."""
        ...

    def provider_list(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers, in display order, for the model picker."""
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the pre-run readiness gate."""
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id."""
        ...
```

- **DTOs.** `SettingKey`, `ProviderConfig`, `AppReadinessSnapshot`, `RunStartRequest`, `RunId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7b.3 ResumeGateway

Backs the Resume Benchmark widget (`03_Resume_Benchmark_Widget/implementation_structure.md`). Wraps `RunsStore`, `ResultsStore`, `TasksStore`, `ReadinessService` (drift refresh), `SettingsService` (sort persistence), and the resume command.

```python
from typing import Protocol


class ResumeGateway(Protocol):
    """Adapter gateway for the Resume Benchmark widget (D-R-06)."""

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first, for the run table."""
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one fully-assembled run (for Clone / detail reads)."""
        ...

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Create a run header + snapshots (the Clone-as-new-retry-run use case)."""
        ...

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a run-header status/counter patch."""
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear a run's user-facing name."""
        ...

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run and its dependent rows."""
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return a run's results (for counts / Clone)."""
        ...

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume."""
        ...

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to PENDING; return the count reset."""
        ...

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Stage-preserving retry reset (DD-66): a judge-only failure resumes at the
        judge stage on its preserved response; every other failure re-runs the whole
        task. Return the count reset."""
        ...

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert initial result rows (Clone-as-new-retry-run)."""
        ...

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result row."""
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks (Clone)."""
        ...

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot (Clone-as-new-retry-run)."""
        ...

    def refresh_readiness(self) -> AppReadinessSnapshot:
        """Refresh the readiness snapshot before the Run Drift Detector runs."""
        ...

    def get_sort_setting(self) -> tuple[str, bool]:
        """Read the persisted sort column and descending flag."""
        ...

    def set_sort_setting(self, column: str, descending: bool) -> None:
        """Persist the sort column and direction."""
        ...

    def resume_run(self, run_id: RunId) -> None:
        """Resume an INCOMPLETE run from where crash recovery left it."""
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (for the per-row `is_executing` flag)."""
        ...

    def active_run_id(self) -> RunId | None:
        """The id of the currently executing run, or `None` when idle."""
        ...
```

- **DTOs.** `BenchmarkRun`, `RunId`, `RunStatusPatch`, `BenchmarkResult`, `ResultId`, `ResultPatch`, `BenchmarkTask`, `AppReadinessSnapshot` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7b.4 ProgressGateway

Backs the Progress widget (`04_Progress_Widget/implementation_structure.md`). Wraps `BenchmarkFlowService` (pause/resume/stop), `RunRegistryStore` (run metadata; rename), `RunsStore` (elapsed/header/summary), `ResultsStore` (per-task counters), `RunLogReader` (past-log load), `SettingsStore` (`ui.run_log_verbosity`, `ui.auto_scroll_run_log`), and a manual-provider-probe command.

```python
from typing import Protocol


class ProgressGateway(Protocol):
    """Adapter gateway for the Progress widget (D-R-06)."""

    def pause_run(self) -> None:
        """Request a cooperative pause of the active run."""
        ...

    def resume_run(self) -> None:
        """Resume execution after a pause."""
        ...

    def stop_run(self, reason: str | None = None) -> None:
        """Request a cooperative stop of the active run."""
        ...

    def run_metadata(self, run_id: RunId) -> BenchmarkRun:
        """Read the active run's metadata from the run registry."""
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear the active run's user-facing name (the inline pencil)."""
        ...

    def run_header(self, run_id: RunId) -> BenchmarkRun:
        """Read a run header — elapsed time and the terminal run summary."""
        ...

    def task_counters(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read per-task result rows for the run-progress counters / current task."""
        ...

    def load_past_log(self, run_id: RunId) -> str:
        """Load the saved run-log of a past run for replay."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read `ui.run_log_verbosity` / `ui.auto_scroll_run_log`, or `None`."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist `ui.run_log_verbosity` / `ui.auto_scroll_run_log`."""
        ...

    def manual_provider_probe(self) -> None:
        """Trigger a manual provider probe (the stability "retry probe" action)."""
        ...
```

- **DTOs.** `RunId`, `BenchmarkRun`, `BenchmarkResult`, `SettingKey` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7b.5 ResultGateway

Backs the Result widget (`05_Result_Widget/implementation_structure.md`). Wraps `RunsStore` (headers; persist `run_analysis`), `ResultsStore` (tab caches), `TasksStore` (per-task metadata), `SettingsStore` (`ui.last_result_tab`, `ui.export_save_directly`, `ui.score_display_format`), `RunAnalysisService` (regenerate), `ChartService` (chart data), `TableSerializationService` (CSV/Markdown).

```python
from typing import Protocol


class ResultGateway(Protocol):
    """Adapter gateway for the Result widget (D-R-06)."""

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return the run headers for the run-selector dropdown."""
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Read one run header (for the active-run analysis and metadata)."""
        ...

    def persist_run_analysis(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Persist the consolidated `run_analysis` via a run-header patch."""
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read a run's results for the Summary / Details / Charts / Analysis caches."""
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Read per-task metadata (question, golden answer, required terms)."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read `ui.last_result_tab` / `ui.export_save_directly` /
        `ui.score_display_format`, or `None`."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist `ui.last_result_tab` / `ui.export_save_directly`."""
        ...

    def regenerate_run_analysis(self, run_id: RunId) -> None:
        """Regenerate the consolidated run analysis (worker thread)."""
        ...

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData:
        """Compute one chart's prepared `ChartData` / `HeatmapData`."""
        ...

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload."""
        ...
```

- **DTOs.** `BenchmarkRun`, `RunId`, `RunStatusPatch`, `BenchmarkResult`, `BenchmarkTask`, `SettingKey`, `ChartKind`, `ChartData` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` and `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md` for `ChartData`/`HeatmapData`.

### 7b.6 SettingsGateway

Backs the Settings Dialog (`06_Settings_Dialog/implementation_structure.md`). Wraps `ProvidersStore`, `AppSettingsStore` (incl. embedding selection keys), `ModelCapabilitiesStore`, `SettingsService`, `ProviderRegistry` (Test probes / model discovery), and `ReadinessService` (`probe_all`, embedding probe, snapshot).

```python
from typing import Protocol


class SettingsGateway(Protocol):
    """Adapter gateway for the Settings Dialog (D-R-06)."""

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Read the provider catalog for the Providers tab."""
        ...

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        """Look up a provider by display name for live duplicate-name validation."""
        ...

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically (Save / Import / Reset)."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read one user-saved setting, including the embedding selection keys
        (`embedding.selected_provider_name` / `embedding.selected_model_name`)."""
        ...

    def list_settings(self) -> dict[SettingKey, str]:
        """Read the full user-saved settings row set for the working copy."""
        ...

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        """Write several settings atomically (the settings half of Save / Reset)."""
        ...

    def get_resolved_str(self, key: SettingKey) -> str:
        """Resolve the current effective value of a general-tab key (initial copy)."""
        ...

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Read cached capability records for a model (capability hints)."""
        ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Persist a user-overridden capability record."""
        ...

    def test_provider(self, provider_id: ProviderId, model_name: ModelName) -> InferenceTestResult:
        """Run the per-row Test-connection inference probe for a provider/model."""
        ...

    def discover_models(self, provider_id: ProviderId) -> tuple[ModelName, ...]:
        """Discover a provider's models for the embedding-section picker."""
        ...

    def probe_all(self) -> AppReadinessSnapshot:
        """Run the auto-check on open; emits readiness-changed."""
        ...

    def probe_embedding(self) -> AppReadinessSnapshot:
        """Run the Test-Embedding probe behind the embedding section."""
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Read the current snapshot for the Health Dots."""
        ...
```

- **DTOs.** `ProviderConfig`, `SettingKey`, `ProviderId`, `ModelName`, `ModelCapabilityRecord`, `InferenceTestResult`, `AppReadinessSnapshot` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 7b.7 TaskEditorGateway

Backs the Task Editor (`09_Task_Editor/implementation_structure.md`). Wraps `SettingsStore` (workspace settings keys), `WorkspaceStore` (current workspace state), and `RunRegistryStore` (active run's task paths for the in-use marker).

```python
from typing import Protocol


class TaskEditorGateway(Protocol):
    """Adapter gateway for the Task Editor workspace (D-R-06)."""

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a workspace settings key (`task_editor.auto_format_on_save`,
        `task_editor.warn_on_empty_grading_criteria`,
        `task_editor.validation_debounce_ms`, `ui.task_editor_last_folder`)."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a workspace settings key (e.g. `ui.task_editor_last_folder`)."""
        ...

    def active_workspace(self) -> str:
        """Read the current active workspace ("benchmark"/"task_editor")."""
        ...

    def active_run_task_paths(self) -> tuple[str, ...]:
        """Read the active run's task file paths for the in-use marker."""
        ...
```

- **DTOs.** `SettingKey` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 8. Settings Service

Implements the three-layer settings hierarchy specified in `08_Cross_Cutting/08-C_settings_hierarchy.md`: resolution order is **per-run snapshot, then user-saved, then built-in default**. Only the user-saved layer is mutable through this service.

```python
from typing import Protocol


class SettingsService(Protocol):
    """Typed access to the three-layer settings hierarchy."""

    # --- Reads: resolve through snapshot -> user-saved -> default ----------
    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        """Resolve a string setting. When `run` is given, its frozen settings
        snapshot is consulted first. Raises ConfigurationError if the key is
        unknown.
        """
        ...

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        """Resolve a boolean setting. An **unknown key** raises ConfigurationError
        (a programmer error — the key is not in the registry). A **non-coercible
        user-saved value** (e.g. a hand-corrupted `app_settings` row) is treated
        as absent: the in-code **default** is returned and a warning is logged
        naming the key, so the default-floor guarantee of `08-C` (a read never
        returns absent) holds even against a corrupted row (SPEC-110). A
        non-coercible **per-run snapshot** value is a `ProgrammerError` (snapshots
        are app-written from validated input and cannot legitimately be malformed).
        """
        ...

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        """Resolve an integer setting. Same coercion-failure rule as `get_bool`
        (SPEC-110): unknown key raises; a malformed user-saved value falls through
        to the default with a logged warning; a malformed snapshot value is a
        `ProgrammerError`.
        """
        ...

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        """Resolve a float setting. Same coercion-failure rule as `get_bool`
        (SPEC-110): unknown key raises; a malformed user-saved value falls through
        to the default with a logged warning; a malformed snapshot value is a
        `ProgrammerError`.
        """
        ...

    # --- Writes: only the user-saved layer is mutable ----------------------
    def set(self, key: SettingKey, value: str) -> None:
        """Write one value to the user-saved layer. Raises ConfigurationError on
        an unknown key or a value that violates the key's constraint;
        PersistenceError on a storage failure.
        """
        ...

    def upsert(self, values: dict[SettingKey, str]) -> None:
        """Write several values to the user-saved layer atomically, then emit
        the settings-changed signal. Raises ConfigurationError, PersistenceError.
        """
        ...
```

- **Threading.** Synchronous; called on the main thread for UI reads and writes.
- **Errors.** `ConfigurationError` for an unknown key or a value that cannot be coerced to the requested type; `PersistenceError` on a write failure.
- **DTOs.** `SettingKey`, `BenchmarkRun` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 8a. Run Snapshot Builder

`RunSnapshotBuilder` is a standalone Protocol that captures the frozen per-run settings snapshot consumed by the run-creation use case at run start. It is intentionally **separate** from `SettingsService` so that the broad typed-read/typed-write surface does not need to be exposed to the benchmark pipeline (which only ever needs the snapshot). Both Protocols live in the same `backend/settings/` package and may share an internal resolver, but they are independently injected.

```python
from typing import Protocol


class RunSnapshotBuilder(Protocol):
    """Capture the frozen settings snapshot for a new run."""

    def build_snapshot(self) -> RunSettingsSnapshot:
        """Capture the resolved value of every per-run-overridable key as the
        frozen settings snapshot for a new run. Never raises for a present key.
        """
        ...
```

- **Threading.** Synchronous; called by the run-creation use case at run start (on the main thread).
- **Errors.** None for a present, well-typed key set; an underlying `PersistenceError` from the user-saved layer is propagated.
- **DTOs.** `RunSettingsSnapshot` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (the tuple of `BenchmarkRunSettingEntry` rows frozen into a run).

**Provider and embedding selection name snapshot (DD-33).** Alongside the settings snapshot, the run-creation use case also captures the **display-fidelity name snapshots** the historical UI will render: it reads the live `ProviderConfig` of the judge provider (when the run has one) and stamps both `judge_provider_id` and `judge_provider_name` into `BenchmarkRun`; it resolves the selected embedding `(provider, model)` from `app_settings` (when the run runs the cosine phase) and stamps the resolved `embedding_provider_name` and `embedding_model_name`; and for each per-task `BenchmarkResult` row it stamps the test provider's `name` (read from the run's already-frozen `benchmark_run_providers` snapshot — not from the live catalog — so a mid-run rename does not interleave names) into the row's `provider_name`. The run-snapshot builder is the central place this capture happens; the pipeline does not consult the live catalog for provider names after run start.

---

## 9. Provider Registry

Holds one `LLMClient` per configured provider and routes a `(ProviderId, ModelName)` target to its client. It reconstructs its clients when the provider catalog changes.

```python
from typing import Protocol


class ProviderRegistry(Protocol):
    """Owns the live LLM clients and routes targets to them."""

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers in display order. Synchronous; never raises."""
        ...

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        """Return the live client for a provider. Raises ConfigurationError if
        the provider is unknown, disabled, or its api-key env-var name does not
        resolve (the named variable is unset/empty).
        """
        ...

    def reload(self) -> None:
        """Rebuild every client from the current provider catalog, then emit the
        registry-reloaded signal. Raises ConfigurationError if a provider
        configuration is structurally invalid.
        """
        ...
```

- **Threading.** Fast-synchronous. `get_client` returns a client object; the network work happens in the client's own *blocking* methods, which are invoked on `TaskRunner` worker threads.
- **Errors.** `ConfigurationError` for an unknown, disabled, or misconfigured provider.
- **DTOs.** `ProviderConfig`, `ProviderId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 10. LLM Client

The unified provider-facing client. One concrete implementation exists per `ProviderType`; each wraps its provider SDK and translates that SDK's exceptions into the application taxonomy (Section 3). The per-provider quirks matrix is specified in `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`.

```python
from typing import Protocol


class LLMClient(Protocol):
    """A single provider's chat, embedding, and capability surface."""

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the provider's available model names; may be empty for a
        reachable provider that exposes none. Does not raise for an empty
        catalog; raises ProviderError only when the listing call itself fails.
        """
        ...

    def probe_health(self) -> ProviderHealth:
        """Reachability + conditional model discovery; NEVER an inference call.

        The probe performs only checks the provider can be expected to support
        without producing a billable inference. The two checks, in order:

        1. **Reachability.** Confirms the configured endpoint is reachable
           (DNS resolves, TCP connect succeeds, the basic auth handshake — if
           any — completes). A failure here sets `reachable=False` with
           `last_error` populated and skips the discovery step.
        2. **Model discovery — only if the provider supports it.** Providers
           vary: OpenAI-compatible endpoints expose `GET /v1/models`; some
           providers (notably Anthropic) historically expose no models-list
           endpoint and the model catalog is treated as configured; some Azure
           deployments are configured per-deployment. When the per-provider
           implementation does not support discovery, the probe records the
           FACT that discovery was skipped — `discovery_supported=False`,
           `model_count=None` — and **does NOT mark the provider unhealthy on
           that basis**. Zero discovered models is also not an unhealthy
           signal: a reachable provider that returns an empty list is reported
           as `reachable=True, discovery_supported=True, model_count=0`.

        Never raises: every failure mode (refused connection, auth rejected,
        deadline expired, listing call failed) is captured into the returned
        `ProviderHealth`. Never issues a chat or embedding inference call:
        the probe is cheap and idempotent enough to run on a background
        schedule without producing user-visible cost.
        """
        ...

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Run a small end-to-end chat call against this provider's named model
        and return a typed `InferenceTestResult`.

        This is the manual end-to-end check the Provider Edit dialog exposes
        as the **Test inference** action. It is user-initiated only — never
        run automatically — because for paid cloud providers this call is
        billable. The caller MUST hold the application-wide single-inference
        gate (`InferenceActivityStore.try_acquire(PROVIDER_TEST, ctx)`); if
        the gate is held by another activity, the method returns
        `InferenceTestResult(outcome=GATE_BUSY, ...)` without issuing a call.

        The method issues exactly one chat completion against `model_name`
        with a fixed canned prompt (for example "Reply with the single word:
        ok"). The total budget is bounded by the inference-test deadline. On
        completion it populates the result with:

        - the classified `outcome`,
        - `latency_ms` (total wall time, or `None` when the call never issued),
        - a redacted `response_excerpt` (≈200 chars) on success,
        - `last_error` (redacted) on any failure,
        - `tested_at` (unix-ms UTC) from the injected Clock.

        **Never raises.** Provider-side errors (model not found, auth,
        rate-limit, timeout) are captured into the result; no new exception
        class is introduced. No provider SDK exception type ever escapes.
        See `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.
        """
        ...

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Convenience wrapper (DD-51): consume this client's own `chat_stream`
        to completion and return the trailing `ChatResponse`. NOT a second
        transport path — `chat_stream` is the single execution algorithm; this
        sugar exists for callers that need no live progress. Error behaviour is
        identical to `chat_stream`.
        """
        ...

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        """THE chat execution surface (DD-51; blocking; invoked on a worker
        thread). Returns a synchronous iterator of `ChatChunk` — content chunks,
        plus >= 1 Hz empty-content heartbeat chunks during provider silence (the
        sub-second per-read timeout produces them) — followed by
        `trailing_response() -> ChatResponse`. The transport always opens in
        streaming mode so time-to-first-token can be measured; when the provider
        cannot stream (capability `False`, or the stream-open is rejected at call
        time) the client silently falls back to a non-streaming request behind
        the SAME iterator contract: heartbeat chunks while waiting, then one
        full-content chunk, then the trailing response (`ChatResponse.streamed`
        records which path ran; `ttft_ms` is `None` when not genuinely streamed).
        The per-run hard-cancel abort hook is registered around the in-flight
        stream for the call's duration (DD-39). Raises ProviderError when the
        provider rejects the request or returns an unusable response, and
        TimeoutError when the call exceeds `request.timeout_ms`. A non-throwing
        soft failure (a refusal that still returns text) is reported in
        `ChatResponse.error` instead.
        """
        ...

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding vector for `text`. Implemented only by
        embedding-capable clients. Raises ProviderError on failure; TimeoutError
        on a timeout.
        """
        ...

    def supports_streaming(self) -> bool:
        """Whether the transport supports token streaming. When `False`,
        time-to-first-token is `None` for every inference against this provider.
        """
        ...

    def supports_reasoning_effort(self) -> bool:
        """Whether the provider accepts a reasoning-effort parameter."""
        ...

    def supports_thinking(self) -> bool:
        """Whether the model emits a reasoning/thinking block. Probed once,
        then cached in `model_capabilities`.
        """
        ...
```

- **Threading.** `list_models`, `probe_health`, `test_inference`, `chat`, `chat_stream`, and `embed` are *blocking* — synchronous methods invoked only on a `TaskRunner` worker thread (they perform network I/O). The three `supports_*` methods are fast-synchronous capability lookups callable from any context.
- **Errors.** `chat` and `embed` raise `ProviderError` and `TimeoutError`. `list_models` raises `ProviderError` only when the listing call fails. `probe_health` never raises. `test_inference` never raises — every provider-side failure is captured into the returned `InferenceTestResult`. Each provider adapter is solely responsible for catching its SDK's exception types and re-raising them in this taxonomy; no provider SDK exception escapes the client.
- **DTOs.** `ModelName`, `ProviderHealth`, `InferenceTestResult`, `InferenceTestOutcome`, `ChatRequest`, `ChatResponse` (and `ChatMessage`, `ChatRole`, `ReasoningEffort`, `ResponseFormat`) — all in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 11. Benchmark Pipeline (Flow API)

The single backend entry point that drives a benchmark run from creation to a terminal status, across all three run modes (`SYNTHETIC`, `TASKS`, `GRADED`). The pipeline **never raises to its caller**: every failure is captured into a result's `error_kind`, `error_message`, and `ResultStatus`, and a catastrophic failure sets the run's `RunStatus` to `FAILED`. The state machine it drives is specified in `08_Cross_Cutting/08-B_benchmark_state_machine.md`.

```python
from typing import Protocol


class BenchmarkFlowApi(Protocol):
    """Controls the lifecycle of a single benchmark run. Never raises to the caller."""

    def start(self, request: RunStartRequest) -> RunId:
        """Create a run from the request, freeze its task / model / provider /
        settings snapshots, persist the initial result rows, and **hand the run
        to the pipeline's dedicated dispatcher thread (DD-38)**, which executes
        the run's units one at a time on `TaskRunner` worker threads. Returns the
        new run id promptly (it does not block until the run finishes); progress
        is reported via the Event Bus. A failure during creation is recorded as
        `RunStatus.FAILED`.

        **Admission is the gate (SPEC-036).** The **first** step of `start`, run
        **synchronously on the GUI thread**, is `InferenceActivityStore.try_acquire(BENCHMARK_RUN)`
        (DD-50 — an atomic test-and-set returning a `GateLease`, or `None` when an
        activity already holds it). Only on a successful acquire does `start` create
        the run, persist the initial result rows, and hand the run **and its lease**
        to the dispatcher thread, which releases the lease in its terminal `finally`.
        Acquiring before any creation or row write closes the double-click / second-path
        admission window: a rapid second call hits `None` and cannot create a second
        run or write any row.

        **Precondition — already running.** If `try_acquire` returns `None`,
        `start` does **not** launch a second run (execution is strictly serial,
        D-R-16): it makes no new run, leaves the active run untouched, writes nothing,
        and returns without starting anything. The attempt is surfaced as a rejected
        `RunStatus.FAILED` record and is never raised to the caller; the currently
        active run's `RunId` remains the one reported by `current_run()`. Callers must
        gate the Start affordance on `is_running()` and treat a returned id as belonging
        to the rejected attempt, not a newly launched second run.
        """
        ...

    def resume(self, run_id: RunId) -> None:
        """Resume an `INCOMPLETE` run: re-execute its `PENDING` and retryable-failure
        results one at a time on worker threads from where the crash-recovery sweep
        left them. Returns promptly; a failure is recorded on the run, not raised.

        **Admission is the gate (SPEC-036).** Exactly like `start`, the **first** step,
        run **synchronously on the GUI thread**, is `InferenceActivityStore.try_acquire(BENCHMARK_RUN)`
        (DD-50). Only on success does `resume` reset the selected retry rows (the
        Retry-Selection / Resume-Summary picker's chosen rows) and hand the run **and
        its lease** to the dispatcher thread (DD-38), which releases the lease in its
        terminal `finally`. If `try_acquire` returns `None`, `resume` is a **no-op**:
        it resets no rows, enqueues nothing, and returns — so a double-click, or a
        Resume-Summary Confirm racing another admission, cannot reset rows or start a
        second pipeline against the same run. The row reset is idempotent: re-resetting
        an already-`PENDING` row is a no-op, so even a retried admission is safe.
        """
        ...

    def pause(self) -> None:
        """Request a cooperative pause at the next safe checkpoint. The persisted
        run status stays `INCOMPLETE`; the paused state is in-memory only.
        **No-op when idle:** if `is_running()` is `False`, `pause` does nothing and
        returns; it never raises and emits no event. Calling `pause` while already
        paused is also a no-op.
        """
        ...

    def resume_paused(self) -> None:
        """Resume execution after `pause()`. **No-op when idle or not paused:** if
        `is_running()` is `False`, or a run is active but not paused, `resume_paused`
        does nothing and returns; it never raises.
        """
        ...

    def stop(self) -> None:
        """Request a hard-cancel stop (`CancelReason.USER_STOP` — DD-39/DD-42). When
        the run halts, its persisted status becomes `STOPPED` (outcome matrix,
        `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` §6.8). A stop on a
        run parked as `PAUSED` wakes the parked dispatcher and settles it `STOPPED`.
        **No-op when idle:** if `is_running()` is `False`, `stop` does nothing and
        returns; it never raises and emits no event.
        """
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit: cancel the token,
        stop accepting new units, and wait up to `timeout_ms` for in-flight work
        to settle, the worker pool to drain, and the dispatcher thread (DD-38) to
        halt and be joined. Called on the GUI thread during quit; the bounded wait
        may briefly block, after which the app exits (a timeout triggers a
        force-quit). See `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §6.
        """
        ...

    def is_running(self) -> bool:
        """Whether a run is currently executing (including the paused state)."""
        ...

    def current_run(self) -> BenchmarkRun | None:
        """The run currently being executed, or `None` when idle."""
        ...
```

The in-memory `RUNNING` and `PAUSED` states this API exposes are never written to the database; only the four persisted statuses (`INCOMPLETE`, `COMPLETED`, `FAILED`, `STOPPED`) appear in storage. The pipeline reports progress entirely through Event Bus signals (`08_Cross_Cutting/08-J_event_bus_catalog.md`).

- **Threading.** `start` and `resume` are fast-synchronous on the GUI thread: they validate, enqueue a run command to the pipeline's dedicated **dispatcher thread** (DD-38, `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a), and return promptly. The dispatcher thread runs the blocking run loop and is the only thread that blocks awaiting a unit's `Future`. `shutdown` is synchronous and may briefly block (bounded) during quit while the pool drains and the dispatcher thread is joined. `pause`, `resume_paused`, `stop`, `is_running`, and `current_run` are fast-synchronous control/query methods called on the GUI thread. Cancellation is cooperative via the `threading.Event`-backed `CancellationToken`.
- **Errors.** None raised to the caller. Every failure is captured into result and run records. The containment mechanism is §11a below.
- **DTOs.** `RunStartRequest` (and `ModelDescriptor`, `PerformanceConfig`), `BenchmarkRun`, `RunId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

### 11a. Exception containment — how "never raises" is achieved (DD-44)

The pipeline's never-raises guarantee is a **mechanism**, not an aspiration. Every
exception class its dependencies can raise is caught and converted at a defined point:

| Exception reaching the pipeline | Caught where | Converted to |
|---|---|---|
| Provider-surface errors from a unit (`ProviderError` leaves, `TimeoutError`) | The dispatcher, when it reads the unit's `Future` | The result row's `error_kind` / `error_message` / terminal `ResultStatus` (after the retry policy inside the unit is exhausted) |
| `TaskCancelledError` (soft or hard cancel) | The dispatcher's halt path | The DD-42 outcome matrix — `PAUSED` / `STOPPED` / `INCOMPLETE`; never an error |
| `ConfigurationError` from the Provider Registry or Settings Service during run setup or resume | The run-creation / resume use case | `RunStatus.FAILED` with the error recorded on the run; `_run_start_failed` or `_run_failed` emitted |
| `DatabaseLockedError` on a pipeline write | The single DB writer call site | Retried per the retry table (8 attempts / 5 s total — `11_Services_and_Algorithms/18_RETRY_POLICY.md` §6.2); converts to the persist-failure path below only if exhausted |
| Any other `PersistenceError` on a pipeline write (disk full, corruption) | The dispatcher | **The persist-failure path:** the run settles `FAILED` — the pipeline *best-effort* writes `RunStatus.FAILED` plus the error to the run header; if even that write fails, it logs the failure to the `app.*` stream, emits `_run_failed` so the UI is honest, and leaves the run `INCOMPLETE` for the next-launch recovery sweep (the sweep is the designed safety net for exactly this state) |
| `ProgrammerError` | **Never caught.** | Propagates to the process-terminal hook and crashes with a full diagnostic, per the error-handling standard |

**Enforcement.** An architecture test asserts that no public `BenchmarkFlowApi` method can
propagate an `AppError` to its caller: each is invoked against dependency fakes rigged to
raise every taxonomy category in turn, and the method must return normally (with the
failure recorded as data) for every category except `ProgrammerError`.

---

## 12. Readiness Service

Aggregates per-provider health probes and the embedding-model reachability into a single application-readiness snapshot. The probe algorithm is specified in `11_Services_and_Algorithms/09_READINESS_PROBE.md`.

```python
from typing import Protocol


class ReadinessService(Protocol):
    """Aggregates provider and embedding health into an application-readiness view."""

    def snapshot(self) -> AppReadinessSnapshot:
        """Return the most recent readiness snapshot. Synchronous; never raises;
        returns a `CHECKING` snapshot before the first probe completes.
        """
        ...

    def probe_all(self) -> AppReadinessSnapshot:
        """Probe every enabled provider and the embedding model, recompute the
        aggregate, emit the readiness-changed signal, and return the new
        snapshot. Blocking (network I/O) — invoked on a `TaskRunner` worker
        thread. Never raises: an unreachable provider is reported as such.
        """
        ...

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        """Probe one provider and return its health. Blocking; invoked on a
        worker thread. Never raises."""
        ...
```

- **Threading.** `snapshot` is fast-synchronous (callable from the GUI thread). `probe` is *blocking* — a single leaf unit invoked on a `TaskRunner` worker thread. `probe_all` is *blocking* and **orchestrated on the dispatcher thread** (DD-38/DD-40): the dispatcher fans the per-provider reachability handshakes (not inferences — DD-40) out to `TaskRunner` workers concurrently and joins them; the single `embed` probe is the batch's only inference-class call and runs serially. A leaf probe never submits-and-waits on the pool.
- **Errors.** None. Unreachability is data, not an exception.
- **DTOs.** `AppReadinessSnapshot` (and `ReadinessState`), `ProviderHealth`, `ProviderId` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 13. Inference Activity Store

The application-wide single-inference gate. The store enforces the rule that **at most one** inference-using activity class may be in flight at any moment across the whole application: a benchmark run, a judge-analysis generation, a Provider Edit Test Connection probe, and a readiness probe never overlap. Every backend service that issues an inference call must acquire-then-release this gate for the full duration of its activity. Every UI surface that initiates an inference observes the gate state **through the adapter** — never by subscribing to the store directly — and disables its trigger while another activity holds the gate; the service-side `try_acquire` is the safety net. The gate is held for the **full duration** of an activity, not per-call. The watchdog auto-release timeouts and the user-facing edge cases are catalogued in `08_Cross_Cutting/08-I_edge_cases.md`.

The store lives at `backend/stores/inference_activity/` and exposes the method-only Protocol below. On every acquire/release the concrete store publishes the typed `_inference_activity_changed` event on the Qt-free event bus (`08_Cross_Cutting/08-J_event_bus_catalog.md`); the adapter's `qt_event_bus` bridge marshals it onto the Qt main thread, and the adapter additionally exposes an immediate-check gateway method (e.g. `is_inference_busy()`) that the UI calls for an in-place check. The UI never imports the store and never subscribes to a backend reactive primitive (08-A §5, §11).

```python
from typing import Protocol


class InferenceActivityStore(Protocol):
    """Application-wide single-inference gate. Method-only; stdlib + msgspec types
    only — no Qt symbol and no psygnal Signal appear on this Protocol (08-A §3).
    State-change notification is published by the concrete store as the typed
    `_inference_activity_changed` event on the Qt-free event bus; how the concrete
    store detects a change internally (e.g. psygnal) is an implementation detail
    that never crosses this contract.
    """

    def try_acquire(
        self,
        activity: InferenceActivity,
        context: InferenceActivityContext,
    ) -> GateLease | None:
        """Atomically acquire the gate (DD-50).

        Returns a `GateLease` — the opaque ownership token for THIS acquisition —
        when the gate was `IDLE` and is now held; returns `None` when the gate is
        already held by any other activity (a failed acquire is data, never an
        exception). The caller MUST pair a successful `try_acquire` with
        `release(lease)` in a `try/finally` so the gate is freed even on exception.
        """
        ...

    def release(self, lease: GateLease) -> None:
        """Release the gate IF `lease` is the CURRENT holder (DD-50).

        Ownership is the lease, not the activity enum: a `release` carrying a
        superseded or foreign lease — e.g. a worker's late `finally` after the
        watchdog already released its lease and a new same-class activity
        acquired — is a logged no-op and can never free a successor's hold.
        Idempotent.
        """
        ...

    def state(self) -> InferenceActivityState:
        """Return the current state synchronously.

        The returned value is an immutable snapshot; callers do not need to copy it.
        """
        ...

    def is_busy(self) -> bool:
        """Convenience: `state().current != InferenceActivity.IDLE`."""
        ...
```

- **Threading.** All methods are safe to call from **any** thread — both `QThreadPool` worker threads (the pipeline, the Provider Edit Test probe runner) and the Qt main thread (UI gating reads). Thread-safety is provided by **one `threading.Lock`** held internally: `try_acquire` is an atomic test-and-set under that lock and `state`/`is_busy` are locked reads. This gate is one of exactly two cross-thread locked objects in the application (the other is the single DB writer); the "single-owner state needs no lock" rule of `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` §3 is about single-owner state and explicitly carves out this gate. State-change notification reaches the UI as the typed `_inference_activity_changed` event on the Qt-free event bus, marshalled onto the Qt main thread by the adapter's `qt_event_bus` bridge — there is no `psygnal.Signal` on this Protocol (08-A §3, D-R-06). (Per D-R-01 and D-R-06.)
- **Errors.** None. The gate is data: a failed acquire returns `False`, not an exception.
- **DTOs.** `InferenceActivity`, `InferenceActivityContext`, `InferenceActivityState`, `GateLease` — all in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.
- **Watchdog (DD-50).** Implementations apply per-activity auto-release timeouts (specified in `08_Cross_Cutting/08-I_edge_cases.md`) so a crashed acquirer cannot lock the gate forever. The watchdog **arms with the `GateLease` it observed** and auto-releases by calling `release(that_lease)` — so if the original holder's late `finally` fires afterwards, its stale lease no-ops and a successor's hold is never stolen. `BENCHMARK_RUN` has no watchdog — the pipeline owns its own lifecycle and the orphan-run sweep recovers from a process death.

---

## 14. Task File Loader

Loads benchmark tasks from YAML files for a run. It is **loader-tolerant**: it skips a malformed task, logs a warning, and never raises for a per-task content problem. It raises only when a file is wholly unreadable.

```python
from typing import Protocol


class TaskFileLoader(Protocol):
    """Loader-tolerant reader of YAML task files."""

    def scan_directory(self, folder: str) -> tuple[str, ...]:
        """Return the sorted `.yaml` and `.yml` paths in a folder. Raises
        TaskFileError only if the folder cannot be read at all.
        """
        ...

    def load_tasks(self, paths: tuple[str, ...]) -> tuple[BenchmarkTask, ...]:
        """Load and parse the given files into `BenchmarkTask` values, skipping
        malformed individual tasks with a logged warning and de-duplicating by
        `task_id` (first occurrence wins). Raises TaskFileError only for a file
        that cannot be read or parsed as YAML at all.
        """
        ...
```

- **Threading.** Synchronous; file reads are local and fast. The run-creation use case calls it before a run starts.
- **Errors.** `TaskFileError` for an unreadable folder or an unreadable / non-YAML file. A bad individual task is a logged warning, not an exception.
- **DTOs.** `BenchmarkTask` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 15. Task File Validator

Validates a task file for the Task Editor. It is **editor-strict**: it re-reads the raw YAML and produces per-row diagnostics rather than skipping content. It complements the loader, which is tolerant; the validator surfaces every problem so the user can fix it. The validation cascade is specified in `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.

```python
from typing import Protocol


class TaskFileValidator(Protocol):
    """Editor-strict validator producing per-row diagnostics."""

    def validate_file(self, path: str) -> ValidationReport:
        """Re-read and validate one task file, returning a full diagnostic
        report. Raises TaskFileError only when the file cannot be read at all;
        a file that is unparseable YAML is reported as a file-level hard-error
        diagnostic inside the report, not as an exception.
        """
        ...
```

`ValidationReport` and `Diagnostic` are contract-local types used only by the validator and the Task Editor:

```python
import msgspec


class Diagnostic(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    severity: str            # "error" | "warning" | "info"
    task_index: int | None   # None = file-level diagnostic
    field_name: str | None
    message: str
    rule_id: str             # stable identifier, e.g. "TASK_ID_EMPTY"


class ValidationReport(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    file_path: str
    diagnostics: tuple[Diagnostic, ...]
    has_hard_errors: bool    # True when any diagnostic has severity "error"
```

- **Threading.** Synchronous. The Task Editor debounces calls per `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.
- **Errors.** `TaskFileError` only for a file that cannot be opened. Content problems become diagnostics.
- **DTOs.** `ValidationReport` and `Diagnostic` are defined above (contract-local).

---

## 16. YAML Formatter

Serialises and parses task files in the canonical field order, preserving user comments on a round trip. The formatter algorithm and the comment-anchoring rules are specified in `11_Services_and_Algorithms/12_YAML_FORMATTER.md`.

```python
from typing import Protocol


class YamlFormatter(Protocol):
    """Comment-preserving serialiser and parser for task files."""

    def serialize(self, tasks: tuple[BenchmarkTask, ...]) -> str:
        """Render tasks as YAML in canonical field order, preserving anchored
        comments from a prior parse. Never raises for valid `BenchmarkTask`
        values.
        """
        ...

    def parse(self, text: str) -> tuple[BenchmarkTask, ...]:
        """Parse YAML text into `BenchmarkTask` values, retaining comments for a
        later round trip. Raises TaskFileError when `text` is not valid YAML or
        does not match the expected task-file shape.
        """
        ...
```

- **Threading.** Synchronous; in-memory text transforms.
- **Errors.** `parse` raises `TaskFileError` for invalid YAML or a wrong root shape. `serialize` does not raise for valid input.
- **DTOs.** `BenchmarkTask` — see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 17. Adaptive Timeout Service

Computes the per-attempt timeout budget for each `(provider_id, model_name, role)` target from observed call durations, and tracks consecutive maximum-timeout failures so an unstable model can be excluded **per role**. The algorithm is specified in `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`. Control parameters are read from the active run's frozen settings snapshot **per role**: the `benchmark.*` ladder for `role=INFERENCE` (`benchmark.min_timeout_seconds`, `benchmark.max_timeout_seconds`, `benchmark.retry_count`, `benchmark.consecutive_max_timeouts_to_exclude`) and the parallel `eval.judge_timeout_*` ladder for `role=JUDGE` (`eval.judge_timeout_min_seconds`, `eval.judge_timeout_max_seconds`, `eval.judge_timeout_escalation_steps`, `eval.judge_timeout_consecutive_threshold`).

The service has **four consumers**:
- the Benchmark Pipeline Phase 2 inference call — `role=INFERENCE`;
- the Benchmark Pipeline Phase 4 per-task judge call — `role=JUDGE`;
- the Run Analysis Service's user-initiated analysis generation call — `role=RUN_ANALYSIS` (its own independent per-role bucket, DD-65; it does not share state with the per-task JUDGE bucket — see §17 below).

The service is **NOT consulted by** the embedding service (fixed `eval.embedding_timeout_seconds` budget), `LLMClient.test_inference` (fixed 60 s Provider Test deadline), or `LLMClient.probe_health` (fixed short readiness deadline). See DD-34.

A model used as both a test model AND a judge model carries **two independent state buckets**; exclusion in `role=JUDGE` does NOT exclude the same model in `role=INFERENCE`, and vice versa.

`AdaptiveTimeoutModelState` is a contract-local enum used by this service and surfaced to the UI **only through the adapter** (it is carried on a progress-event payload / view-model field, never read by a widget calling the service directly — see `model_state` below and D-R-06):

```python
from enum import StrEnum


class AdaptiveTimeoutModelState(StrEnum):
    OK       = "ok"        # stable; no exclusion pressure
    WARN     = "warn"      # some recent timeouts; near the exclusion threshold
    EXCLUDED = "excluded"  # excluded from the run after repeated max-timeouts (per role)
```

```python
from typing import Protocol


class AdaptiveTimeoutService(Protocol):
    """Per-(provider, model, role) adaptive timeout and stability tracking."""

    def next_budget(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        attempt_index: int = 1,
    ) -> int:
        """Return the timeout budget, in seconds, for the next attempt of a
        `(provider, model, role)` target. Synchronous; never raises; returns the
        role-appropriate configured floor before any outcome is recorded for the
        target. The returned value is consumed by the caller as its per-attempt
        deadline; the caller is responsible for multiplying to milliseconds when
        crossing to the LLM client.
        """
        ...

    def record_success(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        observed_ms: int,
    ) -> None:
        """Record one successful attempt's observed duration in milliseconds for
        the given role. Promotes the per-role last-known-good budget when the
        observation exceeds the current value; resets the in-run consecutive
        max-timeout counter for this `(provider, model, role)`. Synchronous;
        never raises.
        """
        ...

    def record_timeout(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
    ) -> None:
        """Record one timed-out attempt for the given role. Increments the
        in-run consecutive max-timeout counter (when the attempt's budget was at
        the role's max ceiling), and may flip the `(provider, model, role)`
        bucket to EXCLUDED when the role's `consecutive_threshold` is reached.
        Synchronous; never raises.
        """
        ...

    def is_excluded(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
    ) -> bool:
        """Return whether the `(provider, model, role)` target is excluded for
        the remainder of the current run. Independent per role: a JUDGE
        exclusion does NOT exclude the same `(provider, model)` in role
        INFERENCE, and vice versa. Synchronous; never raises.
        """
        ...

    def model_state(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
    ) -> AdaptiveTimeoutModelState:
        """Return the current stability state of a `(provider, model, role)`
        target. Called on the dispatcher thread; its result is delivered to the
        Progress widget's stability indicator (test model at `role=INFERENCE`,
        judge model at `role=JUDGE`) **through the adapter** — carried on a
        progress-event payload / view-model field. The Progress widget never
        calls this method directly (08-A §5, D-R-06). Synchronous; never raises.
        """
        ...
```

- **Threading.** Synchronous; pure in-memory bookkeeping driven by the pipeline and the Run Analysis Service.
- **Errors.** None.
- **Per-role bucket semantics.** State is keyed on `(provider_id, model_name, role)`. The persistent last-known-good budget for a `(provider, model, JUDGE)` bucket is shared between the per-task judge calls of a `BENCHMARK_RUN` activity and a subsequent user-initiated `JUDGE_ANALYSIS` activity; the in-run consecutive-timeout count resets at each new activity invocation (each Generate Analysis click starts a fresh count). See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` §6.1 and `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` §6.
- **DTOs.** `ProviderId`, `ModelName`, `AdaptiveTimeoutRole` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`); `AdaptiveTimeoutModelState` defined above (contract-local).

---

## 18. Provider Circuit Breaker

Tracks consecutive provider failures and trips a provider out of the run for a cooldown window, then probes it before closing again. The open/closed/probing semantics are specified in `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`.

`CircuitState` is a contract-local enum used only by this service:

```python
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED  = "closed"   # provider is in use
    TRIPPED = "tripped"  # provider is skipped during a cooldown window
    PROBING = "probing"  # cooldown elapsed; a single probe is in flight
```

```python
from typing import Protocol


class ProviderCircuitBreaker(Protocol):
    """Per-provider failure circuit breaker for the benchmark pipeline."""

    def state(self, provider_id: ProviderId) -> CircuitState:
        """Return the current breaker state for a provider. Synchronous; never raises."""
        ...

    def record_failure(self, provider_id: ProviderId) -> None:
        """Record a provider failure; may trip the breaker. Synchronous; never raises."""
        ...

    def record_success(self, provider_id: ProviderId) -> None:
        """Record a provider success; closes a probing breaker. Synchronous; never raises."""
        ...

    def should_skip(self, provider_id: ProviderId) -> bool:
        """Whether the pipeline should skip this provider right now (the breaker
        is tripped and still in cooldown). Synchronous; never raises.
        """
        ...

    def cooldown_remaining_seconds(self, provider_id: ProviderId) -> int | None:
        """Seconds left in a tripped provider's cooldown, or `None` when the
        breaker is not tripped. Synchronous; never raises.
        """
        ...
```

- **Threading.** Synchronous; in-memory state consulted by the pipeline.
- **Errors.** None.
- **DTOs.** `ProviderId` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`); `CircuitState` defined above (contract-local).

---

## 19. Workspace Controller

Switches the main window between its two workspaces — the benchmark workspace and the task-editor workspace — and carries an optional hint for the destination.

`WorkspaceHint` is a contract-local type:

```python
import msgspec


class WorkspaceHint(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    open_paths: tuple[str, ...] = ()   # task-editor: pre-open these files
    focus_widget: str | None = None    # e.g. "progress", "result_summary"
```

```python
from typing import Protocol


class WorkspaceController(Protocol):
    """Controls which of the two main-window workspaces is active."""

    def active(self) -> str:
        """Return the active workspace name: "benchmark" or "task_editor".
        Synchronous; never raises.
        """
        ...

    def switch_to(self, name: str, hint: WorkspaceHint | None = None) -> None:
        """Switch to the named workspace ("benchmark" or "task_editor"),
        applying the optional hint. Synchronous; never raises for a valid name.
        """
        ...
```

- **Threading.** Synchronous; called on the main thread.
- **Errors.** None for a valid workspace name.
- **DTOs.** `WorkspaceHint` defined above (contract-local).

---

## 20. Notification Service

Surfaces transient and modal user notifications. It is the only sanctioned path for a controller to raise a user-visible message; UI primitives never throw to the user.

```python
from typing import Protocol


class NotificationService(Protocol):
    """User-facing notifications: toasts and modal error dialogs."""

    def show_info(self, text: str, duration_ms: int = 5000) -> None:
        """Show a transient informational toast. Synchronous; never raises."""
        ...

    def show_warning(self, text: str, duration_ms: int = 5000) -> None:
        """Show a transient warning toast. Synchronous; never raises."""
        ...

    def show_error(self, text: str, blocking: bool = False) -> None:
        """Show an error notification: a toast when `blocking` is `False`, a
        modal dialog when `True`. Synchronous; never raises.
        """
        ...
```

- **Threading.** Synchronous; must be called on the main thread. A background worker that needs to notify the user emits an Event Bus signal instead; the adapter layer marshals it.
- **Errors.** None.
- **DTOs.** None.

---

## 21. OS Adapter Protocols

The operating-system integration surface is split into **three focused Protocols**, one per integration kind. There is no umbrella `Protocol` over the three: each is constructed, injected, and consumed in its own right. The three live in sibling feature packages under `adapters/`. They share these common rules:

- **Threading.** Synchronous; called on the main thread.
- **Errors.** Each method may raise `OsAdapterError` on an integration failure. Picker cancellation is a `None` / empty result, not an error.
- **Substitutability.** Platform-specific code is hidden behind the Protocol so the UI is platform-agnostic and every method is substitutable in tests.

### 21a. NativePickers

`SavePickerOptions`, `FilePickerOptions`, and `FolderPickerOptions` are contract-local types used only by this Protocol:

```python
import msgspec


class SavePickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    title: str
    suggested_name: str
    start_dir: str | None = None
    filters: tuple[str, ...] = ()   # display filters, e.g. "CSV (*.csv)"


class FilePickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    title: str
    start_dir: str | None = None
    filters: tuple[str, ...] = ()
    allow_multiple: bool = False


class FolderPickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    title: str
    start_dir: str | None = None
```

```python
from typing import Protocol


class NativePickers(Protocol):
    """Native save / open-file / open-folder dialogs."""

    def save_file(self, options: SavePickerOptions) -> str | None:
        """Show a native save dialog; return the chosen path, or `None` when the
        user cancels. Raises OsAdapterError only on a dialog-subsystem failure.
        """
        ...

    def open_file(self, options: FilePickerOptions) -> tuple[str, ...]:
        """Show a native open dialog; return the chosen paths (empty when the
        user cancels). Raises OsAdapterError only on a dialog-subsystem failure.
        """
        ...

    def open_folder(self, options: FolderPickerOptions) -> str | None:
        """Show a native folder dialog; return the chosen folder, or `None` when
        the user cancels. Raises OsAdapterError only on a dialog-subsystem
        failure.
        """
        ...
```

- **DTOs.** `SavePickerOptions`, `FilePickerOptions`, `FolderPickerOptions` defined above (contract-local).

### 21b. Clipboard

```python
from typing import Protocol


class Clipboard(Protocol):
    """System clipboard write surface."""

    def copy_text(self, text: str) -> None:
        """Place text on the system clipboard. Raises OsAdapterError if the
        clipboard is unavailable.
        """
        ...
```

- **DTOs.** None.

### 21c. FileSystemActions

```python
from typing import Protocol


class FileSystemActions(Protocol):
    """File-manager integration."""

    def open_in_file_manager(self, path: str) -> None:
        """Reveal a file or folder in the OS file manager. Raises OsAdapterError
        if the path does not exist or the manager cannot be launched.
        """
        ...
```

- **DTOs.** None.

---

## 22. Redaction module

The redaction module is applied at exactly two surfaces — the `app.*` log namespace's structlog pipeline and provider SDK error-message wrapping at the adapter boundary — specified in `10_Domain_and_Data/08_REDACTION_PATTERNS.md`. Its denylist, length cap, and the architectural rule that the local-app threat model treats user-authored prompts and user-machine model responses as the user's own data (and therefore does NOT redact them on display, in exports, or on the clipboard) are specified in that document. The module is a small set of pure functions rather than a stateful service, so its contract is a function-signature group, not a `Protocol`.

```python
def redact(text: str) -> str:
    """Return `text` with every secret-shaped substring masked. Used at the
    provider adapter boundary (to clean an SDK exception message before placing
    it on AppError.message); the `app.*` log namespace applies the companion
    `redact_for_log` structlog processor. Pure; synchronous; never raises.
    """
    ...


def redact_for_log(record) -> dict | str:
    """The structlog processor installed in the `app.*` log namespace pipeline.
    Walks the record's fields, replaces never-log field values with the
    placeholder, serialises the record to its log-line form, applies the
    secret denylist to the serialised line, and applies the length cap.
    Attached ONLY to the `app.*` namespace, NOT to `run.*`. Pure; synchronous;
    never raises.
    """
    ...
```

- **Threading.** Synchronous and pure; callable from any thread.
- **Errors.** None. Redaction never fails; an unrecognised input is returned with whatever secret-shaped substrings it contains masked, and nothing else changed.
- **DTOs.** None.

The architectural rule: the provider adapter calls `redact(text)` on every SDK exception message before constructing `AppError.message`; the `app.*` log pipeline has `redact_for_log` installed as a processor stage; the support-bundle builder applies `redact(text)` to bundled log content and settings credential values when copying them into the archive. The earlier `redact_for_display` and `redact_for_csv` functions are retired (`08_Cross_Cutting/08-F_spec_issues_log.md`); UI surfaces, exports, the clipboard, and the per-run `run.*` log do not apply redaction.

---

## 23. The application context

Every service is constructed exactly once at startup by a single composition root. Concrete classes are never instantiated inside a widget; widgets and adapters receive service handles by constructor injection. The `ApplicationContext` is the composition root's **internal** assembly of those handles — a wiring convenience, **not** a container handed around the app (SPEC-075).

```python
import msgspec


class ApplicationContext(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    clock: Clock
    event_bus: EventBus
    runs_store: RunsStore
    tasks_store: TasksStore
    results_store: ResultsStore
    providers_store: ProvidersStore
    model_capabilities_store: ModelCapabilitiesStore
    app_settings_store: AppSettingsStore
    settings: SettingsService
    run_snapshot_builder: RunSnapshotBuilder
    providers: ProviderRegistry
    readiness: ReadinessService
    inference_activity: InferenceActivityStore
    flow: BenchmarkFlowApi
    task_loader: TaskFileLoader
    task_validator: TaskFileValidator
    yaml_formatter: YamlFormatter
    adaptive_timeout: AdaptiveTimeoutService
    circuit_breaker: ProviderCircuitBreaker
    workspace: WorkspaceController
    notifications: NotificationService
    native_pickers: NativePickers
    clipboard: Clipboard
    file_system_actions: FileSystemActions
```

The composition root builds each concrete service, wires the dependencies between them, and assembles this context **for its own use only**. It is **never** handed to the UI layer, to a widget, to a controller, or to an adapter — passing this whole bundle to a consumer would be a service locator, which `08_Cross_Cutting/08-A_architecture_principles.md` §11 bans (SPEC-075). Instead, `compose.py` reads handles out of the context to construct each widget with **only** its adapter gateway (§7b) plus the few UI-layer services it needs, by explicit constructor injection. A view talks only to its controller; a controller talks only to its gateway. No consumer receives the `ApplicationContext` itself.

---

## 24. Where each contract is consumed

| Contract | Primary consumers |
|---|---|
| `Clock` | every service that timestamps or measures a duration |
| `EventBus` | every widget controller; the Benchmark Pipeline; the Readiness Service |
| `RunsStore` | the run-creation use case; the Benchmark Pipeline; the Resume and Result widgets |
| `TasksStore` | the run-creation use case; the Benchmark Pipeline; the Resume widget (clone) and Result widget |
| `ResultsStore` | the Benchmark Pipeline; the Resume and Result widgets; the crash-recovery sweep at startup |
| `ProvidersStore` | the Settings dialog (Add via `add(draft)`, Edit via `update`, duplicate-name pre-check via `get_by_name`); the Provider Registry; the Readiness Service; the importer |
| `ModelCapabilitiesStore` | the Settings dialog; the model-capability service consulted by the Benchmark Pipeline |
| `AppSettingsStore` | the Settings dialog (including the embedding `(provider, model)` selection keys `embedding.selected_provider_name` / `embedding.selected_model_name`); the SettingsService; the embedding service; the run-creation use case (resolves and snapshots the embedding selection) |
| `SettingsService` | the Settings dialog; the run-creation use case (via `RunSnapshotBuilder`); the Benchmark Pipeline |
| `RunSnapshotBuilder` | the run-creation use case (the only consumer; called once at run start to freeze the per-run-overridable settings snapshot) |
| `ProviderRegistry` | the Benchmark Pipeline; the Readiness Service; the Settings dialog |
| `LLMClient` | the Benchmark Pipeline (inference and judge phases); the embedding service; the Settings dialog Provider Edit (`probe_health` for the **Test reachability** action and `test_inference` for the **Test inference** action — both user-initiated); the Readiness Service (`probe_health` only) |
| `BenchmarkFlowApi` | the New Benchmark widget; the Resume widget; the Main Window |
| `ReadinessService` | the status-bar health dot; the New Benchmark widget gating |
| `InferenceActivityStore` | the Benchmark Pipeline (`BENCHMARK_RUN`); the Run Analysis Service (`JUDGE_ANALYSIS`); the Provider Edit Test Connection probe (`PROVIDER_TEST`); the Readiness Service (`READINESS_PROBE`); the Generate Analysis dialog, the Settings dialog's Test connection button, and the New Benchmark Start button (UI gating reads) |
| `TaskFileLoader` | the run-creation use case |
| `TaskFileValidator` | the Task Editor |
| `YamlFormatter` | the Task Editor; the Task File Loader |
| `AdaptiveTimeoutService` | the Benchmark Pipeline (dispatcher thread); the Progress widget stability indicator receives its state via the adapter, not by calling this service |
| `ProviderCircuitBreaker` | the Benchmark Pipeline |
| `WorkspaceController` | the Main Window; the workspace switcher |
| `NotificationService` | every widget controller |
| `NativePickers` | the export flows (Save picker); the Task Editor (Open File / Open Folder / New File); the Settings dialog (Export / Import / Task Editor folder picker) |
| `Clipboard` | the Result widget (Copy as Markdown, per-field copy affordances); the Settings dialog (Copy path) |
| `FileSystemActions` | the Result widget (Open Exports Folder); the Resume widget (Show run-log file); the Settings dialog (the three Open-folder buttons) |
| Redaction functions | every log call site; every export writer; every diagnostic surface |

The full method-by-method service index, including which concrete class implements each contract and which test double fakes it, is in `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`.
