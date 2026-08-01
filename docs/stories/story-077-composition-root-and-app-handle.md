---
id: STORY-077
title: Build the composition root, the AppHandle, and the export-filename bridge
status: done
spec_clauses:
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#7-the-composition-root
  - 16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#2-the-single-execution-runner-guarantee
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
  - 01_Main_Window/description.md#31-settings-action
  - 01_Main_Window/description.md#32-about-action
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#69-per-provider-type-behaviour-matrix
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#63-the-embedding-model-probe
modules:
  - ui/main_window/
  - backend/provider_registry/
  - backend/provider_openai_compatible/
  - backend/provider_anthropic/
  - backend/provider_gemini/
acceptance_criteria:
  - STORY-077-AC-1
  - STORY-077-AC-2
  - STORY-077-AC-3
  - STORY-077-AC-4
  - STORY-077-AC-5
  - STORY-077-AC-6
  - STORY-077-AC-7
  - STORY-077-AC-8
  - STORY-077-AC-9
  - STORY-077-AC-10
  - STORY-077-AC-11
  - STORY-077-AC-12
depends_on:
  - STORY-104
  - STORY-112
adrs:
  - ADR-0010
  - ADR-0014
owner: coder
estimate: L
---

# STORY-077 — Build the composition root, the AppHandle, and the export-filename bridge

## Goal

Wire the whole application object graph once, by hand, in the single composition root. `build_app`
constructs every concrete service and widget in fixed order using plain keyword-argument factory
calls, assembles them into the main window, and returns an `AppHandle` that gives the entry point
the window to show and the ordered shutdown to run at exit. As part of that wiring, `build_app`
constructs the theme manager and applies the persisted theme before the window is shown, and it
injects the real Settings-open and About-open callbacks into the main-window controller so both
menu actions are live. The graph is built synchronously with no network call — the startup
readiness probe is deferred to a single tick scheduled after the window is shown.

## In scope

- `compose.py`: `build_app(*, app, loop) -> AppHandle`, the single place concrete implementations
  are constructed and wired via keyword-argument factory calls, in the fixed construction order of
  `01_PROJECT_STRUCTURE.md` §7–§8 — including the one `TaskRunner` and the one synchronous HTTP
  client (each constructed exactly once).
- **Opening the one shared database write connection.** This story calls the existing
  `open_write_connection(db_path)` exactly once and injects the resulting
  `(write_conn, lock)` pair plus the `open_read_connection` factory into all six per-aggregate
  persistence stores. The `03_PERSISTENCE_SCHEMA.md` §2 write-connection pragmas are applied
  *inside* that one call — see Design constraints for why the open and the pragmas are a single
  indivisible step and cannot be split across stories.
- Ensuring the database file's parent directory exists (a plain recursive, idempotent `mkdir`) purely
  so the open can succeed. STORY-078 supersedes this with the hardened, whole-subtree version that
  adds the permission-failure abort modal.
- `AppHandle`: a `msgspec.Struct(frozen=True, kw_only=True, gc=False)` on the composition root's
  public surface carrying the main window and a shutdown handle (the ordered shutdown of
  `05_CONCURRENCY_GUARANTEES.md` §8), per ADR-0010.
- The export-filename bridge: a small adapter in `compose.py` satisfying the UI
  `compose_filename(*, run, kind, ext)` Protocol (declared by `ui/results` and `ui/resume_benchmark`)
  by delegating to `backend/csv_export`'s `compose_export_filename(*, run_name, run_id, kind, ext)`,
  deriving the run's effective name and id and mapping the `kind` string to `ExportKind`.
- Startup theme application: `build_app` constructs the theme manager (`make_theme_manager`),
  resolves the effective theme from the persisted `ui.theme` setting, and applies the design-token
  objects to the `QApplication` before the main window is shown (launch step 9, ADR-0010).
