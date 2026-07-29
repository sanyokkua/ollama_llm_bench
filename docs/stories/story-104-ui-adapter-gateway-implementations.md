---
id: STORY-104
title: Give every UI adapter gateway exactly one production implementation
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#23-the-application-context
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#6-ui-modules
modules:
  - ui/main_window/
  - ui/common_dialogs/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-104-AC-1
  - STORY-104-AC-2
edge_cases: []
depends_on:
  - STORY-105
  - STORY-106
  - STORY-107
  - STORY-108
  - STORY-109
  - STORY-110
  - STORY-111
adrs:
  - ADR-0014
owner: coder
estimate: M
---

# STORY-104 — Give every UI adapter gateway exactly one production implementation

## Goal

Close the gap that stops the application from being assembled at all: every widget and dialog reaches
the backend through one per-widget gateway object, and today not one of those gateways has a real
implementation — only test fakes. This is the umbrella story for the sweep that builds them. It
delivers the single cross-cutting guarantee no individual gateway story can own — that every gateway
Protocol the user interface declares is satisfied by exactly one real production object, and that no
user-interface controller is left holding a backend store or service — and depends on the seven
per-gateway child stories that write the implementations.

## In scope

- The application-wide conformance guarantee that each of the seven gateway Protocols named in
  `08-E_interfaces_contracts.md` §7b has exactly one production implementation reachable from the
  adapters layer's public surface, and that a production implementation exists for the four
  Common-Dialogs gateways too.
- Coordinating the seven per-gateway child stories: STORY-105 (Main Window), STORY-106 (New
  Benchmark), STORY-107 (Progress), STORY-108 (Result), STORY-109 (Resume), STORY-110 (Settings),
  STORY-111 (Task Editor).
- Proving that the four Common-Dialogs gateways are satisfied structurally by the sibling gateways
  their method sets are subsets of, with no extra adapter class written for any of them.

## Out of scope

- The per-gateway implementations themselves — each is owned by its own child story listed above.
- The `FileChangeWatcher` implementation the Task Editor needs — owned by STORY-112. It is a
  collaborator Protocol, not one of the seven §7b gateways, and it lands in a different module.
- The `ExportFilenameHelper` bridge declared by `ui/results/` and `ui/resume_benchmark/` — owned by
  STORY-077 per ADR-0010.
- The `RunValidator` Protocol declared locally by `ui/new_benchmark/` — it is a backend service, not
  a gateway, and no story owns it yet; see this story's Design constraints.
- Wiring the gateways into `build_app` and the widget factories — owned by STORY-077, which depends
  on this story.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the adapter is the
  exclusive boundary and exposes exactly one gateway Protocol per widget; each gateway is
  method-only, stdlib and `msgspec` types only, no `psygnal` and no Qt symbol; a gateway is a
  purpose-built facade scoped to the methods its controller actually calls, never a blanket
  re-export of a store (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#23-the-application-context` — the composition root
  reads handles out of its own internal context and constructs each widget with **only** its adapter
  gateway plus the few user-interface services it needs; the context itself is never handed to a
  widget, controller, or adapter (SPEC-075).
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter layer is the
  only layer that holds backend Protocols; a controller calls the gateway and never sees the
  Protocol; every Qt-specific accommodation lives in the adapter.
- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#6-ui-modules` — each user-interface module's
  dependency column lists the backend *capabilities* the adapter wires behind that widget's gateway,
  never Protocols the widget holds (D-R-06 / SPEC-074).

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.

## Acceptance criteria

### STORY-104-AC-1

For every gateway Protocol declared in the user-interface layer's `protocols.py` files, exactly one
production class outside any `testing.py` module satisfies it, and that class is reachable through
the adapters layer's public surface:

| Gateway Protocol      | Declared in                        | Production implementation reachable from the adapters public surface |
| --------------------- | ---------------------------------- | -------------------------------------------------------------------- |
| `MainWindowGateway`   | `ui/main_window/protocols.py`      | yes                                                                  |
| `NewBenchmarkGateway` | `ui/new_benchmark/protocols.py`    | yes                                                                  |
| `ProgressGateway`     | `ui/progress/protocols.py`         | yes                                                                  |
| `ResultGateway`       | `ui/results/protocols.py`          | yes                                                                  |
| `ResumeGateway`       | `ui/resume_benchmark/protocols.py` | yes                                                                  |
| `SettingsGateway`     | `ui/settings_dialog/protocols.py`  | yes                                                                  |
| `TaskEditorGateway`   | `ui/task_editor/protocols.py`      | yes                                                                  |

### STORY-104-AC-2

Each Common-Dialogs gateway is satisfied by the sibling gateway whose method set contains it, with no
adapter class written specifically for it:

| Common-Dialogs gateway  | Satisfied structurally by |
| ----------------------- | ------------------------- |
| `RunSummaryGateway`     | `NewBenchmarkGateway`     |
| `RenameRunGateway`      | `ResumeGateway`           |
| `ResumeSummaryGateway`  | `ResumeGateway`           |
| `RetrySelectionGateway` | `ResumeGateway`           |

## Test plan

- STORY-104-AC-1 — architecture, table-driven (one `@pytest.mark.parametrize` row per gateway
  Protocol), `tests/architecture/test_gateway_implementations_exist.py`,
  `test_every_ui_gateway_protocol_has_one_production_implementation`. Each row resolves the
  Protocol, asserts a non-`testing.py` class in the adapters layer satisfies it, and asserts that
  exactly one such class does. Passes only once STORY-105 … STORY-111 are `done`.
- STORY-104-AC-2 — unit, table-driven (one row per Common-Dialogs gateway),
  `tests/unit/test_common_dialog_gateway_structural_satisfaction.py`,
  `test_common_dialog_gateways_are_satisfied_by_their_sibling_gateway`. Each row assigns the sibling
  gateway instance to a variable annotated with the Common-Dialogs Protocol and calls every method
  the Protocol declares.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-104.
- [ ] The seven child stories (STORY-105 … STORY-111) are `done`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.

## Notes

- **Unowned follow-up: `RunValidator`.** `ui/new_benchmark/protocols.py` declares it locally and
  records that no canonical Protocol exists in `08-E_interfaces_contracts.md`, that only
  `02_New_Benchmark_Widget/description.md` and `implementation_structure.md` name it in prose, and
  that its eventual home is `backend/benchmark_pipeline/protocols`. STORY-071's notes additionally
  record that the widget-local `SyntheticSizeRuleValidator` must be subsumed by — not duplicated
  alongside — that future backend validator. No story owns it. It needs a scope decision from the
  owner before it can be written.
