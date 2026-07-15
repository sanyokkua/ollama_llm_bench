---
id: STORY-037
title: Write the rotating application log and the per-run log files
status: done
spec_clauses:
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#41-applicationsystem-log
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#42-benchmark-run-event-log
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#81-application-log-rotation
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#82-run-log-cleanup
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#9-filesystem-permissions
  - 11_Services_and_Algorithms/15_LOG_FORMATTING.md#7-the-two-logging-streams
modules:
  - backend/log_file_writer/
acceptance_criteria:
  - STORY-037-AC-1
  - STORY-037-AC-2
  - STORY-037-AC-3
  - STORY-037-AC-4
edge_cases:
  - EC-FL-9
  - EC-FL-10
depends_on:
  - STORY-004
  - STORY-005
owner: coder
estimate: M
---

# STORY-037 — Write the rotating application log and the per-run log files

## Goal

Give the application its two on-disk log sinks: a factory for the rotating application log at
`<app-data>/logs/app/app.log` and a factory for a per-run benchmark log at
`<app-data>/logs/run/run_<run_id>_<unix_ts>.log`, each writing off the UI thread with owner-only
permissions, the per-run file always recording the full Verbose field set regardless of the
on-screen verbosity, plus the startup run-log count-based cleanup that prunes the oldest logs down
to 200.

## In scope

- `backend/log_file_writer/`: the writer factories for the application-log sink and the per-run
  log sink, plus a `backend/log_file_writer/testing.py` fake.
- The per-run log file path template `run_<run_id>_<unix_ts>.log` under `<app-data>/logs/run/`,
  and the application-log path `<app-data>/logs/app/app.log` with its rotation backups.
- The run-log startup cleanup: when more than 200 run logs remain, delete the oldest until 200
  remain (run logs are pruned by count, never rotated).
- Filesystem safety: `0600` owner-only permissions on every log file, off-UI-thread writes, and
  the atomic temp-then-rename pattern so a disk-full write leaves no partial file.

## Out of scope

- Formatting the on-screen Run Log line — owned by `backend/log_formatting/` (STORY-036); this
  writer formats events to a plain-text line for the file independently and always at the full
  Verbose field set.
- The `structlog` App Log record pipeline and its `redact_for_log` processor — owned by
  `backend/infra/` / `backend/errors/`; this writer provides the rotating file sink the App Log
  stream writes through, not the record-construction or redaction logic.
- Resolving the OS-specific `<app-data>` directory and creating the directory tree — owned by
  `backend/platform/` (STORY-005) and the first-launch directory creation; this writer consumes
  the resolved paths.
- Progress-widget surfacing of a write-failure warning indicator — owned by `ui/progress/`.

## Spec inputs

- `10_Domain_and_Data/07_FILE_LAYOUT.md#41-applicationsystem-log` — the app-log location, the
  rotating-file model, and its backups.
- `10_Domain_and_Data/07_FILE_LAYOUT.md#42-benchmark-run-event-log` — the per-run file location,
  the `run_<run_id>_<unix_ts>.log` template, and the never-rotated bound-by-task-count rule.
- `10_Domain_and_Data/07_FILE_LAYOUT.md#81-application-log-rotation` — the app-log rotation
  policy this sink implements.
- `10_Domain_and_Data/07_FILE_LAYOUT.md#82-run-log-cleanup` — the startup count-based prune to
  200 run logs, oldest first.
- `10_Domain_and_Data/07_FILE_LAYOUT.md#9-filesystem-permissions` — the `0600` owner-only ACL on
  every log file.
- `11_Services_and_Algorithms/15_LOG_FORMATTING.md#7-the-two-logging-streams` — the Run Log vs
  App Log split and the rule that the run-log file always records the full Verbose field set.

## Design constraints

- `backend/log_file_writer/` is Qt-free and asyncio-free; it imports only `backend/infra`
  (`01_MODULE_INVENTORY.md` §4.5). No PySide6 — writes run off the UI thread.
- File writes use the atomic temp-then-rename pattern (or an append with fsync appropriate to the
  rotation model) so an interrupted or disk-full write never leaves a partial or truncated file;
  the failure is surfaced, not swallowed.
- Every log file is created with `0600` owner-only permissions (defence in depth — the file may be
  shared when reporting a bug).
- The per-run file is written at the full Verbose field density regardless of the on-screen
  `ui.run_log_verbosity`; run logs are pruned by count at startup, never rotated by size.
- `icontract` on any `api.py` symbol guards programmer invariants only — never file content.

## Acceptance criteria

### STORY-037-AC-1

Given a `run_id` and a start timestamp, when the per-run writer is created, then it writes to a
file named `run_<run_id>_<unix_ts>.log` under `<app-data>/logs/run/`, and each written event line
carries the full Verbose field set regardless of the configured on-screen verbosity.

### STORY-037-AC-2

Given more than 200 run-log files exist under `<app-data>/logs/run/`, when the startup run-log
cleanup runs, then the oldest files are deleted until exactly 200 remain and no other files are
touched.

### STORY-037-AC-3

Given a log write that fails mid-write with a disk-full error, when the writer reports the
failure, then no partial or truncated file is left at the target path and the failure is
surfaced rather than swallowed.

### STORY-037-AC-4

Given any log file the writer creates, when it is created, then its filesystem permissions are
`0600` (owner read/write only).

## Test plan

- STORY-037-AC-1 — integration (against a `tmp_path` app-data tree), colocated
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_writer.py`,
  `test_per_run_file_name_and_verbose_field_set`.
- STORY-037-AC-2 — integration (populate >200 run logs in `tmp_path`), colocated
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`,
  `test_startup_cleanup_prunes_oldest_to_200`. Covers EC-FL-10.
- STORY-037-AC-3 — integration (simulated disk-full write), colocated
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_atomic_write.py`,
  `test_write_failure_leaves_no_partial_file`. Covers EC-FL-9.
- STORY-037-AC-4 — integration, colocated
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_permissions.py`,
  `test_log_files_are_owner_only`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-037.
- [x] EC-FL-9 and EC-FL-10 have passing tests.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/log_file_writer/`.
- [x] An architecture test confirms the module imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-037
  (remaining `just trace-check` failures are pre-existing, unrelated to this story — see
  Notes below).
- [x] The module inventory is unchanged.

## Notes

- `just trace-check` reports pre-existing failures unrelated to this story: dangling
  `EC-PERSIST-6`, unmapped `EC-PROV-1a`/`EC-RUN-1a`, and `EC-IMP-*` edge cases named by the
  still-unimplemented `STORY-038` (`backend/import_export/`). Verified by stashing this story's
  changes and re-running `just trace-check`: the identical failure set reproduces on the
  pre-existing tree. STORY-037's own acceptance criteria and edge cases (EC-FL-9, EC-FL-10)
  resolve cleanly with no orphans.
- `just coverage-layers`' UI-layer coverage steps report "No data to report" because no `ui/*`
  code exists yet in this phase — pre-existing, unrelated to this story. The backend-layer gate
  (`>=90%`) passes at 91%, and `backend/log_file_writer/`'s own implementation files are at
  100% statement+branch coverage (only `protocols.py`'s `...` stub bodies and `testing.py`'s
  fakes — exercised only by downstream consumers, not yet written — read below 100%, matching
  every sibling module's own pattern).
