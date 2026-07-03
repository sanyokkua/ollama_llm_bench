# Main Window — Description

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `01_Main_Window/state_machine.md`, `01_Main_Window/flow_diagram.md`, `01_Main_Window/implementation_structure.md`, `01_Main_Window/mockup.html`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-H_app_modes.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-L_ui_standardization.md`, `08_Cross_Cutting/08-M_app_lifecycle.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

The Main Window is the single application shell of Ollama LLM Bench. It hosts a minimal menu bar, a swappable workspace region, and a persistent status bar; it owns no benchmark or task-editing business logic and delegates every domain action to a controller. This document specifies its layout, every menu-bar item, the status bar, the workspace switcher, the window-level run states, the geometry and splitter persistence, the close-confirmation flow, the cross-panel coordination it performs, its edge cases, and its full function inventory.

---

## Table of Contents

1. Role and ownership
2. Window layout
3. Menu bar
4. Status bar
5. Workspace switcher and the workspace region
6. Window-level run states
7. Persistence — geometry, splitter sizes, active workspace
8. Close-confirmation behaviour
9. Cross-panel coordination
10. Event Bus integration
11. Service dependencies
12. Window title
13. Theme and fonts
14. Accessibility
15. Error surfacing
16. Edge cases
17. Function inventory
18. Out of scope

---

## 1. Role and ownership

The Main Window is the application's only top-level window. It is responsible for:

- Hosting the three permanent shell regions — the menu bar, the workspace region, and the status bar.
- Constructing and swapping between the two workspaces (Benchmark and Task Editor) through the Workspace Controller.
- Reflecting the window-level run state in its title, menu bar, and status bar.
- Persisting and restoring window geometry, splitter sizes, and the active workspace.
- Confirming a quit when a run is in a non-terminal state or a task buffer is unsaved.
- Surfacing application-wide notifications as status-bar toasts and modal dialogs.

The Main Window is **not** responsible for: configuring or starting a run (the New Benchmark widget and the run-creation use case do that), executing a run (the Benchmark Pipeline does that), rendering results (the Result widget does that), or editing task files (the Task Editor does that). It wires those surfaces together and owns nothing they own.

The application is single-window. There is no second window, no system tray icon, and no detached top-level shell; the only modeless secondary surfaces are detached chart windows spawned from the Result widget, which are out of this document's scope.

## 2. Window layout

The Main Window is composed of three stacked regions inside one resizable frame:

```
+====================================================================+
|  Settings  About   [ Benchmark | Task Editor ]   Running...   v1.0  | <- menu bar (32 px)
+====================================================================+
|                                                                    |
|                       WORKSPACE REGION                             | <- swappable; fills remaining height
|             (Benchmark workspace or Task Editor workspace)          |
|                                                                    |
+====================================================================+
|  * Ready                       <toast region>              v1.0.0  | <- status bar (22 px)
+====================================================================+
```

- **Sizing.** Minimum size `1280 x 720`; default size `1440 x 900`. The window is resizable above the minimum. Size and position are restored from the `ui.window_geometry` setting on launch (see §7).
- **Menu bar.** Fixed height 32 px. Built in-window on every platform, including macOS, so the control surface is identical everywhere (`08-L_ui_standardization.md` §2.1).
- **Workspace region.** Fills all height between the menu bar and the status bar. Its content is owned by the Workspace Controller and is one of the two workspaces described in §5.
- **Status bar.** Fixed height 22 px. Always present, in both workspaces (§4).

### 2.1 Benchmark workspace layout — idle versus running

When the Benchmark workspace is active, the workspace region holds a single horizontal splitter with three panels:

```
+------------------+----------------------------+---------------------+
| LEFT             | CENTRE                     | RIGHT               |
| Run configuration| Progress                   | Result              |
| (New / Resume)   | (progress, log)            | (Summary/Details/   |
|                  |                            |  Charts/Judge       |
|                  |                            |  Analysis)          |
+------------------+----------------------------+---------------------+
```

