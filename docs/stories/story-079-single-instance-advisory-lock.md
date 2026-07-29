---
id: STORY-079
title: Add the single-instance advisory lock with stale-owner recovery
status: done
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

- [x] Every acceptance criterion has a passing test that names STORY-079.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/infra/`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

Implementation: `backend/infra/_internal/instance_lock.py` — the acquire algorithm sits behind the
`LockPrimitives` Protocol seam so the stale-reclaim branch (which depends on kernel lock-visibility
lag) is deterministically testable via `LaggingLockPrimitives` in the colocated test suite.

The `_HeldInstanceLock.release()` method wraps the unlock call in a `try`/`finally`, with a
`contextlib.suppress(OSError)` inside each of the `try` and `finally` bodies (one around the
unlock, one around the descriptor close).
The `finally` guarantees the close always runs, even if the unlock call raises something other
than `OSError`; the `suppress(OSError)` around each call absorbs the specific failure each one
can legitimately raise on its own.
This matters because `release()` promises its caller it never raises an `OSError` from the unlock
or the close: the application's shutdown sequence and the test-cleanup fixture both call it
unconditionally during teardown and must not have that teardown itself throw over the specific
failure mode `fcntl.flock`/`os.close` can produce.

This helper is POSIX-only: `default_primitives()` returns `PosixLockPrimitives`, built on
`fcntl.flock` for the exclusive advisory lock and `os.kill(pid, 0)` for the liveness check.
On a non-POSIX host (`os.name != "posix"`), `default_primitives()` raises a typed
`ConfigurationError` naming the platform, so the application aborts startup rather than running
unprotected with no single-instance guarantee.
Windows support is a follow-up story that adds an `msvcrt`-based `LockPrimitives` implementation;
the `LockPrimitives` Protocol seam is designed so that is a drop-in replacement for
`PosixLockPrimitives`, with no change needed to `acquire_instance_lock_impl` or `api.py`. The
seam earns its keep here: it also captures `is_pid_alive`, which a Windows implementer *must*
reimplement rather than reuse, because `os.kill(pid, 0)` on Windows terminates the target process
instead of merely probing it.
The existing tests are the one part of this claim that does not hold as-is: all six test fakes in
`test_instance_lock.py` (`_UnlockFailsPrimitives`, `LaggingLockPrimitives`, and the rest) subclass
the concrete `PosixLockPrimitives`, whose `try_lock_exclusive`/`unlock` methods `import fcntl` at
call time, so on Windows constructing any of those fakes raises `ImportError` before the AC-3
proof can even run. A Windows follow-up needs a platform-neutral fake base the POSIX and
`msvcrt` fakes both subclass, not a reuse of these fakes as written.

Releasing the lock deliberately does not delete `<app-data>/.instance.lock`.
Deleting the file on release would let a concurrent acquirer's `os.open` create a new inode at
the same path and lock that new inode instead of the one the releasing process held; both
processes could then believe they hold the lock and run at the same time, which is exactly the
failure this story exists to prevent.
Leaving the file in place is safe because the lock's identity is the `flock`, not the file's
presence — a subsequent launch reopens the same path and takes the lock cleanly whether or not a
stale, unlocked file is already sitting there.

A related hazard was considered and deliberately left unhandled: the release path never deletes
the lock file (above) because deleting races a concurrent acquirer into locking a different
inode. The acquire path has the mirror hazard: if something *outside* the application deletes
`.instance.lock` while a holder is still live, the next `os.open(..., O_CREAT)` creates a fresh
inode and both instances would then run at once. The standard defence is to compare
`os.fstat(fd).st_ino`/`st_dev` against `os.stat(lock_file)` right after taking the lock and retry
once on mismatch. This is not implemented because the application itself never deletes the file
— it would only defend against an outside actor deleting it, which is out of scope for this
story.

`just trace-check`'s eight `EC-M-1` through `EC-M-8` failures ("named by a story but has no
proving test") are pre-existing Phase-11 debt from the still-unimplemented STORY-076, STORY-078,
STORY-080, and STORY-081.
They were present before this story started and are unaffected by it; verified by running
`just trace-check` after this story's changes and confirming the failure count stayed at exactly
eight, every failing id is `EC-M-*`, and no `STORY-079` line appears among them.