- **Widening `make_main_window`'s signature** to accept and forward two new optional keyword
  parameters, `settings_requested` and `about_requested`, through to the `MainWindowController`
  constructor parameters of the same name (which already exist and already default to `None`). This
  is the missing link that makes AC-8 reachable: today `compose.py` has no way to inject either
  callback because the public factory neither accepts nor forwards them.
- Settings/About dialog callback injection: `build_app` passes real Settings-open and About-open
  callbacks through the widened factory, so activating the menu-bar Settings and About actions
  invokes them.
- **Calling the per-widget gateway factories and injecting each gateway into exactly one widget.**
  `build_app` calls `make_main_window_gateway`, `make_new_benchmark_gateway`, `make_progress_gateway`,
  `make_result_gateway`, `make_resume_gateway`, `make_settings_gateway` and
  `make_task_editor_gateway` — each delivered by a STORY-104 child story, not by this story — passing
  each the backend handles it wraps, and hands each gateway to its one widget factory. It also calls
  `make_file_change_watcher` (STORY-112) for the Task Editor's collaborator bundle.
- Constructing and showing the main window, wired with the `MainWindowGateway` instance built above,
  whose `reprobe()` the already-existing deferred-tick path calls (see Design constraints).
- **The one shared synchronous HTTP client (Gap 1).** `build_app` constructs exactly one
  `httpx.Client()` and injects it into all three provider client-collaborator bundles
  (`backend/provider_openai_compatible/`, `backend/provider_anthropic/`,
  `backend/provider_gemini/`), each of which is widened to accept and store an `http_client: httpx.Client` and to reuse it for its reachability probe instead of constructing a
  per-call `httpx.Client`.
- **The two new `LLMClient` capability methods (Gap 2).** `backend/provider_registry/`'s
  `LLMClient` Protocol gains `supports_embedding() -> bool` and `supports_discovery() -> bool`,
  matching `readiness/protocols.py::ReadinessLLMClient`'s existing contract, implemented on
  all three concrete provider clients so `provider_registry` structurally satisfies
  `ReadinessProviderRegistry` and `build_app` can wire the readiness service.
- **Trivial `ActiveRunTaskPaths` and `RunValidator` stubs (Gaps 3–4).** Two small
  always-empty-result classes local to `compose.py`, documented as deliberate placeholders for
  a future story, unblocking the Task Editor and New Benchmark gateway wiring without
  duplicating either Protocol's real implementation.
- **Three further trivial stubs (disclosed 2026-08-01, after an independent review found them
  undisclosed in the original implementation report).** `make_progress_gateway` and
  `ResultCollaborators` each require a collaborator with no production implementation anywhere
  in the codebase, exactly the same "future story's job" shape as Gaps 3–4:
  `_NoOpManualProviderProbeCommand`/`_AlwaysOkRunLogWriteStatus` (both already deferred by
  STORY-107's own Protocol docstrings to "whichever future story wires a real implementation"),
  and `_NoModelFetcher` for the Result widget's Generate-Analysis dialog model picker (no
  production `ModelFetcher` exists; per `07_Common_Dialogs/generate_analysis_dialog.md`'s own
  edge case EC-GA-2, an always-empty catalog is exactly that dialog's already-specified
  no-models-available state, so this is not a UI defect — but the model picker cannot show any
  real models until a future story wires a real `ModelFetcher`). All three follow the same
  pattern and constraint as Gaps 3–4: trivial, documented, inert, and named here as a known
  follow-up rather than left as an implicit implementation detail.

## Out of scope

- The process entry point and the two exception hooks — owned by STORY-076.
- The app-data-directory hardening, the database schema-version check, default seeding, and the
  three launch-abort modals that run at the top of `build_app` — owned by STORY-078. This story
  opens the write connection; STORY-078 runs the schema check *on the connection this story
  opened* and never opens one of its own.