| Panel | Widget folder | Minimum width | Default width |
|---|---|---|---|
| Left — Run configuration | `02_New_Benchmark_Widget/`, `03_Resume_Benchmark_Widget/` | 320 px | 360 px |
| Centre — Progress | `04_Progress_Widget/` | 480 px | 580 px |
| Right — Result | `05_Result_Widget/` | 480 px | 500 px |

Splitter handles are 1 px wide. Splitter children are **not collapsible** by dragging a handle — no panel can be reduced to zero width (`08-L_ui_standardization.md` §13).

The Benchmark layout is **not static**: it reflows with the window-level run state, per the No-Placeholder-UI rule (`08-L_ui_standardization.md` §1).

- **Idle layout** — no run is active, or a terminal run is selected for review. All three panels are visible.
- **Running layout** — a run is in a non-terminal state (initializing, running, or paused). The **left panel is removed from the layout entirely** — a new run cannot be configured while one is in progress, so its controls are hidden rather than greyed out. The **centre panel expands** into the freed space. The right panel stays visible and updates live.

| Operation | Left panel | Centre panel | Resulting layout |
|---|---|---|---|
| Start a benchmark | removed | expands | running |
| Pause | stays removed | stays expanded | running (unchanged) |
| Resume (paused → running) | stays removed | stays expanded | running (unchanged) |
| Stop | reappears | shrinks back | idle restored |
| Run finishes or fails | reappears | shrinks back | idle restored |

**Pause keeps the running layout** — a paused run is still a non-terminal run. Only Stop, natural completion, or failure restores the idle three-panel layout. The reflow is performed by the Workspace Controller's Benchmark-workspace composite in response to the run-lifecycle events of §10; the splitter sizes saved under `ui.splitter_sizes` describe the idle three-panel layout and are reapplied when the idle layout is restored.

### 2.2 Task Editor workspace layout

When the Task Editor workspace is active, the workspace region holds the editor toolbar above a three-pane editor (Files, Tasks, Field editor). The full layout and behaviour are specified in `09_Task_Editor/`. The menu bar and the status bar persist unchanged; only the workspace region content differs.

## 3. Menu bar

The menu bar is deliberately **minimal**. It carries exactly the items below and **has no File, Edit, View, or Help dropdown menus** (`08-L_ui_standardization.md` §2.2). Operations that a conventional menu would hold live at their functional home, listed in §3.5.

Left-to-right order: Settings action, About action, workspace switcher, running pill, application version.

```
+--------------------------------------------------------------------+
|  Settings   About   [ Benchmark | Task Editor ]   Running...   v1.0 |
+--------------------------------------------------------------------+
   <-- actions -->     <-- workspace switcher -->   <- pill -> <- ver ->
```

### 3.1 Settings action

A single clickable menu-bar item. Activating it opens the Settings modal dialog (`06_Settings_Dialog/`).

The Settings action is **disabled while a benchmark run is in any non-terminal state** — initializing, running, or paused (`08-G_feature_flags.md` §11.3; `08-H_app_modes.md` §6, §10). A disabled Settings action carries the tooltip `Disabled - a benchmark is in progress.` This restriction is what keeps the per-run settings snapshot airtight: the user-saved settings layer cannot change while a run executes. The Settings action is re-enabled when the run reaches a terminal state.

### 3.2 About action

A single clickable menu-bar item. Activating it opens the Application Information modal dialog (`07_Common_Dialogs/about_dialog.md`), which shows the application version, the project link, and the single application-data-folder row with its **Copy path** and **Open folder** actions (the logs and exports are subfolders of that folder; dedicated per-subfolder open actions live in Settings → Storage). The About action is always available — it is never gated by run state.

### 3.3 Workspace switcher

A segmented control with two segments, `Benchmark` and `Task Editor`, always visible in both workspaces. Exactly one segment is active. Activating a segment calls `WorkspaceController.switch_to(...)` (`08-E_interfaces_contracts.md` §19). The full switching behaviour is in §5.

### 3.4 Running pill

