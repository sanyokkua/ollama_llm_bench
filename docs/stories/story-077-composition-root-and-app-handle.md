---
id: STORY-077
title: Build the composition root, the AppHandle, and the export-filename bridge
status: draft
spec_clauses:
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#7-the-composition-root
  - 16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#2-the-single-execution-runner-guarantee
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
  - 01_Main_Window/description.md#31-settings-action
  - 01_Main_Window/description.md#32-about-action
modules:
  - backend/csv_export/
  - ui/main_window/
  - ui/results/
  - ui/resume_benchmark/
  - ui/theme/
acceptance_criteria:
  - STORY-077-AC-1
  - STORY-077-AC-2
  - STORY-077-AC-3
  - STORY-077-AC-4
  - STORY-077-AC-5
  - STORY-077-AC-6
  - STORY-077-AC-7
  - STORY-077-AC-8
depends_on:
  - STORY-104
  - STORY-112
adrs:
  - ADR-0010
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
- **The five `modules:` entries are exactly the modules whose code this story changes**, which is
  what keeps it inside the `L` bound of five: `ui/main_window/` (the widened factory signature),
  `backend/csv_export/` + `ui/results/` + `ui/resume_benchmark/` (the export-filename bridge and the
  two gateways it is injected into), and `ui/theme/` (the startup apply path). `build_app` *calls*
  most of the other 60-odd modules, but calling an unchanged public factory is not "touching" a
  module for sizing purposes — otherwise every composition-root story would cite the whole inventory
  and could never fit any estimate. `ui/settings_dialog/` and `ui/common_dialogs/` are deliberately
  excluded on that basis and are claimed instead by STORY-083, which owns the end-to-end
  dialog-opening behaviour. The gateway modules are excluded on the same basis and are claimed by
  STORY-104's children.
- **The 50–200-line `compose.py` budget fits — this is settled; do not re-raise it.** An earlier
  draft of this story warned the budget was "genuinely tight" on the basis of roughly 80 public
  `make_*`/`create_*` factories in the codebase. That count was misleading: only about 34 of those
  factories are **compose-time**. The rest are per-run (the evaluators, the adaptive-timeout service,
  the circuit breaker, the embedding service, the cancellation token) or per-dialog/on-demand, and
  are constructed by their owners at the moment they are needed, not by `build_app`. A wrapped
  `build_app` at the 100-column `ruff` limit lands at roughly **80–120 lines**, comfortably inside
  the bound. Keep each call compact and keep anything that can live behind an existing module's
  public `api.py` out of `compose.py`, but do **not** treat the budget as a spec-versus-reality
  conflict and do not open an ADR about it.
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
delegating to `compose_export_filename`, for every export kind:

| UI `kind` string | Backend `ExportKind` passed to `compose_export_filename` |
| ---------------- | -------------------------------------------------------- |
| `summary`        | `ExportKind.SUMMARY`                                     |
| `details`        | `ExportKind.DETAILS`                                     |

### STORY-077-AC-5

`compose.py` is between 50 and 200 source lines (the composition-root budget), asserted by an
architecture test that runs against the file's current contents on every suite run — so the bound
holds for the final `compose.py` after every later Phase-11 story has added to it, not only at this
story's merge.

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

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-077.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Why this story dropped from `ready` back to `draft`.** It did not lose any spec grounding — every
  clause still resolves and every acceptance criterion still stands. It moved because
  `02_STORY_FORMAT.md` §8 makes "every `depends_on` story is `done`" an entry condition for `ready`,
  and this story now has two unmet dependencies. Neither STORY-104 (with its seven children) nor
  STORY-112 exists in code yet, so `build_app` still has no gateway to hand `make_main_window`, and
  AC-6 and AC-8 remain unreachable. It returns to `ready` the moment STORY-104 and STORY-112 are
  `done`; nothing else about it needs to change.
- **STORY-104 is `draft` pending ADR-0014.** ADR-0014 settles where the concrete gateway
  implementations live (one new `adapters/ui_gateways/` module) but is `proposed`, because it needs an
  owner-approved one-row correction to the read-only module inventory. Until that is ratified,
  STORY-104's children cannot move to `ready`, and therefore neither can this story. This is the
  critical path for the whole of Phase 11.
