---
id: STORY-047
title: Provide the Qt notification surface for status-bar toasts and modal error dialogs
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#20-notification-service
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#83-globalmessageevent--_global_message
modules:
  - adapters/notification_service/
acceptance_criteria:
  - STORY-047-AC-1
  - STORY-047-AC-2
  - STORY-047-AC-3
depends_on: []
owner: coder
estimate: M
---

# STORY-047 — Provide the Qt notification surface for status-bar toasts and modal error dialogs

## Goal

Provide the single sanctioned surface for a controller to raise a user-visible message: a
transient status-bar toast for info/warning, and either a toast or a modal dialog for errors.
UI primitives never throw to the user; they call this service instead. The service is
synchronous, called on the main thread, and never raises.

## In scope

- The `NotificationService` Protocol implementation and its `make_notification_service` factory
  over a `QStatusBar` (toasts) and `QMessageBox` (modal error dialog).
- `show_info(text, duration_ms=5000)` and `show_warning(text, duration_ms=5000)` — transient
  toasts with the given dwell time.
- `show_error(text, blocking=False)` — a toast when `blocking` is `False`, a modal dialog when
  `blocking` is `True`.

## Out of scope

- Subscribing to the `_global_message` event and calling this service — the Main Window
  status-bar wiring subscribes to that event; this story provides the surface it drives.
- Redaction of message text — the emitter redacts before emitting `_global_message`; this
  service renders the already-redacted text.
- The event bus Qt delivery — owned by `adapters/qt_event_bus/` (STORY-040).

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#20-notification-service` — the exact
  `NotificationService` surface (`show_info`, `show_warning`, `show_error`), the toast-vs-modal
  rule for `show_error`'s `blocking` flag, the synchronous-on-main-thread contract, and the
  never-raises guarantee.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#83-globalmessageevent--_global_message` — the
  `GlobalMessageEvent(text, severity, duration_ms)` payload the status-bar toast renders, the
  severity values (`info`/`success`/`warning`/`error`), and the already-redacted-text rule.

## Design constraints

- `adapters/notification_service/` imports PySide6 only (`01_MODULE_INVENTORY.md` §5); it holds
  no backend Protocol. No `asyncio`.
- Every method is synchronous, called on the main thread, and never raises to the caller.
- `show_error(blocking=True)` shows a modal `QMessageBox`; `blocking=False` shows a toast.
- The service assumes text is already redacted; it applies no redaction of its own.

## Acceptance criteria

### STORY-047-AC-1

Given the service, when `show_info(text)` or `show_warning(text)` is called, then a transient
toast carrying that text is shown on the status bar and the call returns without raising
(table-driven over info and warning).

### STORY-047-AC-2

Given the service, when `show_error(text, blocking=True)` is called, then a modal error dialog
carrying that text is shown; when `show_error(text, blocking=False)` is called, then a transient
error toast is shown instead (the `blocking` flag selects modal vs. toast).

### STORY-047-AC-3

Given the service, when any of `show_info`, `show_warning`, or `show_error` is called, then the
call is synchronous and returns without raising to the caller (the never-raises contract holds).

## Test plan

- STORY-047-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/adapters/notification_service/tests/test_notification_service.py`,
  `test_info_and_warning_show_transient_toast`.
- STORY-047-AC-2 — unit (`pytest-qt`), same file,
  `test_show_error_blocking_flag_selects_modal_or_toast`.
- STORY-047-AC-3 — unit (`pytest-qt`), same file,
  `test_all_methods_are_synchronous_and_never_raise`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-047.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/notification_service/`.
- [ ] An architecture test confirms the module imports no backend Protocol and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