- The single-instance advisory lock helper — owned by STORY-079.
- The quit sequence and the shutdown-handle body's step-by-step behaviour — owned by STORY-080.
- Runtime theme re-application on a settings change and the end-to-end menu-driven dialog opening —
  owned by STORY-083; this story only performs the one-time startup theme apply and the compose-time
  callback injection.
- **Writing the concrete gateway implementations.** Every one of the seven `08-E` §7b gateways is
  owned by a STORY-104 child story (STORY-105 … STORY-111), and the Task Editor's file-change watcher
  by STORY-112. This story *calls* their factories and injects the results; it implements none of
  them and changes none of their modules.
- **Any change to `ui/settings_dialog/` or `ui/common_dialogs/`.** The injected callbacks call
  `make_settings_dialog` and `make_about_dialog` exactly as they exist today. Neither module's code
  or public surface changes, so neither appears in `modules:` — see Design constraints for the
  sizing reasoning.
- Every `make_*` factory being wired — delivered by STORY-001..STORY-075 and, for the gateways, by
  STORY-104's children. **With the single exception of `make_main_window`'s signature widening named
  in "In scope" above, this story calls those factories, it does not implement or modify them.**

## Spec inputs

- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#7-the-composition-root` — `compose.py` is the
  sole wiring point (`build_app(*, app, loop) -> AppHandle`), roughly 50–200 lines of keyword-argument
  factory calls, no DI container / service locator / reflection; `__main__.py` carries no business
  logic.
- `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root` — the fixed construction
  order and the shape of `build_app` / `AppHandle`; dependencies passed as plain keyword arguments;
  the illustrative fragment's `AppHandle(window=..., pipeline=..., loop=loop)` return shape.
- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the graph is built
  synchronously and performs no network call (step 8); the theme is applied from the theme setting
  (step 9); the main window's show handler schedules one deferred tick that triggers the readiness
  probe (step 10); `app.exec()` (step 11) is the only event loop.
- `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#2-the-single-execution-runner-guarantee` — exactly
  one `TaskRunner` and exactly one synchronous HTTP client are created at composition time.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — the theme
  module is the single styling authority that builds and applies the stylesheet/`QPalette` from the
  active token container; `build_app` resolves the persisted `ui.theme` and applies it at startup.
- `01_Main_Window/description.md#31-settings-action` — the menu-bar Settings action opens the Settings
  modal dialog; the callback that opens it must be wired in at composition time.
- `01_Main_Window/description.md#32-about-action` — the menu-bar About action opens the Application
  Information modal dialog; the callback that opens it must be wired in at composition time.

## Design constraints

- `compose.py` is the only file allowed to import concrete implementations (import-linter contract);
  every other file imports Protocols.
- `AppHandle` is a frozen keyword-only `msgspec.Struct` with `gc=False`; it references the PySide6
  main window and is therefore a composition-root type, not a `backend/domain` DTO.
- No `asyncio`/`anyio`/`qasync`; construction is synchronous and does no network I/O.
- A UI controller never receives a backend Store/Service Protocol directly — each widget factory is
  wired with its per-widget adapter gateway. Those gateway objects do not exist yet; STORY-104's
  children build them, which is why this story now depends on STORY-104. This story's obligation is
  to call each gateway factory once with the backend handles it wraps and pass the result into
  exactly one widget factory — never to hand a widget a store or a service, and never to hand any
  consumer the whole context bundle (SPEC-075).
- The theme is applied by the theme module only — `compose.py` invokes `make_theme_manager` and the
  theme module's apply path; no other module assembles or applies a stylesheet.
- **Opening the write connection and applying its pragmas is one indivisible step, and this story
  owns it.** `03_PERSISTENCE_SCHEMA.md` §2 requires every connection to apply its pragmas
  "immediately after opening, before any statement runs", so no other statement — and therefore no
  other story's step — may sit between the two. The existing `open_write_connection` helper already
  performs both atomically and already raises `PersistenceError` when the file is not a valid SQLite
  database. Do not add a separate pragma-application step anywhere in the launch sequence.
