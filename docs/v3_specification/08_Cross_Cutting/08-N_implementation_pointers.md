# Implementation Pointers

**Status:** Draft
**Owner:** arch
**Audience:** arch, coder
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-A_architecture_principles.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `10_Domain_and_Data/`, `11_Services_and_Algorithms/`, `16_Engineering_Standards/`

This document bridges the *what* of the specification to the *how* of engineering. For each major engineering concern — architecture and layering, module organisation, persistence, concurrency, error handling, logging, state management, settings, testing, continuous integration, and packaging — it gives a one-paragraph orientation and a **See (binding):** pointer to the engineering-standards document in `16_Engineering_Standards/` that actually carries the rule, plus the behavioural spec folders that depend on it. This document is a navigation aid, **not** a binding contract: nothing here is normative on its own — every binding rule lives in the document named by its **See (binding):** line (an exact filename in `16_Engineering_Standards/`, `08_Cross_Cutting/`, or `10_Domain_and_Data/`, per the concern — SPEC-115). The engineering standards are self-contained inside this specification at `16_Engineering_Standards/`; this document references no material outside `App_Specification_Ollama_Bench_Final/`.

---

## Table of Contents

1. How to use this document
2. Architecture and layering
3. Module organisation
4. Persistence
5. Concurrency and threading
6. Error handling
7. Logging and observability
8. State management and the event bus
9. Settings
10. UI construction and theming
11. Testing
12. Continuous integration
13. Packaging and distribution
14. Toolchain and dependency baseline
15. Concern-to-document index

---

## 1. How to use this document

When a story or a widget specification raises an engineering question — "where does this module live?", "how is this error surfaced?", "what is atomic here?" — start here. Find the matching concern below, read the one-paragraph orientation, then open the cited `16_Engineering_Standards/` document for the binding rule and the cited spec folders for the behaviour that exercises it. An architect drafting development notes reads §2, §3, and §8 first; a coder implementing a feature reads the concern that the feature touches; a tester reads §6 and §11.

The `16_Engineering_Standards/` folder re-creates, adapted to this application, the project structure, toolchain, module framework, coding standards, continuous-integration setup, and packaging approach. Everything an implementer needs is inside this specification.

---

## 2. Architecture and layering

The application is a hexagonal (ports-and-adapters) system: a technology-agnostic core of domain types and use cases sits at the centre, services are defined as `Protocol` ports, and concrete adapters (the six SQLite per-aggregate stores, the per-provider LLM clients, the three operating-system Protocols (`NativePickers`, `Clipboard`, `FileSystemActions`), the PySide6 widgets) implement those ports at the edges. Dependencies point inward only — the core never imports an adapter, and the user interface never reaches past a port. A single manual composition root wires every concrete adapter to its port at startup; there is no dependency-injection framework and no service locator. The layering is enforced mechanically by an import-linter contract, `ruff`, `mypy --strict`, and architecture tests, so a layering violation fails the build rather than being caught in review.

**See (binding):** `08_Cross_Cutting/08-A_architecture_principles.md` (hexagonal layering, the composition root, the enforcement stack).

**Behavioural spec:** `08_Cross_Cutting/08-A_architecture_principles.md` records the invariants; `08_Cross_Cutting/08-E_interfaces_contracts.md` defines the service ports; `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` lists every port and its adapter.

**Consult when:** designing any new public API, introducing any new service, or placing a new module in the layer graph.

---

## 3. Module organisation

The codebase is packaged feature-first: the top level is a set of feature packages, and each feature is internally layered to a depth that matches its complexity, with larger features containing sub-features. A module presents a small, deliberate public surface — typically a factory function and its supporting types — and keeps everything else in an internal area. A feature is split into sub-modules when its public surface or its internal code grows past the size thresholds in the standard. Every module that can be tested in isolation declares a colocated test target; the module inventory records, per module, its path, purpose, public entry point, dependencies, and test target.

**See (binding):** `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` (feature-first packaging, the per-module public-surface conventions, the split thresholds).

**Behavioural spec:** `14_Process_and_Traceability/01_MODULE_INVENTORY.md` is the master module list; each widget folder's `implementation_structure.md` applies the module framework to that widget.

**Consult when:** creating a new module, deciding whether to split a growing module, or defining a module's public API.

---

## 4. Persistence

All persistent state lives in a single SQLite database in the application-data folder, opened in write-ahead-logging mode with foreign keys enforced. Access is mediated by six per-aggregate persistence Protocols — `RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`, `ModelCapabilitiesStore`, and `AppSettingsStore` — each owning the SQL of its own aggregate root. The core and the use cases never issue SQL directly; they consume the focused store Protocols. Cross-boundary records are `msgspec.Struct` values, and the schema maps them to flat columns for anything queried or sorted and to encoded blobs otherwise. There is no data-migration framework (DD-53): the database carries a schema-version marker, within a major version the schema evolves through purely structural additive steps applied at startup (existing rows never updated, backfilled, or converted), a newer-than-app or cross-major version at startup is a hard error, and a new major version uses a fresh database. On startup a crash-recovery sweep — owned by `ResultsStore.recover_in_flight_results` — reconciles any run left in a non-terminal state by an interrupted process.

