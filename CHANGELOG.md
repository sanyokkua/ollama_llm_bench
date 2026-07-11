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
