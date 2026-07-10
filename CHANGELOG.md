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
