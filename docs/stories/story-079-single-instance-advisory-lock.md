---
id: STORY-079
title: Add the single-instance advisory lock with stale-owner recovery
status: ready
spec_clauses:
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#5-file-lock-policy
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#6-multi-instance-handling
modules:
  - backend/infra/
acceptance_criteria:
  - STORY-079-AC-1
  - STORY-079-AC-2
  - STORY-079-AC-3
depends_on: []
adrs:
  - ADR-0010
owner: coder
estimate: S
---

# STORY-079 — Add the single-instance advisory lock with stale-owner recovery

## Goal

Stop two copies of the application from writing the same data directory at once. On startup the
application takes an exclusive advisory lock on a dedicated lock file inside the data directory and
holds it for the whole process lifetime. A second copy pointed at the same directory finds the lock
held and refuses to run. A lock left behind by a crashed process — whose owning process is no longer
alive — is treated as stale and reclaimed, so a crash never permanently blocks the next launch.

## In scope

- A new Qt-free helper in `backend/infra/` that acquires an exclusive advisory lock on
  `<app-data>/.instance.lock`, records the owning PID and a start timestamp in it, and returns a
  release handle held for the process lifetime.
- The stale-owner check: when the lock appears held, the recorded PID is checked for liveness; if no
  live process owns it, the lock is treated as stale and re-acquired.
- The refuse-to-run result: an acquisition that fails because a live process holds the lock returns a
  clear "already running" outcome to its caller without opening the database or mutating the data
  directory.

## Out of scope

- Rendering the "already running" / permission modals and exiting — the composition root shows the
  modal on the live `QApplication` and exits (STORY-076/STORY-078); this backend helper only reports
  the acquire/refuse outcome (ADR-0010).
- Asking the first instance to raise its window — a best-effort convenience, not part of this helper's
  binding behaviour.
- SQLite's own per-connection file locking and the `busy_timeout` pragma — independent of this
  process-level lock and owned by the persistence layer.
- The shutdown-time lock release ordering — owned by STORY-080's shutdown handle.

## Spec inputs

- `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#5-file-lock-policy` — the lock file
  (`<app-data>/.instance.lock`) records the owning PID and a start timestamp, is held for the whole
  process lifetime, and a lock held by a dead process is reclaimed after a PID-liveness check rather
  than refusing to start; the data directory must be on a local filesystem.
- `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#6-multi-instance-handling` — the application is
  single-instance per data directory: the first instance acquires the lock, a later instance on the
  same directory does not open the database, does not start its pipeline, and does not mutate any file
  in the data directory; two instances on different directories both run normally.

## Design constraints

- `backend/infra/` is Qt-free; the helper renders no dialog and imports no PySide6.
- The lock is an OS-level advisory lock held for the process lifetime and dropped by the OS on crash;
  the helper adds the PID-liveness reclaim on top so a stale lock is recoverable.
- The helper opens no database and mutates nothing in the data directory on a failed acquisition.

## Acceptance criteria

### STORY-079-AC-1

Given a data directory with no live lock owner,
when the helper acquires the single-instance lock,
then acquisition succeeds and `<app-data>/.instance.lock` records the owning PID and a start
timestamp.

### STORY-079-AC-2

Given the single-instance lock is held by a live process,
when a second acquisition is attempted against the same data directory,
then acquisition fails with an "already running" outcome and no database is opened and no file in the
data directory is mutated.

### STORY-079-AC-3

Given a lock file whose recorded PID is not a live process,
when the helper attempts acquisition,
then the stale lock is reclaimed and acquisition succeeds.

## Test plan

- STORY-079-AC-1 — unit, colocated `src/ollama_llm_bench/backend/infra/tests/test_instance_lock.py`,
  `test_first_acquisition_succeeds_and_records_pid_and_timestamp`.
- STORY-079-AC-2 — unit, same file, `test_second_acquisition_against_live_owner_refuses_and_touches_nothing`.
- STORY-079-AC-3 — unit, same file, `test_stale_lock_from_dead_pid_is_reclaimed`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-079.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/infra/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
