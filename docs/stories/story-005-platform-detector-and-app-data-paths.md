---
id: STORY-005
title: Detect the host OS and resolve OS-appropriate application-data paths
status: done
spec_clauses:
  - 08_Cross_Cutting/08-K_platform_specifics.md#2-the-platform-detector-and-the-platform-profile
  - 08_Cross_Cutting/08-K_platform_specifics.md#3-application-data-paths-per-operating-system
  - 08_Cross_Cutting/08-K_platform_specifics.md#13-platform-specific-edge-cases
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#1-application-data-directory-per-operating-system
modules:
  - backend/platform/
acceptance_criteria:
  - STORY-005-AC-1
  - STORY-005-AC-2
  - STORY-005-AC-3
  - STORY-005-AC-4
edge_cases:
  - EC-PLAT-1
  - EC-PLAT-4
depends_on: []
owner: coder
estimate: S
---

# STORY-005 — Detect the host OS and resolve OS-appropriate application-data paths

## Goal

Give the application one authoritative, cached answer to "what OS is this, and where does
its data live", produced once at launch, so every later module (logging, persistence,
exports, theming, file pickers) reads a single immutable platform profile instead of
re-detecting the host or hand-rolling its own OS branch.

## In scope

- The `PlatformDetector` Protocol and its `make_platform_detector()` factory, classifying the
  host into exactly one of `MACOS` / `WINDOWS` / `LINUX` / `UNKNOWN`.