A pill visible **only while at least one benchmark run is in a non-terminal state**. It is absent — removed from the layout, not greyed out — when no run is active (`08-L_ui_standardization.md` §1, §2.2). Its label uses the run's effective name: `BenchmarkRun.run_name` when set, otherwise the name generated from `run_id`, `run_mode`, and `timestamp` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §6.7). Clicking the pill switches to the Benchmark workspace and focuses the Progress widget — it calls `WorkspaceController.switch_to("benchmark", hint=WorkspaceHint(focus_widget="progress"))`.

The pill carries a small leading **status dot** (the "blip") that signals an active run at a glance. The blip uses the `primary.base` colour role and is **static** — it does not pulse or animate; the pill's mere visibility is the only "a run is live" signal, so no motion is required to convey it. Were a slow pulse ever introduced, it would be a decorative animation and must therefore honour the reduced-motion preference (no animation when the OS reports reduced motion — §14, `08-L_ui_standardization.md` §2.2 menu-bar pill).

### 3.5 Menu-bar item summary and the removed menus

| Item | Trigger | Effect | Gating |
|---|---|---|---|
| Settings action | Click | Open the Settings modal dialog | Disabled while a run is non-terminal |
| About action | Click | Open the Application Information modal dialog | Always available |
| Workspace switcher | Click a segment | Switch the active workspace | Always available; dirty-buffer prompt on leaving Task Editor |
| Running pill | Click | Switch to Benchmark, focus Progress | Visible only while a run is non-terminal |
| Version string | — | Informational only; no affordance | Always shown |

There are **no File / Edit / View / Help menus**. Their conventional contents live at their functional home:

| Former menu operation | Functional home |
|---|---|
| Open Task File, Open Folder, New File, Save, Save All, Reload, Close File | Task Editor toolbar (`09_Task_Editor/`) |
| Add Task, Duplicate Task, Move Task Up / Down | Task Editor tasks pane (`09_Task_Editor/`) |
| View YAML preview, Validate file | Task Editor toolbar (`09_Task_Editor/`) |
| Switch workspace | Workspace switcher segmented control (§3.3) |
| Open the application data folder (root of logs/ and exports/) | About dialog folder row (`07_Common_Dialogs/about_dialog.md`); per-subfolder open actions in Settings → Storage |
| Quit | Window close (X) control (§8) |

### 3.6 Window chrome (title-bar window controls)

The title bar itself is **OS-native** and is provided by the windowing system, not drawn in-window — unlike the menu bar, which is built in-window on every platform (§2, `08-L_ui_standardization.md` §2.1). The OS title bar supplies the three standard window controls — **close**, **minimise**, and **maximise** — and renders them in the platform's native style: on macOS these are the red / yellow / green traffic-light controls at the top-left; on Windows and Linux they are the platform's native title-bar buttons (typically top-right). Their presence, glyphs, order, and exact appearance are OS-provided and vary by platform; the application does not restyle them.

Their behaviour binds to shell behaviour as follows:

- **Close** is the quit affordance. It routes through the **same close-confirmation sequence** as any in-window quit path (§8, `08-M_app_lifecycle.md` §7): when a run is non-terminal or a task buffer is dirty, the confirmations run before the process exits. There is no separate, unconfirmed close path.
- **Minimise** and **maximise / zoom** interact normally with the geometry persistence of §7 — a maximise / restore or a resize updates the window geometry that is debounced and written to `ui.window_geometry`, and is reapplied on the next launch (subject to the off-screen clamp).

## 4. Status bar

The status bar is always present, in both workspaces. It has three regions (`08-L_ui_standardization.md` §4):

| Region | Position | Content source | Behaviour |
|---|---|---|---|
| Health dot + label | left | Readiness Service snapshot (Benchmark workspace); editor status (Task Editor workspace) | Clickable in the Benchmark workspace — see §4.2 |
| Toast region | centre | Notification Service info channel, via `_global_message` events | Auto-clears after 5 s; empty in steady state |
| Version string | right | Application version constant | Informational only; no affordance |

### 4.1 Health dot states (Benchmark workspace)

The dot reflects the most recent `AppReadinessSnapshot.overall` (`ReadinessState`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.2):