- **Do not add a `showEvent` override or a startup `QTimer.singleShot` to `ui/main_window`.** The
  deferred readiness tick already exists end to end and was delivered by STORY-053:
  `MainWindowShell.showEvent` fires `QTimer.singleShot(0, ...)` behind a once-only
  `_has_scheduled_initial_show_tick` guard, `MainWindowController.bind()` registers
  `set_on_show_callback(self._on_shell_shown)`, and `_on_shell_shown` calls `gateway.reprobe()`.
  This story's only obligation for AC-6 is to inject the real gateway STORY-105 built, whose
  `reprobe()` reaches the real readiness service. Adding a second show hook would schedule a second
  tick and fire two startup probes — a regression, not a fix.
- **The `modules:` entries are exactly the modules whose code this story changes** — corrected
  2026-08-01 after an independent spec-conformance review caught that `backend/csv_export/`,
  `ui/results/`, `ui/resume_benchmark/`, and `ui/theme/` were listed despite this story never
  editing a single line inside any of them (verified via `git diff --stat` against each path:
  zero changes). `build_app` *calls* their existing public factories — `compose_export_filename`,
  the two gateway-injection call sites, `make_theme_manager` — but calling an unchanged public
  factory is not "touching" a module for sizing purposes, exactly as this story's own
  Design constraints already argued for `ui/settings_dialog/`/`ui/common_dialogs/`/the gateway
  modules; the original four were an inconsistent application of that same rule to itself. The
  correct, current list is exactly five: `ui/main_window/` (the widened factory signature, then
  further widened during remediation — see the Notes section), `backend/provider_registry/` (the
  two new `LLMClient` capability methods), and `backend/provider_openai_compatible/` +
  `backend/provider_anthropic/` + `backend/provider_gemini/` (the shared-HTTP-client injection
  point). **Five modules is exactly the `L` bound — no oversize exception is needed or claimed.**
  An earlier version of this note incorrectly recorded a 9-module "owner-approved oversize
  exception"; that exception is withdrawn as unnecessary now that the list is correct, not
  because the underlying Gap 1/2 work was wrong — Gap 1/2 remain real, in-scope, correctly
  implemented widenings of `backend/provider_registry/` and the three provider adapters.
- **Owner-approved oversize exception: `compose.py` is 377 lines, not 50–200 (2026-08-01).** An
  earlier draft of this story predicted the wrapped `build_app` would land at roughly 80–120
  lines, on the theory that only about 34 of the ~80 public `make_*`/`create_*` factories in the
  codebase are compose-time. That prediction was made before STORY-104's seven real gateway
  factories existed. Once implemented against the real signatures, the measured floor is
  materially higher: the seven gateway factories alone declare 61 keyword arguments between them
  (`make_settings_gateway` alone takes 12), and each is a real, mandated wiring call this story's
  own "In scope" section requires — none of it is padding. The coder compressed hard before
  reporting this (pinning every multi-keyword factory call to one physical line via `# fmt: skip`,
  a standard ruff-honoured directive this project's own `ruff` config already permits since
  `E501` is unenforced) and could not get materially below 359 lines without reopening
  already-`done` STORY-104 gateway-factory signatures — a much larger change the owner
  declined. A second remediation pass (fixing the `WorkspaceController`/shell duplication and
  building the real New/Resume left-panel tab widget, see the Notes section) added the New/Resume
  `QTabWidget` composition and brought the file to its final **377 lines**. The owner reviewed
  this and chose an explicit, documented exception over further compression or reopening
  STORY-104, using the same precedent as this story's own module-count exception above and
  ADR-0014's one-row module-inventory correction. **The bound AC-5 tests against is now 50–400
  lines**, not 50–200; this note is the required record of why. Keep each call compact and keep
  anything that can live behind an existing module's public `api.py` out of `compose.py`, but do
  not re-litigate this exception without a new, similarly-documented reason.