**See (binding):** `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (and its mirror `08_Cross_Cutting/08-O_persistence_schema.md`) — the database location, pragmas, and the additive-structural-steps / no-data-migration policy (DD-53).

**Behavioural spec:** `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` is the binding DDL; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` defines the records the schema maps; `10_Domain_and_Data/07_FILE_LAYOUT.md` fixes the on-disk layout; `12_Quality_and_NFRs/04_ERROR_RECOVERY.md` covers the recovery sweep and corruption handling.

**Consult when:** adding a table or column, changing a record that is persisted, or touching crash recovery.

---

## 5. Concurrency and threading

The backend is **synchronous and Qt-free** (it imports no Qt symbol and no `asyncio`). Long-running work — benchmark inference, judge calls, embedding calls, CPU-bound aggregation — runs as blocking units on `QThreadPool` worker threads via the adapter's `TaskRunner` port; the GUI thread handles only UI events and marshalled results. A single framework-agnostic cancellation token (backed by `threading.Event`) is threaded through the pipeline so a Stop or a Pause halts work at a clean boundary: each in-flight unit finishes and is saved, then the dispatcher (a single dedicated adapter-owned thread, DD-38) stops submitting, leaving no stale threads and a fully resumable state. Backend→UI notifications travel on the Qt-free event bus and are marshalled onto the GUI thread by the adapter. Cross-thread shared state is limited to the inference-activity gate and the single DB writer, each with one `threading.Lock`. Per-`(provider, model)` timeouts are governed by the adaptive-timeout service rather than a global wall-clock cap. (Per D-R-01, which supersedes the earlier `asyncio`/`qasync` draft.)

**See (binding):** `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` — the synchronous-backend + `TaskRunner` (QThreadPool) model, the cancellation-token contract, the thread-boundary rules, and the anti-patterns. The scheduling algorithm is in `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`.

**Behavioural spec:** `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` specifies the model in detail; `08_Cross_Cutting/08-B_benchmark_state_machine.md` and `04_Progress_Widget/` describe pause, stop, and resume behaviour; `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` covers the timeout model.

**Consult when:** adding background work, wiring cancellation into a new operation, or touching pause/stop/resume.

---

## 6. Error handling

Every error is an instance of the application's own categorised error taxonomy. Adapters at the system edge — each provider client, every persistence store, every operating-system adapter (`NativePickers`, `Clipboard`, `FileSystemActions`) — wrap provider-specific and library-specific exceptions into application error types at the first point the failure can occur, so no external exception type ever propagates into the core. Each leaf error category maps to a defined user-experience response (toast, inline message, dialog, or status indicator) and to a result terminal status where applicable. Secrets are kept out of error messages by passing every SDK exception's message string through `redact(text)` at the adapter boundary before placing it on `AppError.message`; from that wrap point the message flows through display, logs, exports, and the clipboard without further redaction. The structlog processor on the `app.*` log namespace is a second-line defence against secrets that bypass the adapter wrap (third-party SDK debug output, traceback frames). See `10_Domain_and_Data/08_REDACTION_PATTERNS.md` for the **two-surface** scope (the support-bundle surface was removed with crash reporting per D-R-17 — DD-31 as superseded).

**See (binding):** `16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md` and `16_Engineering_Standards/03_CODING_STANDARDS.md` (the taxonomy shape, the wrap-at-the-edge rule, the redaction rule).