| `ReadinessState` | Dot colour role | Label | Meaning |
|---|---|---|---|
| `READY` | `success.base` | `Ready` | Every enabled provider is reachable; the embedding model (when the current need requires it) resolves. |
| `DEGRADED` | `warning.base` | `Degraded` | Some providers are unreachable, but a run is still possible for at least one mode. |
| `NOT_READY` | `error.base` | `Not ready` | The required resources for the gated modes are unavailable. |
| `CHECKING` | `muted.base` | `Checking` | A readiness probe is in flight. |

The dot tooltip lists the per-provider reachability detail from `AppReadinessSnapshot.per_provider` and the embedding reachability. The state never blocks the application — the window stays navigable in every state.

In the Task Editor workspace the left region instead shows the editor's aggregate status (for example `Valid - 12 tasks` or `1 file with unsaved changes`); the provider health dot is hidden in that workspace (`08-G_feature_flags.md` §11.1).

### 4.2 Clicking the health dot

Clicking the dot or its label in the Benchmark workspace opens the Settings dialog on the Providers tab and triggers a readiness re-probe so every enabled provider is re-tested. This action is **blocked while a run is in any non-terminal state**: the click is ignored and a status-bar toast appears reading `Disabled - a benchmark is in progress.` (`08-H_app_modes.md` §10). The block exists because opening Settings is itself blocked during a run (§3.1).

## 5. Workspace switcher and the workspace region

The Main Window has two workspaces that share the same shell. Exactly one is active. The active workspace is held as state by the Workspace Controller and restored on launch from the `ui.active_workspace` setting (default `benchmark`).

| Workspace | Workspace-region content | Status-bar left region |
|---|---|---|
| Benchmark | Three-panel splitter — Run configuration, Progress, Result | Provider readiness dot |
| Task Editor | Editor toolbar above the three-pane editor | Editor status counts |

### 5.1 Switching rules

| Trigger | Behaviour |
|---|---|
| Click a switcher segment | Atomic swap of the workspace-region content. The inactive workspace's state is preserved — open task buffers persist, benchmark widgets persist. The alternate workspace is constructed lazily on its first activation (`08-M_app_lifecycle.md` §2 step 10). |
| Leave the Task Editor with one or more dirty buffers | A modal dialog appears first: `Save changes to N file(s)?` with `Save All`, `Discard All`, and `Cancel`. `Cancel` aborts the switch. The switch proceeds only after the prompt resolves (`08-H_app_modes.md` §10). |
| Click the running pill (from either workspace) | Switch to the Benchmark workspace and focus the Progress widget. |
| Application launch | Restore the workspace named by `ui.active_workspace`. |

Switching the workspace **never** stops, pauses, or disturbs a benchmark run — the Benchmark Pipeline runs on a background worker independent of the active workspace (`08-H_app_modes.md` §1). On every successful switch the new workspace name is written to `ui.active_workspace` and the `_workspace_changed` event is emitted.

## 6. Window-level run states

The Main Window reads the single window-level run-active state from the adapter's **run-activity gateway** (backed by the pipeline's `is_running()` / `current_run()`) and observes the canonical `_run_*` lifecycle events on the Event Bus for push updates (D-R-05; via the gateway, not a direct backend Protocol call, per D-R-06). This is the **same single source** the Progress and Result widgets read, so the panels never disagree about whether a run is active. The full state machine is in `state_machine.md`; this section summarises the affordances each state imposes on the shell.

| Window-level state | Menu bar | Status bar | Benchmark layout |
|---|---|---|---|
| Initialising (launch) | enabled | health dot `Checking` | idle |
| Idle (no run, or a terminal run selected) | Settings enabled | health dot Ready / Degraded / Not ready | idle |
| RunStarting | Settings disabled | toast `Starting...` | transitioning to running |
| Running | Settings disabled; running pill shown | health dot live | running (left panel removed) |
| Paused | Settings disabled; running pill shown | health dot live | running (unchanged) |
| Stopping / Finishing / Failing | Settings disabled until terminal | health dot live | running until terminal |
| SettingsOpen | window dimmed behind modal | unchanged | unchanged |
| AboutOpen | window dimmed behind modal | unchanged | unchanged |
| CloseConfirming | window dimmed behind modal | unchanged | unchanged |