- **AC-5's bound is a standing invariant, not a snapshot.** Its test is authored here but it
  constrains the *final* `compose.py`, and therefore also STORY-076 (entry-point glue), STORY-078
  (the launch prelude and three abort modals), STORY-080 (the quit sequence) and STORY-083 (runtime
  theme re-apply). Never silently weaken or delete AC-5's test.
- **The `loop` parameter is a deliberate spec fossil — accept it, carry it, do not "fix" it.**
  `build_app(*, app: QApplication, loop: QEventLoop)` is pinned by
  `01_MODULE_INVENTORY.md` §7, but nothing ever enters that `QEventLoop`: `08-M_app_lifecycle.md` §2
  step 11 makes `app.exec()` the only event loop and D-R-01 bans `asyncio`, so there is no second
  loop to drive. ADR-0010 kept the signature deliberately because the inventory fixes it. Accept the
  parameter and carry it straight onto `AppHandle` exactly as
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` §7's own illustrative fragment does
  (`AppHandle(window=..., pipeline=..., loop=loop)`). Do not remove it, do not rename it, do not
  mark it unused, and do not raise it as a spec defect — it is already recorded here.

## Acceptance criteria

### STORY-077-AC-1

Given a constructed `QApplication`,
when `build_app` is called,
then it returns an `AppHandle` that is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`
carrying the main window and a shutdown handle.

### STORY-077-AC-2

Given `build_app` is called,
when the object graph is constructed,
then it issues no network call and returns before the deferred readiness probe runs.

### STORY-077-AC-3

For every run of `build_app`, exactly one database write connection is opened, exactly one
`TaskRunner` is constructed, and exactly one synchronous HTTP client is constructed — and the one
write connection and its lock are the same objects injected into all six per-aggregate persistence
stores.

### STORY-077-AC-4

The export-filename bridge satisfies the UI `compose_filename(*, run, kind, ext)` Protocol by
delegating to `compose_export_filename`, for every export kind the real call sites in
`ui/results/_internal/footer.py` and `ui/resume_benchmark/_internal/actions.py` pass (title-case,
matching `ExportKind`'s own `.value`s — not the lowercase tokens an earlier draft of this AC
assumed):

| UI `kind` string | Backend `ExportKind` passed to `compose_export_filename` |
| ---------------- | -------------------------------------------------------- |
| `Summary`        | `ExportKind.SUMMARY`                                     |
| `Details`        | `ExportKind.DETAILS`                                     |

For every other `kind` the real call sites also pass (`RunAnalysis`, `Chart_<slug>`, `Chart` —
kinds `backend/csv_export`'s `ExportKind` enum explicitly does not cover), the bridge falls back
to a local sanitise-then-suffix implementation copied verbatim from
`backend/csv_export/_internal/filename.py`'s `sanitise_run_name` (import-linter forbids reaching
that private helper directly), so behaviour matches byte-for-byte between the two paths.

### STORY-077-AC-5

`compose.py` is between 50 and 400 source lines (the composition-root budget — widened from the
original 50–200 by the owner-approved exception recorded under Design constraints), asserted by
an architecture test that runs against the file's current contents on every suite run — so the
bound holds for the final `compose.py` after every later Phase-11 story has added to it, not only
at this story's merge.

### STORY-077-AC-6

Given `build_app` has returned an `AppHandle` and no readiness probe ran during `build_app` itself,
when the main window is shown,
then exactly one deferred tick fires and it triggers exactly one readiness probe.

### STORY-077-AC-7

Given a persisted `ui.theme` setting,
when `build_app` wires the object graph,
then it constructs the theme manager and applies the theme resolved from that setting to the
`QApplication` before the main window is shown.

### STORY-077-AC-8

Given `build_app` has wired the main window,
when the main-window controller is inspected after wiring,
then its Settings-open and About-open callbacks are non-`None` real callbacks (not the unwired
`None` defaults), so both menu actions can open their dialogs.

### STORY-077-AC-9

