# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking

- Full ground-up rewrite of the application against the v3 specification at
  `docs/v3_specification/`. The previous PySide6 codebase is removed in its entirety; there is
  no migration path from it and no backward compatibility with its data or configuration.
  Rebuilding starts from Phase 0 (repository governance and scaffold) — see
  `docs/reference_planning_docs/01_PHASE_BREAKDOWN.md`.

### Added

- Result widget Details tab (`ui/results/_internal/details_tab/`): per-result table with
  mode-aware column sets (16 columns in SYNTHETIC/TASK mode, all 24 in GRADED), filter chips
  (Verdict/Layer only in GRADED mode), per-column filters, sorting, and column
  visibility/reorder controls. Verdict and status cells render semantic colour roles. The Task
  Detail Panel displays the full structured record for a selected row in eight sections
  (identity, prompts, golden answer, model response, evaluation, judge reasoning, error,
  attempt history), with absent fields shown as em dashes. Chart-click drill-down requests from
  the Charts tab (STORY-064) are received and applied as filters, persisted to the run's view
  state. CSV and Markdown export via `ResultGateway.serialize_table(table="details")` mirrors
  the active filter state, visible columns, and sort order. Mounted into the existing
  `ResultController`/`ResultView` shell (STORY-061) via `DetailsTabController`/`DetailsTabView`.
  Row-selection checkboxes for narrowing export to selected rows are deferred to a follow-up
  story. Badge colour role mapping is implemented and tested, but no badge colour renders yet
  in the running app: `ResultCollaborators` has no `theme_manager` field to thread a real
  `ThemeManager` into the badge delegate, and wiring one requires a `compose.py` change out of
  this story's reach — also deferred to a follow-up story. Per `05_Result_Widget/tabs/details_tab.md`
  and `implementation_structure.md` §5.2.

- Qt notification surface (`adapters/notification_service/`): the `NotificationService` Protocol
  (`show_info(text, duration_ms=5000)`, `show_warning(text, duration_ms=5000)`,
  `show_error(text, *, blocking=False)`) and factory
  `make_notification_service(*, status_bar, parent)` — the sanctioned surface for a controller
  to raise a user-visible status-bar toast or, for `show_error(blocking=True)`, a modal
  `QMessageBox`. Every method is synchronous, callable only on the Qt main thread (enforced by
  `icontract` preconditions on the factory), and never raises to the caller — a Qt-layer failure
  (e.g. an already-destroyed underlying widget) is caught, logged, and swallowed rather than
  propagated. `blocking` is keyword-only per this project's boolean-flag convention, a stricter
  but backward-compatible narrowing of the spec's literal signature. Applies no redaction of its
  own — callers must redact `text` before calling. Ships a `testing.py` `FakeNotificationService`
  in-memory recorder for future widget-controller tests. Imports PySide6 only — no `backend/*`
  and no `asyncio`. Per `08-E` §20 and `08-Q` §8.3.

- Qt event bus deliverer (`adapters/qt_event_bus/`): the concrete `EventBus` implementation
  `QtEventBusDeliverer` and factory `make_qt_event_bus_deliverer()` — the first Qt-binding
  adapter in the codebase and the sole place `backend/events`' Qt-free bus is connected to Qt
  signals. `emit(signal_name, payload)` is callable from any thread; delivery is always
  re-marshalled onto the Qt GUI thread through one generic `Signal(str, object)` relay
  connected with an explicit `Qt.ConnectionType.QueuedConnection` (never `AutoConnection`), so
  every subscriber handler runs on the GUI thread regardless of which thread emitted, and even
  a same-thread `emit()` round-trips through the event loop rather than dispatching
  synchronously. `subscribe(signal_name, handler, owner=...)` rejects a missing `owner` via
  `icontract` (a programming error per `08-J` §2) and auto-cancels when `owner` is destroyed —
  a `QObject` owner via its `destroyed` signal, any other owner via `weakref.finalize`; the
  returned `Subscription.cancel()` is idempotent from either path. A handler exception is
  caught, logged (`app.qt_event_bus`), and isolated — it never breaks delivery to other
  subscribers or raises back to the emitter. The relay signal lives on a private
  `_RelayCarrier(QObject)` rather than directly on `QtEventBusDeliverer`, because PySide6
  silently redirects `SignalInstance.emit()` through `QObject`'s legacy `emit(signal, *args)`
  override once any attribute literally named `emit` exists on the same object. Per `08-E` §6,
  `08-J` §3, and `04_CONCURRENCY_STANDARD.md` §§2, 8. Adds the `tests/conftest.py` Qt-parity
  rig (autouse; fails a test emitting a Qt/PySide warning unless marked
  `@pytest.mark.allow_qt_warnings`), the first infrastructure exercising a real
  `QObject`/signal-slot connection in this test suite.

- Application-wide single-inference gate (`backend/stores/inference_activity/`): the
  method-only `InferenceActivityStore` Protocol (`try_acquire`, `release`, `state`, `is_busy`,
  no `psygnal.Signal`) and factory `make_inference_activity_store(clock, event_bus)`, enforcing
  that at most one inference-class activity (`BENCHMARK_RUN`, `JUDGE_ANALYSIS`,
  `PROVIDER_TEST`, `READINESS_PROBE`) holds the gate at a time. Ownership is a monotonically
  increasing `GateLease`, not the activity itself, so a late or foreign `release` can never
  steal a successor's hold. A lazy, pull-based watchdog (checked at the top of every
  lock-guarded method, no timer thread) auto-releases `JUDGE_ANALYSIS` after 10 minutes,
  `PROVIDER_TEST` after 60 seconds, and `READINESS_PROBE` after 30 seconds of holding the gate;
  `BENCHMARK_RUN` has no watchdog and owns its own lifecycle. Every acquire and release
  (including a watchdog auto-release) publishes `_inference_activity_changed` on the Qt-free
  `EventBus` per `08-E` §13, `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` §4.14, and
  `08-I` EC-RUN-14. No caller is wired to the gate yet — STORY-016 is the first consumer.