**Behavioural spec:** `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` defines the hierarchy and the per-category user-experience dispatch; `11_Services_and_Algorithms/18_RETRY_POLICY.md` covers retry behaviour; `10_Domain_and_Data/08_REDACTION_PATTERNS.md` defines redaction; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ErrorKind`) maps categories to result statuses.

**Consult when:** adding an adapter, introducing a new failure mode, or surfacing an error in the UI.

---

## 7. Logging and observability

The application keeps two independent log streams. The Run Log is per-run and user-facing: one file per run, always recording the full verbose stream, displayed live in the Progress widget at a user-selectable field density. The App Log is per-application-lifetime and diagnostic: a single rotating file, level-filtered, not shown in the user interface. Logging is structured, and every log record passes through the single redaction module before it is written, so no secret reaches a log file. The application log is the local diagnostic record; the user may choose to share it manually when reporting a bug.

**See (binding):** `16_Engineering_Standards/06_LOGGING_STANDARD.md` (and `12_Quality_and_NFRs/03_OBSERVABILITY.md`) — the two-stream model, structured logging, rotation policy.

**Behavioural spec:** `12_Quality_and_NFRs/03_OBSERVABILITY.md` specifies the streams, file locations, and rotation; `04_Progress_Widget/description.md` covers the live Run Log panel and verbosity; `11_Services_and_Algorithms/15_LOG_FORMATTING.md` covers event-to-display rendering; `10_Domain_and_Data/07_FILE_LAYOUT.md` fixes the log file paths.

**Consult when:** adding a logged event or changing log verbosity.

---

## 8. State management and the event bus

Cross-widget communication uses two distinct mechanisms with two distinct purposes. Durable cross-widget *state* — the selected run, the active workspace, readiness, filter state — lives in scoped reactive state stores that widgets observe and that re-render their observers on change. One-shot *domain events* — a run started, a task completed, an analysis received — travel on a typed event bus; each payload is a frozen `msgspec.Struct`. A widget never reaches into another widget; it reads a store or subscribes to an event. The adapter layer marshals every signal that crosses the worker→GUI thread boundary onto the GUI thread via a queued signal/slot connection.

**See (binding):** `08_Cross_Cutting/08-A_architecture_principles.md` §6–§12 and `08_Cross_Cutting/08-J_event_bus_catalog.md` (the store/event split, the adapter marshalling rule).

**Behavioural spec:** `08_Cross_Cutting/08-J_event_bus_catalog.md` catalogues every event and its payload; `08_Cross_Cutting/08-E_interfaces_contracts.md` defines the store ports; each widget folder's `description.md` lists the stores it observes and the events it emits or subscribes to.

**Consult when:** adding a cross-widget signal, introducing a new shared state value, or deciding between a store and an event.

---

## 9. Settings

Settings are resolved through a layered hierarchy: bundled defaults at the base, persisted user values above them, and a frozen per-run snapshot taken at run creation. The pipeline reads every setting from the run's snapshot, never from the live values, so a settings change can never alter a run already in progress. Settings keys are a registered, typed catalogue with documented defaults; persistence is through the `AppSettingsStore`'s `app_settings` table, with typed reads/writes mediated by `SettingsService` and the per-run snapshot built by `RunSnapshotBuilder.build_snapshot()` at run start. The Settings dialog is unreachable while any run is non-terminal, which keeps the snapshot contract intact.

**See (binding):** `08_Cross_Cutting/08-C_settings_hierarchy.md` and `08_Cross_Cutting/08-G_feature_flags.md` (the registered-key catalogue, typed accessors, the snapshot mechanism).

**Behavioural spec:** `08_Cross_Cutting/08-C_settings_hierarchy.md` defines the layering and the merge order; `08_Cross_Cutting/08-G_feature_flags.md` is the key catalogue; `06_Settings_Dialog/` specifies the editing surface; `08_Cross_Cutting/08-F_spec_issues_log.md` (DD-03) records the unreachable-during-run decision.

**Consult when:** adding a setting key, changing a default, or touching the per-run snapshot.

---

## 10. UI construction and theming

Widgets are built programmatically with Qt Widgets through PySide6; the application uses no QML. Each widget feature exposes a factory function and follows a view-model and controller split — a frozen `msgspec.Struct` view-model holds the displayed state and a controller computes derived state from store subscriptions. All visual styling is generated from a typed design-token set by a single theme module; direct stylesheet calls are forbidden outside that module. Both a dark and a light theme are defined in full, and the theme follows the operating-system colour scheme when set to do so.

**See (binding):** `08_Cross_Cutting/08-L_ui_standardization.md` and `08_Cross_Cutting/08-D_color_palette_and_typography.md` (programmatic Qt Widgets, the factory and view-model/controller pattern, the theme-module rule).

**Behavioural spec:** `08_Cross_Cutting/08-L_ui_standardization.md` fixes the visual patterns; `08_Cross_Cutting/08-D_color_palette_and_typography.md` defines the tokens and the contrast matrix; each widget folder's `implementation_structure.md` applies the factory and controller pattern; `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` sets the accessibility floor.

**Consult when:** building a new widget, adding a styled element, or changing a theme token.

---

## 11. Testing

Tests are layered. Pure logic — the domain core, the use cases, the algorithms — is unit-tested against the service ports using the in-memory fakes each adapter module provides. Widgets are tested with `pytest-qt` driving the real Qt event loop. The six per-aggregate persistence stores and other adapters have integration tests against their real backing technology. Architecture tests assert the layer graph, complementing the import-linter contract. A test exists for every edge case and every error category, so the edge-case catalogue and the error taxonomy are both verifiable rather than aspirational.

**See (binding):** `16_Engineering_Standards/` — *Testing Standard* (the test layers, `pytest`/`pytest-qt`, the fakes convention, architecture tests).

**Behavioural spec:** `08_Cross_Cutting/08-I_edge_cases.md` is the edge-case catalogue; `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` maps each edge case to a test pattern; `11_Services_and_Algorithms/` algorithm documents each end with a test-case list; each widget folder's `description.md` carries a function inventory for test traceability.

**Consult when:** deciding a test boundary for a new module, or writing tests for an edge case or error path.

---

## 12. Continuous integration

Continuous integration runs the full enforcement stack on every change: `ruff` for linting and formatting, `mypy --strict` for typing, the import-linter contract for layering, the architecture tests, and the `pytest` suite across the supported platforms. The pipeline is gated — a failure in any stage blocks the merge — and is configured to cancel superseded in-progress runs to bound build-minute consumption. Release builds additionally produce the distributable artifacts.

**See (binding):** `16_Engineering_Standards/` — *Continuous Integration Standard* (the pipeline stages, the gating policy, the platform matrix).

**Behavioural spec:** `16_Engineering_Standards/07_TESTING_STANDARD.md` defines the test tiers and coverage targets the pipeline enforces; `13_Distribution_and_Release/06_VERSIONING_POLICY.md` covers release tagging; `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` tracks build-resource risks.

**Consult when:** adding a pipeline stage, changing the platform matrix, or adjusting a quality gate.

---

## 13. Packaging and distribution

The application is packaged as a desktop application for macOS, Windows, and Linux. The build backend is `uv_build`, uv's native build backend. Distribution is unsigned: the specification documents the operating-system first-run experience for unsigned software on each platform rather than acquiring signing certificates. On Windows the application is distributed as a portable archive with no installer. The application has no auto-update mechanism (DD-36); users update by downloading a new artifact from the GitHub Releases page and replacing the existing installation.

**See (binding):** `16_Engineering_Standards/` — *Packaging and Build Standard* (the `uv_build` backend, per-platform packaging, the unsigned-distribution approach).

**Behavioural spec:** `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` defines the supported platforms; `13_Distribution_and_Release/02_INSTALLATION.md` and `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md` cover installation and the unsigned first-run experience.

**Consult when:** changing the packaging of a platform target, or working on the build or update flow.

---

## 14. Toolchain and dependency baseline

The application targets Python 3.13 with PySide6 for the user interface, and uses `uv` for environment and dependency management. The supporting libraries include `msgspec` for cross-boundary records and serialisation, `psygnal` for reactive signals, `structlog` for structured logging, and SQLite in write-ahead-logging mode for persistence. Concurrency uses the standard library (`threading`, `concurrent.futures`) plus Qt's `QThreadPool` in the adapter layer — there is no `asyncio` and no `qasync` (D-R-01). The policy is to track the latest stable version of every dependency at the time of work; the specification records those versions in a consolidated version table and keeps it current.

**See (binding):** `16_Engineering_Standards/` — *Toolchain and Dependency Standard* (the consolidated version table, the latest-stable policy, the `uv` workflow).

**Behavioural spec:** `08_Cross_Cutting/08-A_architecture_principles.md` records the stack as an invariant; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` reflects the `msgspec` record conventions; `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` tracks stack-stability risks.