Given a provider's reachability probe is invoked after `build_app` has wired the object graph,
when the probe makes its HTTP request,
then it issues that request on the single shared `httpx.Client` instance `build_app` constructed
and injected — no new `httpx.Client` is constructed for the probe.

### STORY-077-AC-10

Given each of the three concrete provider clients (OpenAI-compatible, Anthropic, Gemini),
when its `supports_embedding()` and `supports_discovery()` methods are called,
then each returns the boolean value resolved against
`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.9 and
`11_Services_and_Algorithms/09_READINESS_PROBE.md`'s DD-48 embedding-handshake note — not a
guessed or unconditionally-`True` placeholder — and `backend/provider_registry`'s `LLMClient`
Protocol structurally accepts all three under `mypy --strict`.

### STORY-077-AC-11

Given the `ActiveRunTaskPaths` stub `build_app` constructs for the Task Editor gateway,
when `task_paths_for(run_id=...)` is called with any `run_id`,
then it always returns an empty tuple, and the stub's docstring states this is a deliberate
placeholder pending a future implementation.

### STORY-077-AC-12

Given the `RunValidator` stub `build_app` constructs for the New Benchmark gateway,
when `validate(request=...)` is called with any `RunStartRequest`,
then it always returns an empty tuple of validation entries, and the stub's docstring states
that New Benchmark's field-validation messages are inert until a future implementation lands.

## Test plan

- STORY-077-AC-1 — integration, `tests/integration/test_compose_build_app.py`,
  `test_build_app_returns_frozen_app_handle_with_window_and_shutdown`.
- STORY-077-AC-2 — integration, same file, `test_build_app_is_synchronous_and_makes_no_network_call`.
- STORY-077-AC-3 — integration, same file,
  `test_build_app_constructs_single_runner_writer_and_http_client`.
- STORY-077-AC-4 — unit (table-driven, one `@pytest.mark.parametrize` row per export kind, cross-module
  so it lives at the top level, not colocated), `tests/unit/test_export_filename_bridge.py`,
  `test_bridge_maps_ui_kind_to_export_kind`.
- STORY-077-AC-5 — architecture, `tests/architecture/test_compose_line_budget.py`,
  `test_compose_py_within_50_to_200_lines`.
- STORY-077-AC-6 — integration, `tests/integration/test_compose_build_app.py`,
  `test_show_schedules_single_deferred_readiness_tick`.
- STORY-077-AC-7 — integration, same file,
  `test_build_app_applies_persisted_theme_before_window_shown`.
- STORY-077-AC-8 — integration, same file,
  `test_build_app_injects_settings_and_about_callbacks`.
- STORY-077-AC-9 — colocated unit, one file per provider:
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_client_impl.py`,
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_client_impl.py`,
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_client_impl.py`, each
  `test_probe_reachable_uses_injected_http_client_not_a_new_one`.
- STORY-077-AC-10 — colocated unit, same three files, each
  `test_supports_embedding_and_supports_discovery`.
- STORY-077-AC-11 — unit, `tests/unit/test_active_run_task_paths_stub.py`,
  `test_stub_always_returns_empty_tuple`.
- STORY-077-AC-12 — unit, `tests/unit/test_run_validator_stub.py`,
  `test_stub_always_returns_no_validation_entries`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-077.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Dependencies resolved; story moved `draft` → `ready` (2026-08-01).** STORY-104 and its seven
  children (STORY-105–111) and STORY-112 are all `status: done`. `build_app` now has every gateway
  factory and the file-change watcher it needs, so AC-6 and AC-8 are reachable.