- Settings service and run snapshot builder (`backend/settings/`): the `SettingsService`
  Protocol (typed read/write methods `get_str`/`get_bool`/`get_int`/`get_float`/`set`/`upsert`
  resolving through the three-layer cascade per-run snapshot → user-saved → default) and
  `RunSnapshotBuilder` Protocol (`build_snapshot()` freezing the per-run-overridable keys at
  run creation), plus their factories `make_settings_service()` and `make_run_snapshot_builder()`.
  Implements the DEFAULTS registry (51 keys covering every `benchmark.*`, `feature.*`, `eval.*`,
  `embedding.*`, `ui.*`, `logging.*`, `task_editor.*` setting), the PER_RUN_OVERRIDABLE registry
  (27 overridable keys), coercion-failure fallback with logged warning for user-saved values and
  hard crash for snapshot values (SPEC-110), and an `_app_settings_changed` event on every
  `set`/`upsert` per `08-C` §2–§5, `08-E` §8–§8a, and `08-G` §3–§9.

- Readiness probe service (`backend/readiness/`): the `ReadinessService` Protocol with three
  methods — `snapshot()` (fast-synchronous cached read, returns `CHECKING` before the first
  probe), `probe(provider_id)` (blocking leaf probe of one provider), and `probe_all()`
  (blocking, dispatcher-orchestrated concurrent per-provider probes plus a single embedding
  handshake). Aggregates provider and embedding reachability into an `AppReadinessSnapshot`
  with one of four states (`READY`, `DEGRADED`, `NOT_READY`, `CHECKING`). The service
  never raises, never executes billable `embed()` calls, integrates with the single-inference
  gate via `InferenceActivity.READINESS_PROBE`, coalesces overlapping `probe_all` calls onto
  one shared in-flight batch, and emits `_app_readiness_changed` only when the recomputed
  snapshot differs from the cached one. Consumes `ReadinessProviderRegistry` and
  `ReadinessEmbeddingSelector` Protocols, plus `SettingsService`, `InferenceActivityStore`,
  `EventBus`, `TaskRunner`, and `Clock`. Per `08-E` §12 and `11_Services_and_Algorithms/09_READINESS_PROBE.md`.

- Persistence foundation layer (`backend/persistence/app_settings/`): the single-writer
  connection manager and schema lifecycle (ADR-0004) per DD-41 and DD-53, exposing
  `open_write_connection()` (writer + lock), `open_read_connection()` (read-only connection
  factory), `ensure_schema()` (first-run DDL and startup version check with additive evolution),
  `create_app_settings_store()` (typed settings store factory), and constants
  `EXPECTED_SCHEMA_VERSION` and `DB_FILENAME`. Implements the four-branch startup logic (file
  absent → first-run DDL; schema version match → no-op; older same-major → additive evolution;
  newer or cross-major → hard error).

- Benchmark run persistence (`backend/persistence/runs/`): the `RunsStore` Protocol (six
  methods: `create_run`, `get_run`, `list_runs`, `update_run_status`, `rename_run`, `delete_run`)
  and factory `create_runs_store(write_conn, lock, read_conn_factory)`. Atomically creates a
  run header and its three frozen snapshot child tables (`benchmark_run_models`,
  `benchmark_run_providers`, `benchmark_run_settings`), reads fully assembled runs newest-first,
  applies partial header updates leaving snapshots immutable, renames runs, and cascades delete
  across all eight dependent tables per `08-E` §7.1 and `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`.

- Benchmark task snapshot persistence (`backend/persistence/tasks/`): the `TasksStore` Protocol
  (two methods: `create_tasks`, `list_tasks`) and factory `create_tasks_store(write_conn, lock, read_conn_factory)`. Atomically inserts a run's frozen `benchmark_tasks` snapshot and its
  `benchmark_task_terms` child rows in one transaction, reads tasks in `task_order` with their
  keyword-term rows assembled per `08-E` §7.2 and `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`.

- Provider catalog persistence (`backend/persistence/providers/`): the `ProvidersStore` Protocol
  (six methods: `list_providers`, `get_by_name`, `add`, `update`, `delete`, `replace_providers`)
  and factories `create_providers_store(write_conn, lock, read_conn_factory)` and
  `seed_builtin_providers(write_conn, lock)`. The `add` method generates a fresh UUID4
  `provider_id`, returns it only after commit, and enforces `UNIQUE (name)` constraints. The
  `seed_builtin_providers` function initializes three built-in OpenAI-compatible local providers
  (Ollama, LM Studio, llama.cpp) in one transaction, each with `enabled=1`, no API key, and
  `provider_order` 0/1/2, per `08-E` §7.4, `DD-33`, and
  `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §10.

- Error taxonomy leaf `PersistenceError(PermanentError)` for storage failures raised by every
  method of the six per-aggregate persistence stores (`RunsStore`, `TasksStore`, `ResultsStore`,
  `ProvidersStore`, `ModelCapabilitiesStore`, `AppSettingsStore`) and the module's connection
  and schema-initialization functions per `08-E` §7.3.

- CSV/Markdown table serializer (`backend/csv_export/`): the `TableSerializer` Protocol with four
  methods (`serialize_summary_csv`, `serialize_summary_markdown`, `serialize_details_csv`,
  `serialize_details_markdown`) and factory `make_table_serializer()`, serializing the Summary
  and Details result tables to RFC 4180 CSV and GitHub-flavoured Markdown with a single shared
  column descriptor per table so the two formats never drift — fixed 13-column Summary, 17-column
  Details. The `compose_export_filename(run_name, run_id, kind, ext)` function implements the
  SPEC-064 path-traversal-safe filename composer: allowlist `[A-Za-z0-9._-]`, collapsed
  underscores, no leading dot/underscore, 80-character run-name truncation, `Run_<run_id>`
  fallback. Five DTOs: `ExportKind(StrEnum)` for Summary/Details, `RunExportContext`, `SummaryRow`
  (including provider-name snapshot per DD-33), `SummarySerializationRequest`, `DetailsSerializationRequest`.
  RFC 4180 quoting with **no formula-injection prefix** (verbatim content per spec), Markdown
  pipe/`<br>` escaping, empty-cell single-space rule. Pure, stateless, Qt-free, asyncio-free,
  no I/O, no redaction per `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`,
  `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

