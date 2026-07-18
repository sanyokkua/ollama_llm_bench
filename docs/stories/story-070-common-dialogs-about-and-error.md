---
id: STORY-070
title: Build the About dialog and the generic Error dialog
status: ready
spec_clauses:
  - 07_Common_Dialogs/about_dialog.md#4-identity-block
  - 07_Common_Dialogs/about_dialog.md#5-paths-block
  - 07_Common_Dialogs/about_dialog.md#6-folder-actions
  - 07_Common_Dialogs/error_dialog.md#5-three-error-patterns
  - 07_Common_Dialogs/error_dialog.md#6-content-composition
  - 07_Common_Dialogs/error_dialog.md#9-button-behaviour
  - 08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-070-AC-1
  - STORY-070-AC-2
  - STORY-070-AC-3
  - STORY-070-AC-4
  - STORY-070-AC-5
  - STORY-070-AC-6
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
- The About dialog persists nothing and emits no event; the Copy-path action copies the full,
  untruncated path.
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

| Factory function    | Fake collaborators                           |
| ------------------- | -------------------------------------------- |
| `make_about_dialog` | fake `Clipboard`, fake `FileSystemActions`   |
| `make_error_dialog` | none (pure presentation of a caller payload) |

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
- STORY-070-AC-6 — unit (`pytest-qt`, fake `Clipboard`/`FileSystemActions`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_about_dialog.py`,
  `test_about_dialog_constructs_and_shows_with_no_error_logs`, and colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`,
  `test_error_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-070.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the About dialog state
  machine and the three Error dialog patterns of `07_Common_Dialogs/error_dialog.md`.
- [ ] An architecture test confirms both dialog factories hold no domain logic, that the Error
  dialog performs no redaction, and that the module references no `setStyleSheet`, embeds no
  colour literal, and imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/common_dialogs/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-070.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