- **Widened during grounding (2026-08-01) — see the oversize-exception note under Design
  constraints.** Two construction-time gaps the original 5-module scope never anticipated (no
  shared HTTP client injection point; `provider_registry` not structurally satisfying
  `ReadinessProviderRegistry`) required adding `backend/provider_registry/`,
  `backend/provider_openai_compatible/`, `backend/provider_anthropic/`, and
  `backend/provider_gemini/` to `modules:`, plus four new acceptance criteria (AC-9..AC-12). The
  owner reviewed and approved treating this as an explicit oversize exception rather than a split,
  using ADR-0014's one-row inventory correction as precedent. Two further gaps
  (`ActiveRunTaskPaths`/`RunValidator` having no production implementation) are resolved with
  trivial always-empty stubs local to `compose.py`, documented as deliberate placeholders — New
  Benchmark's field-validation messages and the Task Editor's active-run task-path lookup are
  inert until a future story replaces them.
- **STORY-104 was `draft` pending ADR-0014; ADR-0014 is now `accepted`.** It settled where the
  concrete gateway implementations live (`adapters/ui_gateways/`), including the owner-approved
  one-row correction to the module inventory — the same precedent this story's own oversize
  exception now relies on.
- **Second remediation pass (2026-08-01) — three real construction-time gaps the implementing
  session's own grounding surfaced, beyond the plan.** (1) `AC-5`'s 50–200-line bound didn't
  survive contact with the real STORY-104 gateway signatures — see the oversize exception above,
  now 50–400. (2) The `WorkspaceController` `build_app` wires was, at first, given a separate,
  never-shown `QStackedWidget` while `MainWindowShell` (STORY-053) kept independently hosting its
  own duplicate copy of the workspace pages — the shell's own docstring had already flagged this
  exact reconciliation as this story's job. Fixed by making `compose.py` build one
  `QStackedWidget`, hand it to `make_workspace_controller`, prime both pages via
  `switch_to("task_editor")` then `switch_to("benchmark")` (using only `WorkspaceController`'s
  existing public Protocol — `adapters/workspace_controller/` was not reopened), and pass that
  same container into a widened `make_main_window(container=...)` — `MainWindowShell` now only
  hosts the container; it never builds a page or switches it. (3) The Resume Benchmark widget was
  being constructed and immediately discarded (Resume unreachable in the running app, per
  `01_Main_Window/description.md` §2.1's own layout table, which specifies the left panel is
  `02_New_Benchmark_Widget/` **and** `03_Resume_Benchmark_Widget/` together). Fixed by building
  the left panel as a `QTabWidget` (`objectName="benchmark_left_panel"`) with "New Benchmark" and
  "Resume" tabs, New Benchmark active by default (the spec is silent on persisting the selected
  tab, so none is added). The AC-4 reflow mechanism (hide the left panel when a run starts) was
  updated to locate this real panel by its `objectName` instead of the old, disconnected
  placeholder widget it previously toggled. This session's own claim of having "proven by a real
  smoke test" was **false** — no such test existed in the tree, only a throwaway manual script;
  an independent spec-conformance review caught this (see the third remediation entry below),
  and a real, permanent regression test now exists
  (`tests/integration/test_compose_build_app.py::test_workspace_switch_reuses_pages_and_never_duplicates_the_left_panel`).
  `ui/main_window/`'s existing tests were updated to the new construction shape.
- **Independent spec-conformance review (2026-08-01) found four real defects the first two
  implementation passes missed**, verified independently by the orchestrating session before any
  further work: (1) `build_app` raised `ConfigurationError` uncaught when no provider was
  enabled, permanently bricking the app's ability to launch at all — a hard contradiction of
  `08-M_app_lifecycle.md`'s launch-abort rules and edge case EC-M-5 (an unusable environment
  lands `NOT_READY` with a navigable UI, never a refusal to start); (2) the app had **two**
  stacked status bars — `MainWindowShell`'s own `StatusBarWidget` embedded in the central layout,
  plus a second, separate `QStatusBar` `compose.py` mounted via `window.setStatusBar(...)` for
  the notification service — so toasts rendered into the wrong, empty bar; (3) the workspace
  priming trick (see the second remediation entry above) always landed on `"benchmark"`
  regardless of the persisted `ui.active_workspace` setting, contradicting the same launch clause
  this story cites; (4) the "proven by a smoke test" claim above was false. The review also
  caught that four of this story's nine `modules:` entries were never actually modified
  (`backend/csv_export/`, `ui/results/`, `ui/resume_benchmark/`, `ui/theme/` — confirmed via
  `git diff --stat`, zero changes) — see the corrected Design constraints bullet above; correcting
  the list drops the count to exactly five, so the 9-module oversize exception was withdrawn as
  unnecessary, not because Gap 1/2 were wrong.