- HTML renderer for result details and log lines (`backend/html_rendering/`): the
  `ResultHtmlRenderer` Protocol with three methods (`render_result_detail`, `render_log_line`,
  `set_theme`) and factory `make_result_html_renderer(initial_theme)`, rendering a
  `BenchmarkResult`/`BenchmarkTask` pair into the ordered result-detail HTML fragment (§6.1) with
  omit-empty-section semantics (e.g., SYNTHETIC-mode results omit the grading section), and a
  `LogEntry` into a compact log-line fragment. Mandatory HTML escaping (`&`/`<`/`>`/`"`) of
  every value sourced from a task file, model response, or provider message; structural safety
  against `<script>`/`<style>`/`<iframe>`/`on*` attributes and network `href`/`src`. Four DTOs:
  `UiTheme(StrEnum)` for light/dark, `LogSeverity(StrEnum)` for severity levels, `LogEntry`
  (timestamp, severity, message, optional provider/model/task context), `ResultDetailRenderRequest`
  (result, task, run_mode). Light/dark inline-style palette per §8. Pure, stateless apart from
  the recorded theme; GUI-thread-only by convention; Qt-free, asyncio-free; no I/O, no redaction
  per `11_Services_and_Algorithms/20_HTML_RENDERING.md`.

- Chart aggregators for the Result widget's Charts tab (`backend/charts/`): the `ChartAggregator`
  Protocol (single method `compute`) and factory `make_chart_aggregator()`, computing all twelve
  `ChartKind` aggregations (average TTFT/TPS/time per model, success/failed/incomplete counts,
  pass rate, average cosine, verdict counts, time-vs-tokens scatter, task-by-model heatmap,
  per-category bar, speed-vs-quality Pareto scatter, tokens-per-task box plot) from a run's
  `BenchmarkResult`/`BenchmarkTask` snapshot into ready-to-paint `ChartData`/`HeatmapData`
  structures. Shared five-step pipeline: a mode gate restricting six grading-only chart kinds to
  `RunMode.GRADED`, the five `ChartFilters` global filters (Models/Status/Verdict/Category/
  Difficulty, each empty-means-all, with an unjoinable `task_id` dropped), a per-chart
  `COMPLETED`-status pre-filter (kind `SUCCESS_FAILED_INCOMPLETE_STACKED` keeps every row),
  out-of-domain per-chart-option fallback to its documented default with a one-time
  `chart_option_out_of_domain` warning log, and per-model/per-`(category, model)` grouping with
  a minimum-sample-size guard. IQR × 1.5 outlier handling (dropped before the mean for TTFT/time,
  never dropped from the tokens-per-task box geometry). Strict-domination Pareto frontier for the
  speed-vs-quality scatter. Every kind returns its own exact empty-state message rather than
  raising. Pure, stateless, Qt-free, asyncio-free, no I/O, safe from any thread, per
  `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`. Additively extends `backend/domain`'s
  `ChartSeries` (STORY-001) with `sample_sizes`/`low_sample_flags` (the minimum-sample-size
  guard) and `estimated_flags`/`reasoning_flags` (per-model `≈`/`⧉` markers on
  `AVG_TPS_PER_MODEL`, since total generation throughput is not directly comparable across
  estimated-throughput or reasoning-token-emitting models) — every other existing consumer of
  `ChartSeries` is unaffected by the new defaulted fields.

