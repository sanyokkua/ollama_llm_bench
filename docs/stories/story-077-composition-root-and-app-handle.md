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
depends_on: []
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
  `01_PROJECT_STRUCTURE.md` §7–§8 — including the one shared write connection, the one `TaskRunner`,
  and the one synchronous HTTP client (each constructed exactly once).
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
- Settings/About dialog callback injection: `build_app` injects the real Settings-open and
  About-open callbacks into the main-window controller (whose callbacks default to `None` until
  wired), so activating the menu-bar Settings and About actions opens their modal dialogs.
- Constructing and showing the main window, whose show handler schedules the single deferred
  readiness tick.

## Out of scope

- The process entry point and the two exception hooks — owned by STORY-076.
- The launch glue (logging, app-data directory, database open + schema check + seeding) that runs at
  the top of `build_app` — owned by STORY-078.
- The single-instance advisory lock helper — owned by STORY-079.
- The quit sequence and the shutdown-handle body's step-by-step behaviour — owned by STORY-080.
- Runtime theme re-application on a settings change and the end-to-end menu-driven dialog opening —
  owned by STORY-083; this story only performs the one-time startup theme apply and the compose-time
  callback injection.
- Every `make_*` factory being wired — already delivered by STORY-001..STORY-075; this story calls
  them, it does not implement them.

## Spec inputs

- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#7-the-composition-root` — `compose.py` is the
  sole wiring point (`build_app(*, app, loop) -> AppHandle`), roughly 50–200 lines of keyword-argument
  factory calls, no DI container / service locator / reflection; `__main__.py` carries no business
  logic.
- `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root` — the fixed construction
  order and the shape of `build_app` / `AppHandle`; dependencies passed as plain keyword arguments.
- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the graph is built
  synchronously and performs no network call (step 8); the theme is applied from the theme setting
  (step 9); the main window's show handler schedules one deferred tick that triggers the readiness
  probe (step 10).
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
  wired with its per-widget adapter gateway.
- The theme is applied by the theme module only — `compose.py` invokes `make_theme_manager` and the
  theme module's apply path; no other module assembles or applies a stylesheet.

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

For every run of `build_app`, exactly one shared write connection, exactly one `TaskRunner`, and
exactly one synchronous HTTP client are constructed and injected into their dependents.

### STORY-077-AC-4

The export-filename bridge satisfies the UI `compose_filename(*, run, kind, ext)` Protocol by
delegating to `compose_export_filename`, for every export kind:

| UI `kind` string | Backend `ExportKind` passed to `compose_export_filename` |
| ---------------- | -------------------------------------------------------- |
| `summary`        | `ExportKind.SUMMARY`                                     |
| `details`        | `ExportKind.DETAILS`                                     |

### STORY-077-AC-5

`compose.py` is between 50 and 200 source lines (the composition-root budget), asserted by an
architecture test.

### STORY-077-AC-6

Given `build_app` has returned an `AppHandle`,
when the main window is shown,
then its show handler schedules exactly one deferred tick that triggers the readiness probe, and no
readiness probe runs during `build_app` itself.

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