A **non-terminal** run state is RunStarting, Running, Paused, Stopping, or Finishing-before-terminal; a **terminal** run state is Idle with a Completed, Stopped, or Failed run, or the no-run case (`08-H_app_modes.md` §2). The Settings action and the running pill are driven entirely by whether the current state is non-terminal.

## 7. Persistence — geometry, splitter sizes, active workspace

The Main Window persists three pieces of shell state through the Settings Service (`08-E_interfaces_contracts.md` §8). The keys are defined in `08-G_feature_flags.md` §7.

| Setting key | What it stores | Written when | Read when |
|---|---|---|---|
| `ui.window_geometry` | Window position and size | On resize / move, after a 200 ms debounce; and on quit | On launch, before the window is shown |
| `ui.splitter_sizes` | The idle three-panel Benchmark splitter sizes | On splitter-handle drag, after a 200 ms debounce; and on quit | On launch; and whenever the idle layout is restored |
| `ui.active_workspace` | The active workspace name (`benchmark` or `task_editor`) | On every workspace switch | On launch |

The 200 ms debounce coalesces a stream of resize or drag events into a single write so the storage layer is not hit on every pixel of movement. On quit, the current values are written one final time as part of the quit sequence (`08-M_app_lifecycle.md` §7 step 4). If a stored geometry would place the window fully off-screen — for example after a monitor was disconnected — the Main Window clamps the restored geometry to the available screen area and falls back to the default centred `1440 x 900` when no valid placement exists.

## 8. Close-confirmation behaviour

A quit is requested by the window close (X) control. The Main Window runs the quit sequence of `08-M_app_lifecycle.md` §7, which may show up to two confirmations in sequence:

1. **Running-benchmark confirmation.** When `BenchmarkFlowApi.is_running()` is true (a run is non-terminal, paused included), a modal dialog asks `Stop the benchmark and quit?`. `Cancel` aborts the quit and returns the window to its prior state. `Confirm` requests a graceful pipeline shutdown via `BenchmarkFlowApi.shutdown(timeout_ms)`; the Main Window waits for the `_run_stopped` event or for the bounded timeout to elapse, whichever comes first.

2. **Unsaved-buffer confirmation.** When the Task Editor holds one or more dirty buffers, a modal dialog asks `Save changes to N file(s)?` with `Save All`, `Discard All`, and `Cancel`. `Cancel` aborts the quit. `Save All` writes every dirty buffer before the quit proceeds; `Discard All` proceeds without saving.

When both conditions hold, the running-benchmark prompt is shown first, then the unsaved-buffer prompt; a cancel at either step aborts the entire quit (`08-M_app_lifecycle.md` §9 EC-M-7). After every confirmation resolves toward quitting, the Main Window persists `ui.window_geometry`, `ui.splitter_sizes`, and `ui.active_workspace`, the database is closed cleanly, and the process exits.

## 9. Cross-panel coordination

The Main Window mediates a small number of cross-panel interactions. It does not move domain data between panels — domain data flows through the scoped reactive state stores and the Event Bus — but it coordinates the shell-level effects:

- **Run start.** When `_run_started` arrives, the Main Window shows the running pill, disables the Settings action, sets the running window title, and triggers the Benchmark-workspace reflow to the running layout (left panel removed). The Result widget's own controller, subscribed to the run-selection store, jumps the run selector to the new run independently — the Main Window does not push that selection.
- **Run terminal.** When `_run_finished`, `_run_stopped`, or `_run_failed` arrives, the Main Window hides the running pill, re-enables the Settings action, clears the running window title, and triggers the reflow back to the idle layout.
- **Running pill click.** Switches to the Benchmark workspace and focuses the Progress widget — the only shell-initiated cross-panel navigation.
- **Run rename.** When `_run_renamed` arrives for the currently running run, the Main Window updates the window title and the running-pill label.
- **Task-file change.** When `_task_file_changed` arrives and the Benchmark workspace is active, the New Benchmark task-files panel refreshes itself; the Main Window forwards no payload — the New Benchmark widget subscribes directly.

