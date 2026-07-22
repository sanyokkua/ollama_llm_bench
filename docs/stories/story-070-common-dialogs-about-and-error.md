---
id: STORY-070
title: Build the About dialog and the generic Error dialog
status: done
spec_clauses:
  - 07_Common_Dialogs/about_dialog.md#4-identity-block
  - 07_Common_Dialogs/about_dialog.md#5-paths-block
  - 07_Common_Dialogs/about_dialog.md#6-folder-actions
  - 07_Common_Dialogs/about_dialog.md#11-edge-cases
  - 07_Common_Dialogs/error_dialog.md#5-three-error-patterns
  - 07_Common_Dialogs/error_dialog.md#6-content-composition
  - 07_Common_Dialogs/error_dialog.md#9-button-behaviour
  - 07_Common_Dialogs/error_dialog.md#12-edge-cases
  - 08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/common_dialogs/
  - adapters/file_system_actions/
acceptance_criteria:
  - STORY-070-AC-1
  - STORY-070-AC-2
  - STORY-070-AC-3
  - STORY-070-AC-4
  - STORY-070-AC-5
  - STORY-070-AC-6
  - STORY-070-AC-7
edge_cases:
  - EC-AB-2
  - EC-AB-3
  - EC-AB-7
  - EC-ERR-6
depends_on:
  - STORY-049
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: M
---

# STORY-070 — Build the About dialog and the generic Error dialog

## Goal

Deliver the two remaining shared modal dialogs that have no natural first-consumer widget: the
About dialog (application identity, GitHub link, and the application-data-folder row with
Copy-path and Open-folder actions) and the generic Error dialog (the single blocking error modal
raised by the Notification Service, rendering a caller-supplied payload in one of three fixed
patterns — recoverable, action-available, fatal).

## In scope

- `ui/common_dialogs/` About dialog factory: the identity block (name, optional build version,
  description, `Project on GitHub` link), the application-data-folder path row, and the
  Copy-path / Open-folder / open-repository actions, each staying open after use.
- `ui/common_dialogs/` Error dialog factory: the title/message/detail rendering, the three
  patterns with their footer button sets, the Copy Details action (present only when `detail` is
  supplied), the recovery-action pattern, and the fatal pattern's Quit-only, no-Escape behaviour.

## Out of scope

- The About and Error dialog trigger wiring (the Main Window About menu action, the Notification
  Service dispatch) — the dialogs are pure factories; the callers are owned elsewhere.
- The Notification Service that raises the Error dialog and serialises concurrent blocking errors
  — consumed as a Protocol; this story renders the caller payload.
- The Run Summary, Resume Summary, Retry Selection, Rename Run, and Generate Analysis dialogs —
  owned by STORY-055, STORY-056, STORY-057, and STORY-065.
- Wiring the dialog factories in `compose.py` — this story **must not touch** `compose.py` (Phase
  11 owns it).

## Spec inputs

- `07_Common_Dialogs/about_dialog.md#4-identity-block` — the application name, the optional
  build-version omission rule, the description, and the repository link.
- `07_Common_Dialogs/about_dialog.md#5-paths-block` — the single application-data-folder row with
  its resolved path and truncation-with-tooltip rule.
- `07_Common_Dialogs/about_dialog.md#6-folder-actions` — the Copy-path (untruncated) and
  Open-folder actions that keep the dialog open.
- `07_Common_Dialogs/error_dialog.md#5-three-error-patterns` — the recoverable, action-available,
  and fatal patterns and their footer button sets.
- `07_Common_Dialogs/error_dialog.md#6-content-composition` — the verbatim rendering of the
  caller's title/message/detail with no derivation.
- `07_Common_Dialogs/error_dialog.md#9-button-behaviour` — the per-pattern button behaviours,
  including the fatal pattern's Quit-only, no-Close, no-Escape rules.
- `08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling` — the dialogs repaint correctly
  on a runtime theme change.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only; the error glyph tint comes from the `error.base` role.

## Design constraints

- Both dialogs are pure presentation and hold no domain logic; the invoking caller supplies the
  content, and the Error dialog performs no redaction (it renders the already-redacted payload).
- The Error dialog never changes pattern after it opens; the fatal pattern has no Close button and
  ignores Escape.
- The About dialog persists nothing; the Copy-path action copies the full, untruncated path.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-070-AC-1

Given the About dialog is built without an injected build-version string, when it renders, then
the version line is omitted entirely and the name, description, repository link, and path row are
unaffected.

### STORY-070-AC-2

Given the About dialog, when the user clicks Copy path, then the full untruncated
application-data-folder path is written to the clipboard and the dialog stays open; and when the
user clicks Open folder, then the folder is revealed via the OS adapter and the dialog stays
open.

### STORY-070-AC-3

For each error pattern, the Error dialog renders the specified footer button set:

| Pattern          | Footer buttons                                                 |
| ---------------- | -------------------------------------------------------------- |
| recoverable      | Copy Details (if detail), Close (primary)                      |
| action available | Copy Details (if detail), recovery action, Close (primary)     |
| fatal            | Copy Details (if detail), Quit (destructive primary); no Close |

### STORY-070-AC-4

Given the caller supplies no `detail`, when the Error dialog renders, then the detail block and
the Copy Details button are both absent.

### STORY-070-AC-5

Given the fatal pattern, when the dialog is shown, then Escape does not dismiss it and there is no
close (X) glyph; the only exit is the Quit button, which runs the clean-shutdown sequence.

### STORY-070-AC-6