**Consult when:** adding or upgrading a dependency, or verifying the supported Python version.

---

## 15. Concern-to-document index

| Engineering concern | Binding standard in `16_Engineering_Standards/` | Primary behavioural spec |
|---|---|---|
| Architecture and layering | Project Architecture | `08-A`, `08-E`, `11_Services_and_Algorithms/01` |
| Module organisation | Project Structure and Module Framework | `14_Process_and_Traceability/01` |
| Persistence | Persistence and Data Storage Standard | `10_Domain_and_Data/03`, `/02`, `/07` |
| Concurrency and threading | `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` | `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`, `08-B` |
| Error handling | Error Handling and Coding Standards | `11_Services_and_Algorithms/17`, `/18`, `10_Domain_and_Data/08` |
| Logging and observability | Logging and Observability Standard | `12_Quality_and_NFRs/03`, `04_Progress_Widget/` |
| State management and event bus | State Management and UI-Backend Communication Standard | `08-J`, `08-E` |
| Settings | Configuration and Settings Standard | `08-C`, `08-G`, `06_Settings_Dialog/` |
| UI construction and theming | UI Construction and Styling Standard | `08-L`, `08-D` |
| Testing | Testing Standard | `08-I`, `14_Process_and_Traceability/06` |
| Continuous integration | Continuous Integration Standard | `16_Engineering_Standards/07`, `16_Engineering_Standards/08` |
| Packaging and distribution | Packaging and Build Standard | `13_Distribution_and_Release/` |
| Toolchain and dependencies | Toolchain and Dependency Standard | `08-A`, `15_Risks_and_Open_Questions/01` |
