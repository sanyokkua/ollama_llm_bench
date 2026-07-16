---
id: STORY-048
title: Provide the native picker, clipboard, and file-manager OS integration adapters
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#21-os-adapter-protocols
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#21a-nativepickers
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#21b-clipboard
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#21c-filesystemactions
modules:
  - adapters/native_pickers/
  - adapters/clipboard/
  - adapters/file_system_actions/
acceptance_criteria:
  - STORY-048-AC-1
  - STORY-048-AC-2
  - STORY-048-AC-3
  - STORY-048-AC-4
  - STORY-048-AC-5
depends_on: []
owner: coder
estimate: M
---

# STORY-048 — Provide the native picker, clipboard, and file-manager OS integration adapters

## Goal

Provide the three focused OS-integration adapters that give the UI a platform-agnostic surface
for native save/open dialogs, clipboard copy, and revealing a path in the OS file manager. Each
hides its platform-specific branches behind a Protocol so the UI is platform-neutral and every
method is substitutable in tests. Picker cancellation is a `None`/empty result, and a genuine
integration failure surfaces as `OsAdapterError`.

## In scope

- `adapters/native_pickers/` — the `NativePickers` Protocol implementation and
  `make_native_pickers`: `save_file`, `open_file`, `open_folder` over the contract-local
  `SavePickerOptions`, `FilePickerOptions`, `FolderPickerOptions` options structs.
- `adapters/clipboard/` — the `Clipboard` Protocol implementation and `make_clipboard`:
  `copy_text`.
- `adapters/file_system_actions/` — the `FileSystemActions` Protocol implementation and
  `make_file_system_actions`: `open_in_file_manager`.
- Per-OS branches isolated in each module's `_internal/`, tested with platform-aware fakes.

## Out of scope

- The UI surfaces that invoke these adapters (Result export footer, Task Editor pickers, Settings
  import/export) — later UI phases.
- The `OsAdapterError` error class definition — owned by the error-taxonomy story (STORY-002);
  these adapters translate integration failures into it.
- Redaction of copied text — the local-app threat model does not redact user-owned content on
  the clipboard (`08-E` §22); `copy_text` places the text unchanged.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#21-os-adapter-protocols` — the three sibling OS
  adapters, the synchronous-on-main-thread rule, the `OsAdapterError`-on-integration-failure
  rule, the picker-cancellation-is-`None`/empty rule, and the substitutability requirement.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#21a-nativepickers` — the `NativePickers` surface
  (`save_file` → path or `None`; `open_file` → paths tuple, empty on cancel; `open_folder` →
  folder or `None`) and the three options structs.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#21b-clipboard` — `Clipboard.copy_text` and its
  `OsAdapterError`-when-unavailable rule.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#21c-filesystemactions` —
  `FileSystemActions.open_in_file_manager` and its `OsAdapterError` when the path does not exist
  or the manager cannot launch.

## Design constraints

- `adapters/native_pickers/` and `adapters/clipboard/` import PySide6;
  `adapters/file_system_actions/` imports PySide6. No `asyncio`. `01_MODULE_INVENTORY.md` §5
  lists `platformdirs` as a notable dependency of `file_system_actions`, but neither
  `08-E` §21c nor `08-K` §5 assigns it a concrete role in the reveal action; the implementation
  uses a `sys.platform`-based classifier instead (mirroring `backend/platform`'s own
  classifier) and does not import `platformdirs` — reviewed and accepted as a minor
  implementation judgment call, not a spec gap.
- Per-OS branches live in each module's `_internal/`; every method is substitutable behind its
  Protocol for platform-aware fakes.
- Picker cancellation returns `None` (save/folder) or an empty tuple (open-file) — never an
  exception; only a dialog-subsystem/integration failure raises `OsAdapterError`.
- Each of the three adapters owns exactly one Protocol; there is no umbrella Protocol.

## Acceptance criteria

### STORY-048-AC-1

For each `NativePickers` method, given the user cancels the dialog, then the method returns the
cancellation result for that method — `None` for `save_file` and `open_folder`, an empty tuple
for `open_file` — and does not raise (table-driven over the three pickers).

### STORY-048-AC-2

For each `NativePickers` method, given the user selects a path, then the method returns the
chosen path(s) — the chosen path for `save_file`/`open_folder`, the chosen paths tuple for
`open_file` (table-driven over the three pickers).

### STORY-048-AC-3

Given the clipboard is available, when `Clipboard.copy_text(text)` is called, then exactly that
text is placed on the system clipboard.

### STORY-048-AC-4

Given an existing path, when `FileSystemActions.open_in_file_manager(path)` is called, then the
OS file-manager reveal action is invoked for that path and the call returns without raising.

### STORY-048-AC-5

For each OS adapter, given the underlying platform operation fails (dialog subsystem
unavailable, clipboard unavailable, or a nonexistent/​unlaunchable path), then the method raises
`OsAdapterError` and never leaks the raw platform exception (table-driven over the three
adapters).

## Test plan

- STORY-048-AC-1 — table-driven unit (platform-aware fake), colocated
  `src/ollama_llm_bench/adapters/native_pickers/tests/test_native_pickers.py`,
  `test_cancel_returns_none_or_empty_per_picker`.
- STORY-048-AC-2 — table-driven unit, same file,
  `test_selection_returns_chosen_paths_per_picker`.
- STORY-048-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/adapters/clipboard/tests/test_clipboard.py`,
  `test_copy_text_places_exact_text_on_clipboard`.
- STORY-048-AC-4 — unit (platform-aware fake), colocated
  `src/ollama_llm_bench/adapters/file_system_actions/tests/test_file_system_actions.py`,
  `test_open_in_file_manager_invokes_reveal_for_existing_path`.
- STORY-048-AC-5 — table-driven unit (each adapter's failure path), across the three adapters'
  colocated test files, `test_integration_failure_raises_os_adapter_error`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-048.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/native_pickers/`,
  `adapters/clipboard/`, and `adapters/file_system_actions/`.
- [x] An architecture test confirms each module isolates per-OS branches in `_internal/` and
  imports no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test (STORY-048's
  five ACs and the tests that prove them; `just trace-check`'s only remaining failures are the
  three pre-existing, unrelated backlog gaps EC-PERSIST-6/EC-PROV-1a/EC-RUN-1a).
- [x] The module inventory is unchanged.