Run management — rename, delete, resume, retry, clone, export — is **not** a Main Window responsibility. It lives in the Resume Benchmark widget (`03_Resume_Benchmark_Widget/`), with the single exception of renaming the actively-running run, which lives in the Progress widget header. The Result widget is view-only and carries no rename or delete affordance.

## 10. Event Bus integration

The Main Window subscribes to the events below; every subscription passes the Main Window as the owner so it auto-cancels on window destruction (`08-J_event_bus_catalog.md` §2). The Main Window emits no domain events of its own — workspace switches are emitted by the Workspace Controller.

| Subscribed event | Payload | Main Window reaction |
|---|---|---|
| `_run_started` | `RunStartedEvent` | Show running pill; disable Settings; set running title; reflow Benchmark layout to running |
| `_run_paused` | `RunPausedEvent` | Keep running pill and running layout; reflect paused state in the title |
| `_run_resumed` | `RunResumedEvent` | Restore the running (non-paused) title |
| `_run_stopped` | `RunStoppedEvent` | Hide running pill; re-enable Settings; clear running title; reflow Benchmark layout to idle |
| `_run_finished` | `RunFinishedEvent` | Hide running pill; re-enable Settings; clear running title; reflow Benchmark layout to idle |
| `_run_failed` | `RunFailedEvent` | Hide running pill; re-enable Settings; clear running title; reflow Benchmark layout to idle |
| `_run_renamed` | `RunRenamedEvent` | Update the window title and the running-pill label when the renamed run is the running run |
| `_app_readiness_changed` | `AppReadinessChangedEvent` | Repaint the status-bar health dot and refresh its tooltip |
| `_global_message` | `GlobalMessageEvent` | Show the message as a transient status-bar toast (5 s) |
| `_workspace_changed` | `WorkspaceChangedEvent` | Swap the workspace-region content; switch the status-bar left region between health dot and editor status |

The current run-selection, the current run-list, the current provider registry, and the current readiness snapshot are **state**, held in scoped reactive state stores and read by the panels that need them; the events above are change notifications, never the source of truth for a displayed value (`08-J_event_bus_catalog.md` §1).

## 11. Service dependencies

The Main Window is constructed by the composition root and receives its dependencies by constructor injection (`08-E_interfaces_contracts.md` §23). It depends, in contract terms, on:

| Dependency | Contract | Used for |
|---|---|---|
| Event Bus | `EventBus` | Subscribing to the events of §10 |
| Workspace Controller | `WorkspaceController` | Reading and switching the active workspace |
| Benchmark Flow API | `BenchmarkFlowApi` | `is_running()` for the close-confirmation decision; `shutdown(...)` on quit |
| Settings Service | `SettingsService` | Reading and writing `ui.window_geometry`, `ui.splitter_sizes`, `ui.active_workspace`, `ui.theme` |
| Readiness Service | `ReadinessService` | Reading the current snapshot for the status-bar dot; triggering a re-probe on a dot click |
| Notification Service | `NotificationService` | Showing toasts and modal error dialogs |
| File-system actions | `FileSystemActions` | The "open in file manager" affordances exposed from the Main Window menu (the OS colour-scheme preference is read via a thin platform query that lives outside the three OS-adapter Protocols) |

The Main Window never imports a concrete service class and never touches any persistence-store implementation directly — durable reads and writes flow through the panels' controllers.

## 12. Window title

| Condition | Title |
|---|---|
| No run is non-terminal | `Ollama LLM Bench v{version}` |
| A run is running | `Ollama LLM Bench - Running: {effective_run_name}` |
| A run is paused | `Ollama LLM Bench - Paused: {effective_run_name}` |

`{effective_run_name}` is `BenchmarkRun.run_name` when set, otherwise the generated name. When a run is non-terminal and the user has selected a different past run in the Result widget for review, the running (or paused) run takes precedence in the title — the title always reflects the active run, not the reviewed one.