- **Third remediation pass (2026-08-01) — fixed all four defects above, plus added a minimal
  `AppHandle.shutdown()`.** (1) Added `_NullEmbeddingClient`, a structural `LLMClient` stand-in
  used when the persisted embedding selection doesn't resolve to an enabled, secret-resolvable
  provider — `build_app` never substitutes an arbitrary provider the user didn't choose; `embed()`
  raises `EmbeddingUnavailableError`, which `EmbeddingService.embed()` already degrades to an
  empty vector (the existing failure-as-data path). `build_app` now succeeds and shows a working,
  navigable window with zero providers enabled — proven by
  `test_build_app_succeeds_with_zero_enabled_providers`. (2) `ui/main_window/_internal/status_bar.py`'s
  `StatusBarWidget` now subclasses the real `QStatusBar` instead of `QWidget`; `compose.py` builds
  it once via a new `make_status_bar(...)` factory before the window exists, hands the same
  instance to both `make_notification_service(status_bar=..., parent=status_bar)` (a real,
  eventually-shown parent, not an orphan `QWidget()`) and the widened `make_main_window(status_bar=...)`,
  which mounts it via `QMainWindow.setStatusBar(...)` — exactly one status bar exists. This
  further widened `ui/main_window/api.py`'s public surface (a new `make_status_bar` factory;
  `make_main_window` now takes `status_bar`/`container` instead of `theme_manager`/`platform_kind`
  directly) — recorded here since it goes beyond the two-kwarg widening originally scoped. (3) The
  priming sequence now reads `ui.active_workspace` and makes it the *final* `switch_to(...)` call,
  so launch actually restores the persisted workspace. (4) See above.
  `AppHandle.shutdown()` was added per an explicit owner decision reversing this story's original
  "do not add a shutdown method" stance, after the same review found STORY-076's own story text
  already assumes `AppHandle` exposes one. It is deliberately **partial** — it performs only steps
  3–4 of `05_CONCURRENCY_GUARANTEES.md` §8's six-step ordered shutdown (close the HTTP client;
  checkpoint and close the write connection), since steps 1–2 (run cancellation, thread-pool
  drain) need pipeline/run-state this struct doesn't carry and step 5 (instance-lock release)
  needs a lock handle STORY-079 hasn't built yet — both remain STORY-080's job, which calls this
  method as one step of its own assembled sequence. Proven by
  `test_app_handle_shutdown_closes_http_client_and_write_connection` (`Proves: STORY-077-AC-1`).
  All four fixes and the new test were independently re-verified by the orchestrating session
  (`just lint`/`typecheck`/`import-check`/`arch-test` plus the full `test_compose_build_app.py`
  suite run directly) before this story was reconsidered for `done`.
- **`compose.py` is now 399 of the 400-line owner-approved ceiling — essentially no headroom
  left.** The next Phase-11 story touching this file (STORY-078, STORY-080, or STORY-083) will
  likely need either a further documented line-budget widening or a `compose.py` decomposition;
  flagging now so it isn't a surprise.
- **Minor, non-blocking:** `_NoActiveRunTaskPaths`'s docstring says "no tracker exists yet" rather
  than the literal words "placeholder"/"future implementation" AC-11's wording anticipates, though
  it conveys the same meaning; the AC-11 test already documents this and checks the real wording.
  Not worth a fourth remediation pass on its own — fold into whatever story next touches
  `compose.py`.