- The immutable `PlatformProfile` record (a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`) carrying at minimum: `kind`, `os_version`, `app_data_root`, `home_path`,
  `desktop_path`, `path_separator`, `line_ending`, `case_sensitive_fs`,
  `supports_native_dark_mode`, `file_manager_label`.
- The per-OS `app_data_root` resolution rule: `~/Library/Application Support/ OllamaLLMBench/` on macOS; `$XDG_DATA_HOME/OllamaLLMBench/` falling back to
  `~/.local/share/OllamaLLMBench/` on Linux when `XDG_DATA_HOME` is unset or empty;
  `%LOCALAPPDATA%\OllamaLLMBench\` on Windows.
- The `UNKNOWN`-classification fallback: when the host cannot be classified, `app_data_root`
  and all other OS-dependent fields resolve using Linux conventions.
- Recursive, idempotent creation of `<app-data>` (mode `0700` / owner-only ACL) as a
  operation this module exposes for its caller to invoke at first launch, raising a typed
  error naming the path on a permission failure (the caller — a later lifecycle story —
  decides how to present that failure to the user).

## Out of scope

- The full `<app-data>` subtree (`logs/`, `exports/`, `backups/`, `temp/`) and its rotation/
  cleanup policies — owned by `backend/infra/` (STORY-004) and later persistence stories,
  which consume this module's `app_data_root` rather than resolving it themselves.
- The OS adapter's file-manager "reveal" action, native file pickers, theme live-reapply on
  host signal change, and font-chain selection — later `adapters/*` and `ui/theme/` stories
  that consume `PlatformProfile.kind` / `file_manager_label` / `supports_native_dark_mode`,
  not implemented here.
- The startup sequencing (when exactly the detector runs relative to other launch steps) —
  owned by `08-M_app_lifecycle.md` and the composition root, a later phase.
- Windows long-path (`\\?\`) handling and other consumers of the profile's fields — this
  story only produces the profile; consumers apply it.

## Spec inputs

- `08_Cross_Cutting/08-K_platform_specifics.md#2-the-platform-detector-and-the-platform-profile`
  — the four-kind classification, the "runs once at launch, cached, immutable" contract, and
  the exact field list of the platform profile this story must produce.
- `08_Cross_Cutting/08-K_platform_specifics.md#3-application-data-paths-per-operating-system`
  — the exact per-OS `<app-data>` path table and the `XDG_DATA_HOME` fallback rule.
- `08_Cross_Cutting/08-K_platform_specifics.md#13-platform-specific-edge-cases` — `EC-K1`
  (folder creation, permission failure aborts launch with an explanatory dialog naming the
  path), `EC-K4` (`XDG_DATA_HOME` unset/empty fallback), and `EC-K7` (undetectable host falls
  back to Linux conventions) as the concrete edge behaviours this module's public API must
  support its caller in implementing.
- `10_Domain_and_Data/07_FILE_LAYOUT.md#1-application-data-directory-per-operating-system` —
  the corroborating domain-data-authoritative statement of the same per-OS path table and the
  rule that the internal subtree is identical across platforms (only the separator differs).

## Design constraints

- `backend/platform/` is Qt-free and imports nothing project-internal beyond
  `backend/domain/` (for shared constrained types) and the standard library
  (`01_MODULE_INVENTORY.md` §4.1). No `ui` or `adapters` imports.
- `PlatformDetector` is a `typing.Protocol`; the concrete OS-probe implementation lives in
  `_internal/` and is faked in tests via a constructor that accepts an injectable
  environment/`sys.platform` source, so tests can exercise every branch without actually
  running on each OS.
- `PlatformProfile` is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`, produced once
  and never mutated; a later caller that needs an OS-specific value reads it from the
  profile, never re-detects.
- No secret-bearing value is ever placed on the profile; `app_data_root` and `home_path` are
  ordinary filesystem paths, not credentials.
- The directory-creation operation this module exposes raises a typed application error
  (from STORY-002's taxonomy — a `UserError`/`ConfigurationError`-class failure, not a
  `ProgrammerError`) on a permission failure; it never silently continues with a
  non-writable path.

## Acceptance criteria

### STORY-005-AC-1

Given a faked host identity for each of macOS, Windows, and Linux, `make_platform_detector`
classifies `kind` correctly and resolves `app_data_root` to exactly the path documented in
the per-OS table (`~/Library/Application Support/OllamaLLMBench/`;
`%LOCALAPPDATA%\OllamaLLMBench\`; `$XDG_DATA_HOME/OllamaLLMBench/` or its fallback).

### STORY-005-AC-2

Given a faked Linux host with `XDG_DATA_HOME` unset or set to an empty string,
`app_data_root` resolves to `~/.local/share/OllamaLLMBench/` (EC-PLAT-1's precondition — a
writable path must exist before folder creation is attempted).

### STORY-005-AC-3

Given a host identity the detector cannot classify, `kind` resolves to `UNKNOWN` and every
OS-dependent field (`app_data_root`, `path_separator`, `line_ending`, `file_manager_label`)
resolves using the Linux-convention fallback, with no exception raised during detection
itself.

### STORY-005-AC-4

The directory-creation operation creates `<app-data>` recursively and idempotently (a second
call on an already-existing tree does not raise), and on a simulated permission failure
raises a typed application error whose message names the attempted path (EC-PLAT-1); a path
containing non-ASCII characters is created and resolved without a `UnicodeError` or
mojibake (EC-PLAT-4).

## Test plan

- STORY-005-AC-1 — table-driven unit, colocated
  `src/ollama_llm_bench/backend/platform/tests/test_platform_detector.py`,
  `test_platform_kind_and_app_data_root_per_os`.
- STORY-005-AC-2 — unit, same file, `test_xdg_data_home_unset_or_empty_falls_back`.
- STORY-005-AC-3 — unit, same file, `test_unknown_host_falls_back_to_linux_conventions`.
- STORY-005-AC-4 — unit,
  `src/ollama_llm_bench/backend/platform/tests/test_app_data_creation.py`,
  `test_app_data_dir_creation_is_idempotent_and_raises_named_error_on_permission_failure`;
  EC-PLAT-1 and EC-PLAT-4 covered in the same file via
  `test_app_data_dir_creation_permission_failure_and_non_ascii_path` per
  `06_EDGE_CASE_TO_TEST_MAPPING.md`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-005.
- [x] EC-PLAT-1 and EC-PLAT-4 have passing tests.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/platform/`.
- [x] Backend branch coverage for `backend/platform/` meets the Phase 1 ≥90% gate.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- An independent spec-conformance review (post-implementation) found EC-PLAT-1's spec text
  (`08-I_edge_cases.md#EC-PLAT-1`) actually covers both a permission failure *and* a
  disk-space failure, naming both the path and the reason — the first implementation only
  caught `PermissionError` and hardcoded the message reason. Fixed:
  `create_app_data_dir_impl` now catches `OSError` (a superset including `PermissionError`)
  and surfaces the real `strerror`, with a new test
  (`test_app_data_dir_creation_raises_named_error_on_disk_space_failure`) proving the
  disk-space branch via a monkeypatched `Path.mkdir` raising `OSError(errno.ENOSPC, ...)`.
- The review also flagged the Windows `%LOCALAPPDATA%`-unset fallback
  (`home_path / "AppData" / "Local" / "OllamaLLMBench"`) as not spec-authorized (neither
  08-K §3 nor `07_FILE_LAYOUT.md` §1 documents a fallback for this case, since real Windows
  always sets `LOCALAPPDATA`). Kept as a defensive-only branch (avoids producing a broken
  relative path in a pathological environment) with a one-line comment making the judgment
  call explicit, rather than removing it or inventing further untested behaviour.
- `supports_native_dark_mode` resolves to `True` for `UNKNOWN` per the same
  Linux-convention-fallback rule (EC-K7) applied to every other OS-dependent field in this
  profile — Linux's own row is `True` per §7. This is a judgment call the review flagged as
  worth a human decision; kept as-is for consistency with how every other field's `UNKNOWN`
  fallback is resolved in this module.
- `just trace-check` still fails on three pre-existing, STORY-005-unrelated gaps
  (`EC-PERSIST-6` dangling row; `EC-PROV-1a`/`EC-RUN-1a` uncovered) — the same gaps STORY-003
  already documented as pre-existing at the STORY-002 `done` commit. STORY-005 itself
  resolves the `EC-PLAT-1`/`EC-PLAT-4` gaps STORY-003 flagged as pending on this story, and
  introduces zero new orphan clauses/tests. Likewise `just coverage-layers`'s UI-layer check
  still reports "No data to report" because no `ui/` code exists yet in Phase 1 — also
  pre-existing, not introduced by this story. `backend/platform/`'s own coverage is 97-100%
  per file, comfortably above the ≥90% gate.