## 13. Theme and fonts

- **Theme.** System, Dark, or Light, driven by `ui.theme` (default `system`). When the setting is `system`, the OS Adapter supplies the OS colour-scheme preference at launch and the application tracks live OS colour-scheme changes, re-applying the theme without a restart (`08-L_ui_standardization.md` §12). All colours, fonts, spacing, radii, and borders come from the design tokens defined in `08_Cross_Cutting/08-D_color_palette_and_typography.md`; the Main Window uses no literal colour values and no per-widget stylesheet.
- **Fonts.** The Main Window inherits the theme module's **platform-aware** font selection from `08_Cross_Cutting/08-D_color_palette_and_typography.md` §7. At startup the theme module reads the current platform from the Platform Detector (`08_Cross_Cutting/08-K_platform_specifics.md` §2) and applies the sans + mono chain prescribed for that platform; it never probes `QFontDatabase` for per-family availability. The chains are reproduced below for at-a-glance reference; the canonical definition lives in 08-D §7.

| Platform (`PlatformKind`) | Sans chain | Mono chain |
|---|---|---|
| `MACOS` | `"Helvetica Neue", "Arial", sans-serif` | `"Menlo", "Monaco", "Courier New", monospace` |
| `WINDOWS` | `"Segoe UI", "Arial", sans-serif` | `"Consolas", "Cascadia Mono", "Courier New", monospace` |
| `LINUX` | `"Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", sans-serif` | `"DejaVu Sans Mono", "Ubuntu Mono", "Noto Sans Mono", "Liberation Mono", monospace` |
| `UNKNOWN` (defensive fallback) | `"Segoe UI", "Helvetica Neue", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", "Arial", sans-serif` | `"Consolas", "Menlo", "Cascadia Mono", "DejaVu Sans Mono", "Ubuntu Mono", "Monaco", "Courier New", monospace` |

The font chains deliberately exclude `"SF Pro Text"`, `"SF Pro Display"`, `"SF Mono"`, and `"San Francisco"` (hidden/private macOS system fonts that do not resolve reliably through Qt and may trigger toolkit warnings), `"Roboto"` and `"Inter"` (not preinstalled on desktop Linux), and the browser-only `system-ui`, `BlinkMacSystemFont`, and `-apple-system` keywords (inconsistent in Qt stylesheets).

## 14. Accessibility

The Main Window meets the accessibility floor of `08-L_ui_standardization.md` §13:

- Every interactive control — the Settings action, the About action, each switcher segment, the running pill, the health dot — has an accessible name and a hover tooltip.
- The shell is operated by mouse only; there are no keyboard shortcuts or accelerators.
- Every state conveyed by colour — the health dot above all — is also conveyed by a text label, so the shell is usable in greyscale and for colour-blind users.
- Both Dark and Light themes satisfy the WCAG 2.1 AA contrast matrix.
- Every clickable control offers a hit area of at least 24 x 24 px.
- When the OS reports a reduced-motion preference, the running-layout reflow and the toast transitions apply instantly with no animation.

## 15. Error surfacing

The Main Window has two error-surfacing mechanisms, both fed by the Notification Service (`08-E_interfaces_contracts.md` §20):

1. **Toast** — a transient message in the status-bar centre region, auto-dismissed after 5 s. Used for non-blocking information and warnings, delivered via `_global_message` events.
2. **Modal dialog** — a blocking dialog for an error that demands acknowledgement (for example a failed save). Used only for the blocking error channel.

A critical error raised during a run **never** navigates the user away from the Progress view — it surfaces as a toast plus a run-log entry, never as a workspace switch.

**Startup environment dialog.** On the deferred readiness probe (`08-M_app_lifecycle.md` §5), when the probe detects that the environment changed in a way that blocks the user — a previously enabled provider now unreachable, a missing model, a missing embedding model — the Main Window raises an informational modal dialog that states exactly what changed and how to fix it (for example `Provider 'X' is no longer reachable - open Settings - Providers to re-test or disable it`). This modal is **in addition to** the status-bar health dot, never a replacement for it; the user must never reach an enabled run-start affordance for an environment that cannot run a benchmark.

