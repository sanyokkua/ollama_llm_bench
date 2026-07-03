# File Layout

**Status:** Draft
**Owner:** architect
**Audience:** coder, user
**Last Updated:** 2026-05-22
**Cross-references:** 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md, 10_Domain_and_Data/05_EXPORT_FORMATS.md, 10_Domain_and_Data/08_REDACTION_PATTERNS.md, 11_Services_and_Algorithms/15_LOG_FORMATTING.md

This document is the single reference for every file and folder the application creates on disk. It fixes the per-operating-system application data directory, the subfolder tree, the SQLite database and its write-ahead-log companion files, the two logging streams, the rotation and cleanup policies, and the filesystem permissions — in particular the owner-only permission on any file that may contain a secret.

---

## Table of Contents

1. Application data directory per operating system
2. Directory tree
3. The SQLite database and WAL files
4. Logging streams
5. Exports folder
6. Backups folder
7. Temp folder
8. Rotation and cleanup policies
9. Filesystem permissions
10. First-launch creation
11. Edge cases

---

## 1. Application data directory per operating system

The application stores all of its state under a single per-user application data directory, written `<app-data>` throughout the specification. It is resolved once at startup, by the platform detector, and cached for the process lifetime.

| Operating system | `<app-data>` path |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/` |
| Linux | `$XDG_DATA_HOME/OllamaLLMBench/`, falling back to `~/.local/share/OllamaLLMBench/` when `XDG_DATA_HOME` is unset or empty. |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\`, typically `C:\Users\<user>\AppData\Local\OllamaLLMBench\`. |

The directory name `OllamaLLMBench` is identical on every platform. The internal subtree below `<app-data>` is identical on every platform; only the path separator differs (`/` on macOS and Linux, `\` on Windows).

Task files (the YAML files described in `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`) are **not** stored under `<app-data>`. They are user-owned documents kept anywhere on the filesystem and opened on demand.

## 2. Directory tree

```
<app-data>/
├── ollama_llm_bench.db          # SQLite database — primary persistent store
├── ollama_llm_bench.db-wal      # SQLite write-ahead log (present while WAL is active)
├── ollama_llm_bench.db-shm      # SQLite shared-memory index (present while WAL is active)
├── logs/
│   ├── app/
│   │   ├── app.log              # current application/system log
│   │   ├── app.log.1            # rotated application log, newest backup
│   │   ├── app.log.2
│   │   └── ...                  # up to app.log.5
│   └── run/
│       └── run_<run_id>_<unix_ts>.log   # one benchmark run-event log per run
├── exports/
│   └── <exported files>         # see 05_EXPORT_FORMATS.md
├── backups/
│   └── settings_<unix_ts>.yaml  # automatic settings backups
└── temp/
    └── <transient files>        # scratch space; cleared at every startup
```

| Path | Purpose |
|---|---|
| `ollama_llm_bench.db` | The SQLite database holding runs, results, provider configs, embedding config, model capabilities, and settings. Schema is defined in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`. |
| `logs/app/` | The rotating application/system log stream (§4.1). |
| `logs/run/` | The per-run benchmark run-event logs (§4.2). |
| `exports/` | The destination for direct exports when the save-directly toggle is on (see `10_Domain_and_Data/05_EXPORT_FORMATS.md`). |
| `backups/` | Automatic settings backups (§6). |
| `temp/` | Scratch space for in-progress writes and other transient files. Emptied on every startup. |

## 3. The SQLite database and WAL files

| File | Description |
|---|---|
| `ollama_llm_bench.db` | The database file. Always present after first launch. |
| `ollama_llm_bench.db-wal` | The write-ahead log. Present whenever the database is open in WAL journal mode and removed on a clean checkpointing shutdown. |
| `ollama_llm_bench.db-shm` | The WAL shared-memory index. Present alongside the `-wal` file and removed with it. |

Rules:

- The database opens in WAL journal mode. The `-wal` and `-shm` files are an expected, normal part of the on-disk state and must never be deleted by hand while the application is running.
- On a clean shutdown the database is checkpointed and the `-wal` and `-shm` files are released. On an unclean shutdown they remain and are recovered automatically the next time the database is opened.
- The three database files are always treated as one unit. A backup either includes all three (taken while the application is not running) or relies on SQLite's online-backup mechanism, never a raw copy of the `.db` alone while the application is running.
- The full pragma set, table definitions, and indexes are specified in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`.

## 4. Logging streams

The application maintains **two independent logging streams**. They never share a file.

### 4.1 Application/system log

| Aspect | Rule |
|---|---|
| Location | `<app-data>/logs/app/app.log`. |
| Scope | Application lifecycle, configuration, errors, warnings, background-service activity — everything not tied to a single benchmark run. |
| Format | One structured line per record, UTF-8, LF line endings. Each record carries a timestamp (ISO 8601 UTC), a level, a logger name, and the message. |
| Lifetime | Spans the whole installed life of the application across many sessions. |
| Rotation | Size-based; see §8.1. |
| Redaction | Every record is emitted through `redact_for_log` (see `10_Domain_and_Data/08_REDACTION_PATTERNS.md`). |

### 4.2 Benchmark run-event log

| Aspect | Rule |
|---|---|
| Location | `<app-data>/logs/run/run_<run_id>_<unix_ts>.log`, one file per benchmark run. |
| Filename | `run_` then the integer run id, then an underscore and the run's start time as a Unix timestamp in seconds, then `.log`. Example: `run_3_1747407187.log`. |
| Scope | The event stream of a single benchmark run: stage transitions, per-task inference start and completion, retries, evaluation-layer outcomes, verdicts, and run-level errors. |
| Format | One structured line per event, UTF-8, LF line endings, with an ISO 8601 UTC timestamp, the event kind, and the event payload. |
| Lifetime | Created when the run starts; closed when the run reaches a terminal state. Never reopened or appended after the run ends. |
| Rotation | None — a run log is never rotated. It is bounded by the run's task count. Cleanup is age- and count-based; see §8.2. |
| Redaction | Every event is emitted through `redact_for_log`. |

The on-screen Progress widget log is rendered from the same event stream; the run-event log file is the durable record of it.

## 5. Exports folder

`<app-data>/exports/` holds files written by the "save directly to app data folder" export path. Filenames follow the canonical patterns in `10_Domain_and_Data/05_EXPORT_FORMATS.md`. The application only writes here; it never reads back or deletes files in this folder automatically — exported files are user-owned artefacts. The folder is created on first direct export if it does not yet exist.

## 6. Backups folder

`<app-data>/backups/` holds two kinds of file.

| File pattern | Purpose | Created when |
|---|---|---|
| `settings_<unix_ts>.yaml` | An automatic snapshot of the application settings, in the settings export format (see `10_Domain_and_Data/06_IMPORT_FORMATS.md`). | Before the application applies a settings import or a settings reset, so the prior state can be recovered. |

The `backups/` folder holds only automatic settings backups.

## 7. Temp folder

`<app-data>/temp/` is scratch space. The atomic write pattern used across the application — write to a temporary file, then rename it into the final location — uses this folder, or the destination folder, for the temporary file. The temp folder is emptied at every application startup; nothing in it is expected to survive a restart. No code may store anything in `temp/` that it needs after a restart.

## 8. Rotation and cleanup policies

### 8.1 Application log rotation

| Parameter | Value |
|---|---|
| Trigger | The current `app.log` reaching 10 MB. |
| Action | `app.log` is renamed to `app.log.1`; each existing `app.log.N` is renamed to `app.log.N+1`; a fresh empty `app.log` is opened. |
| Retained backups | 5 (`app.log.1` through `app.log.5`). |
| Discard | `app.log.5`, when it would be pushed to `app.log.6`, is deleted. |
| Total ceiling | At most 60 MB across the current file and five backups. |

### 8.2 Run log cleanup

Run logs are not rotated; they are pruned. At application startup, after the crash-recovery sweep, the run-log cleanup runs:

| Rule | Action |
|---|---|
| Age | A run log whose corresponding run finished more than 90 days ago is deleted. |
| Count | When more than 200 run logs remain, the oldest are deleted until 200 remain. |
| Orphans | A run log whose `run_id` no longer exists in the database (the run was deleted) is deleted. |

The age rule and the count rule are both applied; whichever removes more files governs.

### 8.3 Backups cleanup

| Rule | Action |
|---|---|
| Settings backups | At most 20 `settings_<unix_ts>.yaml` files are kept; the oldest beyond 20 are deleted at startup. |

### 8.4 Temp cleanup

The entire contents of `<app-data>/temp/` are deleted at every startup, before any subsystem uses the folder.

## 9. Filesystem permissions

The permission policy distinguishes files that may contain a secret from files that may not. A secret here means an API key value or any text from which one could be reconstructed.

| Path | macOS / Linux mode | Windows | Rationale |
|---|---|---|---|
| `<app-data>/` (the directory) | `0700` | Owner-only ACL | The directory may hold secret-bearing files; restrict listing to the owner. |
| `ollama_llm_bench.db`, `-wal`, `-shm` | `0600` | Owner-only ACL | The provider table persists only api-key **environment-variable names**, never literal keys (D-R-18); the database is owner-read/write only as defence in depth. |
| `logs/app/app.log` and its backups | `0600` | Owner-only ACL | Logs are redacted, but treated as owner-only as defence in depth. |
| `logs/run/*.log` | `0600` | Owner-only ACL | Same as the application log. |
| `backups/settings_*.yaml` | `0600` | Owner-only ACL | A settings snapshot carries provider config including the api-key **environment-variable name** (never a literal key — D-R-18); owner-only ACL applies as defence in depth. |
| `temp/*` | `0600` | Owner-only ACL | May briefly hold secret-bearing content mid-write. |
| `exports/*` | Process umask default | Default ACL | Export files are user-owned artefacts the user may share; the user controls their permissions. |

Rules:

- Files that may contain a secret are created owner-only and stay owner-only. They are never made group- or world-readable.
- The application sets the restrictive mode at the moment of file creation, not as a follow-up step, so there is no window in which the file is readable by others.
- On Windows the equivalent is an access-control list granting access to the current user account only; the application applies it on creation.
- Export files are the one exception: the user explicitly produces them to share, so they take the default umask.

## 10. First-launch creation

On first launch the application data directory and its subtree do not yet exist. Creation rules:

- `<app-data>/` and every subfolder (`logs/app/`, `logs/run/`, `exports/`, `backups/`, `temp/`) are created with a recursive, idempotent make-directory operation, so a partially existing tree is completed rather than rejected.
- The directory is created with mode `0700` (owner-only) on macOS and Linux, and an owner-only ACL on Windows, before any file is written into it.
- If creation fails because the parent path is not writable, the application shows a clear modal naming the path and the reason and does not continue — it cannot run without its data directory.
- The SQLite database file is created and its schema initialised on first open (see `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`).
- A subfolder that is missing on a later launch (for example, deleted by the user) is recreated transparently.

## 11. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-FL-1 | First-launch directory creation | Recursive idempotent mkdir; permission failure shows a clear modal and aborts startup. |
| EC-FL-2 | macOS app launched from a quarantined download | The data directory still resolves under `~/Library/Application Support/`. |
| EC-FL-3 | Windows path longer than 260 characters | Long-path handling is applied internally so deep `<app-data>` paths still work. |
| EC-FL-4 | `XDG_DATA_HOME` unset or empty on Linux | Falls back to `~/.local/share/OllamaLLMBench/`. |
| EC-FL-7 | `-wal` / `-shm` files left after an unclean shutdown | Normal; SQLite recovers them on the next open; never deleted by hand. |
| EC-FL-8 | A subfolder was deleted by the user between sessions | Recreated transparently at the next startup. |
| EC-FL-9 | Disk full while writing a log or export | The atomic temp-then-rename pattern leaves no partial file; an error is surfaced. |
| EC-FL-10 | More than 200 run logs accumulate | Startup cleanup prunes the oldest down to 200. |