For each of this story's dialog factory functions, constructing it with fakes for its declared
OS/clipboard/file-system collaborators and mounting it under `qtbot`, then showing it
(`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), raises no exception,
reports `isVisible()`, and captures no `error`/`critical`-level `structlog` record — verified by
wrapping construction+show in `structlog.testing.capture_logs()` and asserting no captured
entry's `log_level` is in `{"error", "critical"}`:

| Factory function    | Fake collaborators                                          |
| ------------------- | ----------------------------------------------------------- |
| `make_about_dialog` | fake `Clipboard`, fake `FileSystemActions`, fake `EventBus` |
| `make_error_dialog` | fake `Clipboard`, fake `EventBus`                           |

### STORY-070-AC-7

Given the About dialog, when Copy path succeeds, then it emits the confirmation toast `Path copied.`; given the Error dialog, when Copy Details succeeds, then it emits the confirmation
toast `Details copied.`. Given any of Copy path, Open folder, the `Project on GitHub` link, or
Copy Details raises `OsAdapterError`, then the dialog emits the matching failure toast — `Could not copy the path.` (EC-AB-3), `Could not open the folder.` (EC-AB-2), `Could not open the repository link.` (EC-AB-7), or `Could not copy to the clipboard.` (EC-ERR-6) — and the dialog
stays open and fully usable in every case.

## Test plan

- STORY-070-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_about_dialog.py`,
  `test_version_line_omitted_when_absent`.
- STORY-070-AC-2 — unit (`pytest-qt`, fake clipboard/file-system actions), same file,
  `test_copy_path_and_open_folder_keep_dialog_open`.
- STORY-070-AC-3 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`,
  `test_footer_buttons_per_pattern`.
- STORY-070-AC-4 — unit (`pytest-qt`), same file, `test_no_detail_hides_detail_block`.
- STORY-070-AC-5 — unit (`pytest-qt`), same file, `test_fatal_pattern_quit_only_no_escape`.
- STORY-070-AC-6 — unit (`pytest-qt`, fake `Clipboard`/`FileSystemActions`/`EventBus`),
  colocated `src/ollama_llm_bench/ui/common_dialogs/tests/test_about_dialog.py`,
  `test_about_dialog_constructs_and_shows_with_no_error_logs`, and colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`,
  `test_error_dialog_constructs_and_shows_with_no_error_logs`.
- STORY-070-AC-7 — unit (`pytest-qt`, fake `Clipboard`/`FileSystemActions`/`EventBus`,
  asserting on the fake `EventBus`'s captured `GlobalMessageEvent`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_about_dialog.py`:
  `test_copy_path_success_emits_confirmation_toast`,
  `test_open_folder_and_repository_link_success_emit_no_toast` (table-driven),
  `test_action_failure_emits_failure_toast_and_keeps_dialog_open` (table-driven, EC-AB-2/3/7);
  and colocated `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`:
  `test_copy_details_success_emits_confirmation_toast`,
  `test_copy_details_failure_emits_toast_and_keeps_dialog_open` (EC-ERR-6).

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-070.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the About dialog state
  machine and the three Error dialog patterns of `07_Common_Dialogs/error_dialog.md`.
- [x] An architecture test confirms both dialog factories hold no domain logic, that the Error
  dialog performs no redaction, and that the module references no `setStyleSheet`, embeds no
  colour literal, and imports no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/common_dialogs/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-070.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes

**AC-7 / toast work (second pass).** An independent spec-conformance review of this story's
first implementation pass found that `about_dialog.md` §6.1/§8 and `error_dialog.md` §9
require confirmation/failure toasts for Copy path, Open folder, the `Project on GitHub` link,
and Copy Details (EC-AB-2, EC-AB-3, EC-AB-7, EC-ERR-6) — behaviour the first pass left
unreachable because neither dialog held an `EventBus` collaborator or wrapped its OS-adapter
calls in `try`/`except OsAdapterError`. A second pass added `event_bus: EventBus` to
`AboutDialogCollaborators` and to `make_error_dialog`'s parameter list, wrapped every
clipboard/file-manager/browser call, and emits the spec's exact toast text (STORY-070-AC-7).
This corrects the Design constraints section's earlier "The About dialog ... emits no event"
line, which was accurate only for the first pass — the dialog now emits `GlobalMessageEvent`
for its folder-action toasts. The `adapters/file_system_actions/` module entry was also added
to this story's front-matter `modules:` list: the first pass's `open_url` Protocol addition to
`FileSystemActions` was never declared there, a traceability gap this pass closes.

**EC-AB-2/EC-AB-3/EC-AB-7/EC-ERR-6 and `edge_cases:`.** These four ids are dialog-local edge
cases from `about_dialog.md` §11 and `error_dialog.md` §12, not entries in the centrally
governed `08-I_edge_cases.md` catalog — `scripts/_traceability_lib.py`'s `EDGE_CASE_CATALOGS`
list (the fixed set of documents `load_all_catalog_ids()` scans) does not include either
`about_dialog.md` or `error_dialog.md`. `validate_traceability.py`'s `check_edge_cases_covered`
only iterates catalogued ids when checking for missing-test coverage, so a dialog-local id
cited in a story's `edge_cases:` is never required to prove a test there — but `trace.py`'s
`_build_edge_cases_map` builds a `traceability.yaml` entry for **every** `EC-` id any story
cites, catalogued or not, keyed off the format regex alone (`EC-[A-Z]+-\d+[a-f]?`). Verified by
running `just trace` after adding this story's `edge_cases:` block: it generates cleanly with
`EC-AB-2`, `EC-AB-3`, `EC-AB-7`, and `EC-ERR-6` entries in the `edge_cases:` map, each listing
STORY-070 and (once the tester agent adds AC-7's tests) that AC's proving tests. The tooling
accepts a dialog-local id once cited by a story; it is not rejected, so the `edge_cases:`
front-matter block is kept.