## 16. Edge cases

| Reference | Concern | Handling |
|---|---|---|
| EC-RUN-4 | Window close requested while a run is non-terminal | The Stop-and-quit confirmation of §8 runs; the pipeline is shut down gracefully with a bounded timeout before the process exits. |
| EC-RUN-7 | A persisted `INCOMPLETE` run is found at launch | The run is left `INCOMPLETE` and offered for resume in the Resume widget; it is never discarded (`08-M_app_lifecycle.md` §8). |
| EC-SET-4 | Settings open attempted mid-run | The Settings action is disabled and carries a tooltip explaining why (§3.1). |
| EC-WS-1 | Switch to the Task Editor while a detached chart window is open | The switch proceeds; the detached chart window is a modeless surface independent of the active workspace and stays open. |
| EC-WS-2 | Quit with dirty editor buffers and a running run | Both confirmations run in sequence — running-benchmark first, then unsaved-buffer; a cancel at either step aborts the quit (§8). |
| EC-PERF-2 | Two readiness probes overlap | The Readiness Service coalesces overlapping probes into one; `_app_readiness_changed` is coalesced at most twice per second so the dot does not flicker. |
| EC-PERSIST-1 | Database schema mismatch at launch | Launch aborts before the window is shown, with the hard schema-mismatch modal of `08-M_app_lifecycle.md` §3; the Main Window is never constructed. |
| EC-PERSIST-2 | Stored window geometry is fully off-screen | The Main Window clamps the restored geometry to the available screen area and falls back to the centred default when no valid placement exists (§7). |

## 17. Function inventory

Every behaviour the Main Window directly exposes, the trigger, and what gates it. Gates reference `08-G_feature_flags.md`, the active workspace (`08-H_app_modes.md` §1), and the run state (`08-H_app_modes.md` §2).

| Function | Trigger | Gated by |
|---|---|---|
| Switch to the Benchmark workspace | Click the Benchmark switcher segment / click the running pill | Always available |
| Switch to the Task Editor workspace | Click the Task Editor switcher segment | Always available; dirty-buffer prompt on leaving an editor with unsaved buffers |
| Open Settings | Click the Settings menu-bar action | Disabled while a run is in a non-terminal state |
| Open About | Click the About menu-bar action | Always available |
| Quit the application | Click the window close (X) control | Confirmation modal when a run is non-terminal or a task buffer is dirty |
| Click the running pill | Pill click | Visible only while a run is non-terminal |
| Click the status-bar health dot | Dot click | Benchmark workspace only; ignored with a toast while a run is non-terminal |
| Repaint the status-bar health dot | `_app_readiness_changed` event | Always |
| Show a status-bar toast | `_global_message` event | Always |
| Persist window geometry | Resize / move (200 ms debounce); quit | Always |
| Persist splitter sizes | Splitter-handle drag (200 ms debounce); quit | Benchmark workspace only |
| Persist active workspace | Every workspace switch | Always |
| Restore shell state on launch | Application launch | Always |
| Raise the startup-environment modal | Deferred readiness probe detects a blocking change | When the probe verdict is `DEGRADED` or `NOT_READY` with a blocking cause |

The shell-state keys `ui.theme`, `ui.window_geometry`, `ui.splitter_sizes`, and `ui.active_workspace` are read at launch and written through the Settings Service on the events listed above.

## 18. Out of scope

- **System tray icon.** Not part of the application.
- **Multi-window UI.** The application is single-window; detached chart windows spawned by the Result widget are the only modeless secondary surfaces and are specified in `05_Result_Widget/`.
- **Drag-and-drop of YAML files onto the Main Window frame.** Not accepted. YAML drops are scoped to dedicated drop targets only — the New Benchmark task-files panel (`02_New_Benchmark_Widget/`) and the Task Editor workspace (`09_Task_Editor/`).
- **Run management affordances.** Rename, delete, resume, retry, clone, and export live in the Resume Benchmark widget; renaming the actively-running run lives in the Progress widget header.