- Run-log event formatter (`backend/log_formatting/`): the `LogFormatter` Protocol (single
  method `format_event(event, verbosity)`) and factory `make_log_formatter()`, turning one
  `RunLogEvent` into a single-line HTML fragment for the Progress widget's live event log.
  Selects a strictly-nested Short ⊆ Normal ⊆ Verbose field set (§6.2), maps each of the eleven
  `RunLogEventKind` values to a tone class — info/primary/success/warning/error/muted — never a
  raw colour (§6.3), HTML-escapes every user- or model-supplied value and normalizes newlines to
  spaces, and truncates prompt/response excerpts at Normal only after escaping so no entity is
  ever split (§6.4). Prompt/response fields render as character-and-token counts only at Short,
  a truncated excerpt plus counts at Normal, and the full text plus counts at Verbose. Never
  raises to its caller: an unrecognized verbosity falls back to Normal (logged at warning level),
  an unrecognized event kind renders with the `info` tone and a generic tag, and a selected field
  absent from the event payload is simply omitted. Pure, stateless, Qt-free, asyncio-free, no
  I/O, not redacted (the Run Log is an explicitly not-redacted surface) per
  `11_Services_and_Algorithms/15_LOG_FORMATTING.md`. Also closes a gap left by STORY-001/STORY-003,
  both marked done without ever defining the `RunLogEvent`/`RunLogEventKind`/`RunLogVerbosity`
  domain types each had cited as the other's responsibility: adds all three to `backend/domain`
  per `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7.

- Rotating application-log and per-run event-log file writers (`backend/log_file_writer/`):
  factories `make_app_log_writer()` (targets `<app-data>/logs/app/app.log`, rotating at a 10 MB
  trigger with 5 retained backups — `app.log` -> `.1`, each `.N` -> `.N+1`, the oldest backup
  discarded) and `make_run_log_writer(run_id, unix_ts)` (targets
  `<app-data>/logs/run/run_<run_id>_<unix_ts>.log`, never rotated, always rendering the full
  Verbose `RunLogEvent` field set regardless of the on-screen `ui.run_log_verbosity`), plus
  `cleanup_run_logs()` — the startup count-based prune of `logs/run/` to 200 files, oldest
  embedded-timestamp first (only the count rule; the age and orphan rules are out of scope).
  Every write returns a typed `WriteOutcome` instead of raising, goes through a shared
  atomic-append primitive that creates each file at owner-only `0600` permissions atomically at
  creation (never a follow-up `chmod`) and truncates back to the pre-write size on a mid-write
  failure so a disk-full condition never leaves a partial line on disk. Qt-free, asyncio-free,
  imports only `backend/infra` and `backend/domain`, per
  `10_Domain_and_Data/07_FILE_LAYOUT.md` §4, §8, §9 and
  `11_Services_and_Algorithms/15_LOG_FORMATTING.md` §7.

- Settings and provider-config import/export service (`backend/import_export/`): the
  `ImportExportService` Protocol (`build_settings_import_preview`, `apply_settings_import`,
  `build_provider_import_preview`, `apply_provider_import`, `export_settings`,
  `export_providers`) and factory `make_import_export_service(providers_store, app_settings_store, event_bus)`. Parses a settings-or-provider-config YAML file in safe-load
  mode under the three-severity model (hard error / soft warning / soft info) fully before any
  store write, building an Added/Changed/Unchanged/Skipped preview; applying merges settings
  keys but replaces the provider registry wholesale (DD-55). Enforces the environment-variable-
  name-only `api_key` rule (D-R-18) — a literal secret is a hard error for that entry and is
  never persisted — plus a `base_url` syntactic-validity check mirroring the provider-edit
  dialog's own rule, the retired `id:`-field soft-info handling (DD-33), and the `name`-based
  (never `id`) collision pre-check via `ProvidersStore.get_by_name`. `provider_id` is
  intentionally never round-tripped — a fresh UUID4 is generated on every applied import. Qt-free,
  asyncio-free, imports only `ruamel.yaml`, `backend/domain`, `backend/errors`, `backend/events`,
  and the `ProvidersStore`/`AppSettingsStore` Protocols, per `10_Domain_and_Data/06_IMPORT_FORMATS.md`
  §§2, 5–9, 11. No UI wiring yet — the Settings dialog's Import/Export actions and Import Preview
  dialog are a later `ui/settings_dialog/` story.

- `RunDispatcher` port (`backend/concurrency/`) and its Qt-side facade (`adapters/qt_benchmark_flow/`):
  the `RunDispatcher` Protocol (`submit(fn)`, `shutdown(timeout_ms)`) and inline test double
  `make_inline_run_dispatcher()`, plus the real, persistent `pipeline-dispatcher` thread
  factory `make_run_dispatcher()` and the thin forwarding facade `QtBenchmarkFlow`/
  `make_qt_benchmark_flow(pipeline=...)`. Corrects a DD-38 conformance gap left by STORY-029:
  `BenchmarkFlowApi.start()`/`.resume()` previously spawned a brand-new `threading.Thread` on
  every call instead of reusing the single, process-lifetime dispatcher thread the
  specification requires — `make_benchmark_pipeline` now takes an injected `run_dispatcher`
  and hands its dispatch loop to it via `submit()` instead of constructing a thread inline.
  `QtBenchmarkFlow` holds only the backend `BenchmarkFlowApi` (not a `TaskRunner` — see
  `docs/stories/story-042-qt-benchmark-flow-facade.md`'s "Implementation notes" for why) and
  forwards every control/query call (`start`, `resume`, `pause`, `resume_paused`, `stop`,
  `shutdown`, `is_running`, `current_run`) unchanged. Per `08-E` §11 and
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a.

- Qt inference-activity bridge (`adapters/qt_inference_activity_bridge/`): the
  `QtInferenceActivityBridge` class and factory `make_qt_inference_activity_bridge(*, store, event_bus)`,
  forwarding the `InferenceActivityStore`'s `_inference_activity_changed` publications (already
  marshalled onto the Qt GUI thread by `adapters/qt_event_bus/`) to typed subscribers as
  `InferenceActivityChangedEvent` (no coalescing), and exposing the synchronous `is_inference_busy()`
  gateway for immediate in-place checks. The UI observes the gate only through this bridge, never the
  store directly — the sole UI-facing access point to the application-wide single-inference gate (D-R-06).
  Per `08-E` §13 and `08-Q` §8.2.

- Workspace controller (`adapters/workspace_controller/`): the `WorkspaceController` Protocol
  (`active() -> str`, `switch_to(name, hint=None) -> None`) and factory
  `make_workspace_controller(*, workspace_store, event_bus, container, workspace_factories)`, coordinating
  switches between the `"benchmark"` and `"task_editor"` workspaces. Lazily constructs each workspace's
  widget via an injected factory on first switch and retains it thereafter, writes the active workspace
  to the `WorkspaceStore` (STORY-039), reapplies the theme, applies optional focus/pre-open-path hints,
  and emits `_workspace_changed` on an actual workspace change (same-workspace switches are no-ops).
  A same-workspace `switch_to` is a no-op (no rebuild, no event). Invalid workspace names raise
  `ContractViolationError` (programmer error). The `WorkspaceHint` contract-local struct carries
  `open_paths: tuple[str, ...]` and `focus_widget: str | None`. Per `08-E` §19 and `08-Q` §9.1.

- QAbstractTableModel adapters for result tables (`adapters/qt_table_models/`): the factories
  `make_summary_table_model()`, `make_details_table_model()`, and `make_providers_table_model()`,
  each returning a `QAbstractTableModel`, plus the frozen row DTOs `SummaryTableRow`,
  `DetailsTableRow`, `ProviderTableRow`. Models read only frozen rows, hold no backend Protocol,
  and perform no I/O; mutations are always atomic whole-model resets via `set_rows()` using
  `beginResetModel()`/`endResetModel()` cycles. Each model conforms to Qt's
  `QAbstractTableModel` contract and is validated with `QAbstractItemModelTester`. Per
  `01_MODULE_INVENTORY.md` §5, `05_Result_Widget/implementation_structure.md` §6, and
  `08_Cross_Cutting/08-Q_event_payload_schemas.md` §6.

- Native file and folder picker dialogs (`adapters/native_pickers/`): the `NativePickers`
  Protocol (`save_file`, `open_file`, `open_folder`) and factory `make_native_pickers()` —
  native save/open-file/open-folder dialogs wrapping `QFileDialog` statics. Cancellation returns
  `None` (save_file/open_folder) or an empty tuple (open_file), never raises. Three contract-local
  options structs: `SavePickerOptions`, `FilePickerOptions`, `FolderPickerOptions` (with
  `allow_multiple: bool` selecting `getOpenFileName` vs. `getOpenFileNames`). Every method is
  synchronous, callable only on the Qt main thread (enforced by `icontract` preconditions on the
  factory guarding programmer invariants only), and raises `OsAdapterError` on dialog-subsystem
  failure with a fixed hand-written message, never leaking the raw platform exception. Imports
  PySide6 only — no `backend/*` and no `asyncio`. No `testing.py` fakes added in this story (UI
  consumers deferred to later UI stories). Per `08-E` §21a.

- System clipboard access (`adapters/clipboard/`): the `Clipboard` Protocol (`copy_text(text: str) -> None`) and factory `make_clipboard()` — writes to the system clipboard via
  `QGuiApplication.clipboard()`. Applies no redaction — clipboard content is user-owned data
  (per `08-E` §22), placed on the system clipboard unchanged. Synchronous, main-thread-only
  (enforced by `icontract` preconditions on the factory guarding programmer invariants),
  raises `OsAdapterError` if the clipboard is unavailable with a fixed message and chained
  cause. Imports PySide6 only — no `backend/*` and no `asyncio`. No `testing.py` fakes in this
  story (deferred to later UI stories). Per `08-E` §21b.

- File manager reveal actions (`adapters/file_system_actions/`): the `FileSystemActions`
  Protocol (`open_in_file_manager(path: str) -> None`) and factory `make_file_system_actions()` —
  reveals a file or folder in the OS file manager via per-OS `subprocess` commands (macOS:
  `open -R`; Windows: `explorer /select,`; Linux: `xdg-open` the containing folder for a file,
  or the folder itself for a folder target). Per-OS branches isolated in `_internal/`. Synchronous,
  main-thread-only (enforced by `icontract` preconditions on the factory guarding programmer
  invariants), raises `OsAdapterError` if the path does not exist or the file manager cannot
  launch, with a fixed message and chained cause. Uses `subprocess.run(..., check=False)` since
  `explorer.exe` on Windows often exits non-zero despite success. Imports PySide6 only — no
  `backend/*` and no `asyncio`. No `testing.py` fakes in this story (UI consumers deferred). Per
  `08-E` §21c.

- Design tokens and stylesheet generator (`ui/theme/`): the immutable frozen token containers
  `ThemeTokens` (carrying all 30 colour roles, verdict/health palettes, typography, spacing,
  radius, border, focus, shadow, and motion tokens per platform), factories
  `make_dark_theme_tokens(*, platform_kind)` and `make_light_theme_tokens(*, platform_kind)`
  assembling the Dark and Light theme containers, and the stylesheet/palette builders
  `build_stylesheet(tokens)` and `build_palette(tokens)` that compile tokens into the
  application-level Qt stylesheet (targeting dynamic-property role selectors) and `QPalette`.
  Exports colour-resolution accessors `resolve_color(tokens, role)`, `resolve_verdict_color(tokens, state)`,
  and `resolve_health_color(tokens, state)` for use by charts, badges, and status indicators.
  Also exports the enums `PlatformKind`, `VerdictDisplayState`, and `HealthDisplayState` (all
  types importable from `ollama_llm_bench.ui.theme`). The module is the single styling authority
  (ADR-0001, 08-D §16): the only code permitted to call `setStyleSheet()` and the only code
  permitted to assemble stylesheets from raw design tokens. No `asyncio`. Per `08-D` §1–§16.

### Added (Phase 0 continued)

- Repository scaffold for the v3 rewrite: `pyproject.toml` (uv/ruff/mypy/import-linter/pytest
  configuration), `justfile` (local CI-parity task runner), the `src/ollama_llm_bench/`
  three-layer package tree (`backend/`, `adapters/`, `ui/`), the `tests/` tree, the
  traceability tooling (`scripts/trace.py`, `scripts/validate_traceability.py`), and the two
  GitHub Actions workflows (`pr-gate.yml`, `release.yml`).

- Three accepted Architecture Decision Records: `docs/adr/0001-programmatic-qt-widgets-theming.md`,
  `docs/adr/0002-scoped-reactive-stores-and-event-bus.md`,
  `docs/adr/0003-uv-build-and-unsigned-distribution.md`.

- Backend domain vocabulary (`backend/domain/`): 27 closed enumerations (`StrEnum`), 33
  cross-boundary `msgspec.Struct` records, 7 type aliases, 14 constrained types per
  `docs/v3_specification/10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, establishing the
  foundational Qt-free domain model for Phase 1.

- Error taxonomy and secret redaction (`backend/errors/`): 27 exception classes forming the
  four-category error taxonomy (`TransientError`, `PermanentError`, `UserError`,
  `ProgrammerError`) with 20 leaves plus 3 programmer-error leaves; the `ErrorContext`
  redaction-safe carrier; and the `redact()` and `redact_for_log` secret-redaction module
  guarding against provider credential leaks per
  `docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` and
  `docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md`.

- Typed event bus core (`backend/events/`): the `EventBus` and `Subscription` service Protocols
  (`typing.Protocol`, no concrete implementation yet), 36 event payload types as frozen
  `msgspec.Struct` records with full type safety and schema validation, and 36 signal-name
  string constants — the complete closed catalogue per
  `docs/v3_specification/08_Cross_Cutting/08-J_event_bus_catalog.md` and
  `docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`. The Qt delivery
  bridge and the concrete `EventBus` implementation live in the adapter layer (`adapters/qt_event_bus/`,
  a later story).

- Cross-cutting infrastructure (`backend/infra/`): the `Clock` Protocol (injectable,
  testable time source with `now_utc()` and `monotonic_ms()`) backed by a `SystemClock`
  factory; the two-stream `structlog` logging configuration (`configure_logging` for
  `app.*` with rotating file, `INFO` level, full redaction; `open_run_log` context manager
  for per-run `run.*` logs with `DEBUG` level and no redaction) with non-blocking
  queue-and-worker-thread I/O; the `PlatformDetector` Protocol stub (narrow, structurally
  typed, carrying only `app_data_root` until STORY-005); and the path-resolution surface
  (`app_log_path`, `run_log_path`, and their directory variants) composing over the platform
  detector per `docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md` and
  `docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md`.

- Platform detection and OS-appropriate paths (`backend/platform/`): the `PlatformDetector`
  Protocol and `PlatformKind` enum classifying the host into `MACOS`, `WINDOWS`, `LINUX`,
  or `UNKNOWN`; the immutable `PlatformProfile` DTO carrying OS version, application-data
  root, home path, desktop path, path separator, line ending, filesystem properties, and
  native theme support; the factory `make_platform_detector()` binding to the real host
  environment; and `create_app_data_dir()` for recursive, idempotent creation of the
  OS-appropriate app-data directory per `docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md`.

- Provider registry and canonical LLM client protocol (`backend/provider_registry/`): the
  `ProviderRegistry` Protocol (three methods: `list_enabled()`, `get_client(provider_id)`,
  `reload()`) managing one `LLMClient` per enabled, structurally valid provider; the canonical
  `LLMClient` Protocol defining the chat/embedding/health-probe contract every provider
  adapter implements; the `ClientBuilder` type alias for per-`ProviderType` client constructors;
  and the `make_provider_registry(...)` factory guarded by `icontract`. Routes benchmark
  targets by `provider_id` alone; resolves each provider's api-key from the named environment
  variable; rebuilds atomically on configuration change; and defers closing superseded clients
  until the single-inference gate is idle (SPEC-045) per `08-E` §9–§10 and
  `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`.

- Task file loading and validation (`backend/task_files/`): the `TaskFileLoader` Protocol
  (loader-tolerant `load(source_path) -> tuple[BenchmarkTask, ...]` skipping malformed
  individual tasks without raising, raising `TaskFileError` only for whole-file rejection) and
  `TaskFileValidator` Protocol (editor-strict `validate(source_path) -> FileValidationResult`
  converting all content problems to file-level `ValidationIssue`s, raising `TaskFileError`
  only for OS-level read failures), plus factories `make_task_file_loader()` and
  `make_task_file_validator()`. Both use a shared three-level (field/task/file), three-severity
  (clean/info/warning/error) validation cascade with `max_severity` aggregation, implementing
  seven validation rules (non-`.yaml`/`.yml` extension, empty file, duplicate `task_id`, empty
  `question`, empty `category`, overlong prompt, retired `task_type` key) so their verdicts
  never diverge. Invalid `difficulty` and non-bool `cosine_enabled` fallback to struct defaults
  rather than dropping tasks per `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.

- Comment-preserving YAML formatter (`backend/yaml_formatter/`): the `YamlFormatter` Protocol
  (the sole task-file writer; `load_document(source_path) -> TaskFileDocument` round-tripping
  via `ruamel.yaml` with comments; `save(*, document, target_path, format_on_save) -> SaveResult`
  never raising on I/O failure), implementing canonical 14-key field ordering (absent keys not
  inserted, unknown keys preserved after canonical set), comment preservation across reordering
  (end-of-line, standalone, sequence-item, file-head/tail) guarded by `icontract` postcondition
  on comment-token count (`FormatterDefect` on mismatch), atomic save (temp file with `fsync()`
  and `os.replace()`; target untouched on failure), and Form B/C → Form A top-level normalization
  via factory `make_yaml_formatter()` per `11_Services_and_Algorithms/12_YAML_FORMATTER.md`.
  Testing fakes in `testing.py`. First use of `ruamel.yaml` and property-based round-trip
  testing via Hypothesis.

- Run Summary confirmation dialog (`ui/common_dialogs/`): the factory
  `make_run_summary_dialog(*, gateway, run_validator, request, parent=None) -> QDialog | None`
  and the narrow adapter gateway `RunSummaryGateway` Protocol (`readiness_snapshot()`,
  `start_run(request)`). Opens only after a preflight re-check passes (returns `None` if
  environment is broken, leaving widget fields intact — see `07_Common_Dialogs/run_summary_dialog.md` §8),
  presents a mode-aware summary for user review with per-mode sections (work-to-be-done,
  settings snapshots, warnings callout), and on Start Benchmark issues `gateway.start_run(request)`
  and closes. The dialog never edits configuration — it presents and confirms only. Carries no
  dependencies on `NewBenchmarkGateway` or any sibling UI module; the concrete adapter may
  satisfy both Gateway Protocols with one class or two thin ones (compose.py decision). Per
  `07_Common_Dialogs/run_summary_dialog.md` §§6, 8, 12 and `08-E` §7b.2.

- New Benchmark panel completion (`ui/new_benchmark/`): the `RunValidator` Protocol (design
  decision 1 in STORY-055) with a single method `validate(request) -> tuple[ValidationEntry, ...]`
  producing hard-error/soft-warning entries, `ValidationEntry` and `RunValidationSeverity` DTOs
  in `models.py`, and a new required field `run_validator: RunValidator` on the
  `NewBenchmarkCollaborators` dependency bundle. The widget now wires the Judge section (provider
  and model selection, analysis toggle, embedding-status row per 02_New_Benchmark_Widget §44),
  the Advanced Options collapsible section (per-run setting overrides, DD-47 carriage rule per
  §47), validation gating of the Start button (hard-error check, soft-warning distinction, and
  the single-inference-gate `IDLE`-only gate per §48 and `08-E` §13), the Start flow (assembles
  `RunStartRequest`, opens the Run Summary dialog, calls `gateway.start_run(request)` on
  confirm, transitions to read-only Locked state on `_run_started`), and integrates with the
  mode-selector and task-files/test-models sections previously delivered by STORY-054.
  Per `02_New_Benchmark_Widget/description.md` §§6, 44, 47, 48; `state_machine.md`; and
  `08-E` §7b.2.

- Settings service public registry re-export (`backend/settings/`): the `PER_RUN_OVERRIDABLE`
  constant (a `frozenset[SettingKey]` of 35 keys that may be overridden per run) is now
  re-exported from both `api.py` and `__init__.py`, making it available to UI modules that
  assemble per-run setting overrides (the Advanced Options widget). Previously internal to
  `_internal/registry.py`, it is now part of the public contract. No change to the implementation
  or the registry itself — purely a visibility change to support the New Benchmark panel's
  Advanced Options section (STORY-055). Per `08-C` §2 and `08-E` §8a.

- Progress widget shell, run controls, and stability sub-controllers (`ui/progress/`): the
  factory `make_progress_widget(*, bus, gateway, log_formatter) -> QWidget`, the `ProgressGateway`
  Protocol (08-E §7b.4 base surface plus two locally-added extensions: `list_runs()` for the
  rename-pencil's dialog reuse and `is_run_active()` for SPEC-098's bounded reconciliation timer),
  and the locally-declared `RunStage(StrEnum)` with ten values (INITIALIZING, INFERENCE,
  KEYWORD_CHECK, COSINE_CHECK, JUDGE_CHECK, FINISHING, COMPLETED, FAILED, STOPPED, PAUSED)
  parsed from the backend's plain-string stage fields. The header renders the stage badge in
  one of six tones (info/primary/warn/success/error/mute) via `ui.theme.resolve_color()`, the
  run-name label, the rename pencil (visible only while actively executing per 08-L §1's
  no-placeholder-UI rule), Pause/Resume toggle, and Stop with an inline confirmation modal
  (`QMessageBox.question`) plus the SPEC-098 draining status line (exact text "Pausing —
  finishing the current call…" / "Stopping — cancelling the current call…" per description.md
  §3.4). `CountersController` derives per-`ResultStatus` counters and stage-bar segment weights
  from each `_progress_updated` payload, coalesces bursts within a single Qt event-loop turn via
  `QTimer.singleShot(0, ...)` so the last payload wins, and supplies ETA and provider/model
  labels. `StabilityController` derives the model band (ok/warn/excluded), provider band
  (closed/warn/open with manual-probe action via `gateway.manual_provider_probe()` never a direct
  breaker call per D-R-06), and a persistent red judge-model-exclusion callout (EC-PROV-4b)
  surviving later stability events. The SPEC-098 bounded reconciliation timer on entering
  Pausing/Stopping races a `QTimer` against the terminal `EventBus` event; on timeout expiry it
  reconciles via `gateway.is_run_active()` + `gateway.run_header(run_id).status`, using the
  specific terminal/paused `RunStage` (not generic buckets), mirrors the main-window close-handler
  race pattern (first one wins). Deliberately out of scope: the ViewingPastRun Model-summary
  panel and `compose.py` wiring of the real `ProgressGateway` (Phase 11). Per
  `04_Progress_Widget/description.md` §§3–6, 10, 12;
  `implementation_structure.md` §§3, 4.1; `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.4;
  and `08_Cross_Cutting/08-D_color_palette_and_typography.md` §16.

- Progress widget Current-task sub-controller (`ui/progress/`): the `CurrentTaskController`
  implementation, subscribing to six events (`_inference_started`, `_inference_progress`,
  `_judge_started`, `_judge_completed`, `_task_completed`, `_task_retry`) and deriving the
  `CurrentTaskViewModel`. The in-flight task grid displays the active task id, stage, task time,
  and timeouts. The Inference progress sub-row (`context=BENCHMARK_TASK`) shows waiting-for-first-token
  sub-state A and generating sub-state B, rendered from cached `_inference_progress` events; visibility
  reset on `_inference_started`, hidden on `_task_completed`, and showing a placeholder during judge
  phase. The Judge progress sub-row (`context=BENCHMARK_JUDGE`) has parallel waiting and receiving
  sub-states, shown/reset on `_judge_started`, hidden on `_judge_completed`/`_task_completed`. Both
  sub-rows are verbosity-independent and marked with a leading `~` when token counts derive from the
  4-character heuristic (EC-RUN-17). The retry line renders in error tone with the classified reason
  while active and clears on task completion. Context filter accepts only `BENCHMARK_TASK` and
  `BENCHMARK_JUDGE`, ignoring `RUN_ANALYSIS` and `PROVIDER_TEST` progress events. Defensive
  out-of-order handling for a judge event lacking a completed main inference. Covers EC-RUN-17,
  EC-RUN-18, EC-RUN-19, EC-RUN-23, EC-PROV-1. Per `04_Progress_Widget/description.md` §§7, 7.1;
  `implementation_structure.md` §4.2; `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.4;
  `08-D_color_palette_and_typography.md` §16; and `08-Q_event_payload_schemas.md` §4.1a.

- Progress widget run event-log sub-controller (`ui/progress/`): the `LogController`
  implementation, subscribing to fifteen log-source events (`_inference_started`,
  `_inference_completed`, `_task_completed`, `_judge_started`, `_judge_completed`, `_task_retry`,
  `_stage_changed`, `_provider_switched`, `_model_switched`, `_run_stopped`, `_run_finished`,
  `_run_failed`, `_model_stability_changed`, `_provider_registry_reloaded`, `_log_cleared`).
  Caches every raw event and renders one HTML line per event via `LogFormatter` at the
  user-selected verbosity. The toolbar exposes four controls: a verbosity dropdown (Short/Normal/Verbose,
  persisted to `ui.run_log_verbosity`), a case-insensitive search filter, a Clear-view action
  (empties display while retaining cached events for re-render on verbosity change), and a
  bounded-buffer status. The display buffer is capped by `ui.run_log_max_lines` (range 1,000–500,000),
  with oldest lines evicted first when capacity is exceeded; the per-run log file is never trimmed
  by the widget. A log-write-failure warning indicator surfaces when the run-log file writer reports
  an error, allowing in-memory buffering to continue. Auto-scroll toggle persisted to
  `ui.auto_scroll_run_log` follows the newest line by default, suspending on manual scroll-up.
  Past-run log replay loads and renders a prior run's saved log on `_run_id_changed` when no run
  is active via `ProgressGateway.load_past_log(run_id)`. Coalesced per-event view repaints via Qt
  event-loop coalescing to enforce EC-PERF-3. Covers EC-LOG-1, EC-LOG-3, EC-PERF-3, EC-PROV-4a.
  Per `04_Progress_Widget/description.md` §§8, 8.3–8.5; `implementation_structure.md` §4.3;
  `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.4; and `08-D_color_palette_and_typography.md` §16.

- Result widget Charts tab (`ui/results/_internal/charts_tab/`): the one-chart-at-a-time canvas
  with twelve chart kinds (mode-aware: SYNTHETIC/TASKS offer six, GRADED offers all twelve),
  non-wrapping skip-empty prev/next navigation, a chart-kind dropdown, global filter chips (five
  domains), per-chart option controls, chart-click drill-down into the Details tab, a detach-to-window
  action for independent side-by-side viewing, and theme-aware PNG/SVG export at fixed off-screen
  resolution. Mounted into the existing `ResultController`/`ResultView` shell (STORY-061) via
  `ChartsTabController`/`ChartsTabView`. The `FooterController`'s Export buttons now work for the Charts tab.
  Per `05_Result_Widget/tabs/charts_tab.md` §§1–12 and `implementation_structure.md` §5.3.

- File system actions binary write methods (`adapters/file_system_actions/`): two new methods on
  the `FileSystemActions` Protocol — `write_export_file_bytes(*, filename: str, content: bytes) -> str`
  and `write_binary_file(*, path: str, content: bytes) -> None` — as bytes-capable counterparts to the
  existing text-only `write_export_file`/`write_text_file` (STORY-061). Used by the Charts tab's PNG
  export. Both methods apply the same atomic temp-file-then-rename structure and collision-suffix rules
  as their text counterparts. Per `08-E` §21c (extended in STORY-064).

- Settings dialog shell, Providers tab, and Provider Edit sub-dialog (`ui/settings_dialog/`):
  the modal dialog's tab strip/footer/dirty-indicator chrome with auto-`probe_all()`-on-open;
  the Providers tab (a `QTableView` over the existing `adapters/qt_table_models` provider table
  model, with hover-revealed Test/Edit/Reset/Delete row actions and an Enabled toggle) plus its
  embedding-selection section (provider/model dropdowns filtered to embedding-likely models,
  a Show-all-models toggle, a Test Embedding action, persisted-selection and first-start
  bootstrap init from `embedding.selected_provider_name`/`selected_model_name`); and the
  Provider Edit sub-dialog (identity/endpoint/secret-card fields, duplicate-name and
  env-var-name-only validation, and two independent Test actions — reachability and inference —
  both gated on the single-inference-activity store). The Health Dot and Auth badge are two
  independent pure functions (`provider_test_status_to_health`/`provider_auth_badge`) — the
  former of `ProviderTestStatus`, the latter of credential-name presence plus env-var
  resolution — never conflated. The full 13-method `SettingsGateway` Protocol is declared in
  `protocols.py` per `08-E` §7b.6, though this story exercises only 8 of them; the General tab
  and the Save/Import/Reset transactions are a later `ui/settings_dialog/` story (STORY-067), as
  is the concrete `SettingsGateway` wiring into `compose.py` (Phase 11). Qt-free/asyncio-free
  boundary rules hold throughout; no `setStyleSheet`, colour literal, or literal secret reaches
  the working-copy `ProviderConfig`. Per `06_Settings_Dialog/description.md` §§1.2, 1.4, 3.2–3.4,
  `sub_dialogs/provider_edit.md` §§5.1, 8.2, 9, and `08-E` §§7b.6, 13.

- About dialog and generic Error dialog (`ui/common_dialogs/`): two pure-presentation factory
  functions — `make_about_dialog(collaborators, version, data_folder_path, parent)` and
  `make_error_dialog(payload, clipboard, event_bus, parent)` — plus supporting DTOs
  `AboutDialogCollaborators`, `AboutDialogViewModel`, `ErrorDialogPayload`, `ErrorDialogPattern(StrEnum)`
  (RECOVERABLE / ACTION_AVAILABLE / FATAL), and `ErrorDialogAction`. The About dialog renders the
  application identity block (name, optional build version, description, repository link), the
  application-data-folder path row with Copy-path and Open-folder actions, and emits confirmation
  and failure toasts on the injected `EventBus`. The Error dialog renders a caller-supplied payload
  in one of three fixed patterns with pattern-specific footer button sets: recoverable and
  action-available patterns include an optional Copy Details button; the fatal pattern includes only
  a destructive Quit button with no Close or Escape. Both dialogs remain open after actions (Copy,
  Open-folder, repository link) and are fully usable on `OsAdapterError` failures; folder-action and
  copy-details failures emit matching failure toasts. Wiring into `compose.py` and connection to the
  Main Window About menu action or the Notification Service are deferred to later stories. File system
  actions adapter gains a new `open_url(url)` method (raises `OsAdapterError`) for opening the
  repository link in the user's default browser. Per `07_Common_Dialogs/about_dialog.md` §§4–6, 11;
  `error_dialog.md` §§5–6, 9, 12; and `08-E` §21c.
