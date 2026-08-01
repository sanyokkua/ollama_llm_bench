---
id: STORY-104
title: Give every UI adapter gateway exactly one production implementation
status: done
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
  adapters layer's public surface.
- Coordinating the seven per-gateway child stories: STORY-105 (Main Window), STORY-106 (New
  Benchmark), STORY-107 (Progress), STORY-108 (Result), STORY-109 (Resume), STORY-110 (Settings),
  STORY-111 (Task Editor).
- Proving that the four Common-Dialogs gateways are satisfied structurally by those same seven
  classes — by the sibling gateways their method sets are subsets of — so no eighth adapter class is
  written for any of them.

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
- Recording the deviation from ADR-0014's decision item 3 that the child stories shipped (see Notes)
  — that needs its own corrective ADR, which no story owns.

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
- **AC-1 resolves the user-interface copy of each Protocol, never the adapter's own copy.**
  `adapters/ui_gateways/protocols.py` declares its own mirror of six of the seven gateways plus
  `SettingsGateway`, because `import-linter` forbids `adapters/*` from importing `ui/*` and the
  `make_*_gateway` factories still need a return type to annotate. Resolving those mirrors would
  make the architecture test self-satisfying — the adapter checked against its own declaration. The
  Protocol object each parametrised row resolves is therefore the one in the `Declared in` column of
  AC-1's table, which is the widget module's copy and the source of truth for the gateway's shape.
- **The production classes are private; they are reached through the module's factories.** Per the
  module public-surface rule, `adapters/ui_gateways/api.py` exports only the seven `make_*_gateway`
  functions — the seven concrete classes are `_`-prefixed under `_internal/<widget>/gateway.py` and
  are not exported. "Reachable through the adapters layer's public surface" therefore means reached
  by calling the factory, not by importing a class name.
- **`SettingsGateway`'s current shape is the amended one.** ADR-0015 and ADR-0016 changed
  `test_provider`, `discover_models`, `probe_all` and `probe_embedding` to return `None` and deliver
  their results through a callback or through `ReadinessService`'s existing readiness-changed event.
  The expected method set for that row comes from `ui/settings_dialog/protocols.py` as it stands
  today, not from `08-E` §7b.6's verbatim pre-amendment text.

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

Each Common-Dialogs gateway is satisfied by the sibling gateway(s) whose method set contains it, with
no adapter class written specifically for it:

| Common-Dialogs gateway  | Satisfied structurally by          |
| ----------------------- | ---------------------------------- |
| `RunSummaryGateway`     | `NewBenchmarkGateway`              |
| `RenameRunGateway`      | `ResumeGateway`, `ProgressGateway` |
| `ResumeSummaryGateway`  | `ResumeGateway`                    |
| `RetrySelectionGateway` | `ResumeGateway`                    |

These four are the complete set of gateway Protocols `ui/common_dialogs/protocols.py` declares. The
fifth Protocol in that file, `RunAnalysisDispatcher`, is not a gateway — it is a dialog's dispatch
surface onto its own parent tab controller, satisfied by
`ui.results._internal.run_analysis_tab.controller.JudgeAnalysisTabController` and never by an
adapter — so it is outside this criterion's case space.

## Test plan

- STORY-104-AC-1 — architecture, table-driven (one `@pytest.mark.parametrize` row per gateway
  Protocol), `tests/architecture/test_gateway_implementations_exist.py`,
  `test_every_ui_gateway_protocol_has_one_production_implementation`. Each row resolves the
  user-interface module's Protocol (never `adapters/ui_gateways/protocols.py`'s mirror), asserts a
  non-`testing.py` class in the adapters layer satisfies it, and asserts that exactly one such class
  does. Passes only once STORY-105 … STORY-111 are `done`.
- STORY-104-AC-2 — unit, table-driven (one row per Common-Dialogs gateway),
  `tests/unit/test_common_dialog_gateway_structural_satisfaction.py`,
  `test_common_dialog_gateways_are_satisfied_by_their_sibling_gateway`. Each row builds the sibling
  gateway through its `adapters/ui_gateways` factory with fake backend collaborators, assigns it to
  a variable annotated with the Common-Dialogs Protocol, and calls every method the Protocol
  declares.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-104.
- [x] The seven child stories (STORY-105 … STORY-111) are `done`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.

## Notes

- **Unowned follow-up: `RunValidator`.** `ui/new_benchmark/protocols.py` declares it locally and
  records that no canonical Protocol exists in `08-E_interfaces_contracts.md`, that only
  `02_New_Benchmark_Widget/description.md` and `implementation_structure.md` name it in prose, and
  that its eventual home is `backend/benchmark_pipeline/protocols`. STORY-071's notes additionally
  record that the widget-local `SyntheticSizeRuleValidator` must be subsumed by — not duplicated
  alongside — that future backend validator. No story owns it. It needs a scope decision from the
  owner before it can be written.
- **Unowned follow-up: a corrective ADR for ADR-0014's decision item 3.** ADR-0014 says
  `adapters/ui_gateways/` "declares no gateway Protocol of its own", while its decision item 2 says
  each factory returns "the corresponding **UI-declared** gateway Protocol type". Those two cannot
  both hold: annotating with the user-interface module's type *is* importing that module, which the
  "adapters never import the UI layer" `import-linter` contract (added by STORY-105) forbids. The
  child stories resolved it in favour of the layering rule and shipped mirrored declarations in
  `adapters/ui_gateways/protocols.py`, each documented as a deliberate duplicate that must be kept
  in step with its user-interface counterpart. ADR-0014 is accepted and so may no longer be edited
  in place (`04_ADR_FORMAT.md` §8), so recording this needs a new ADR that no story owns. This story
  only has to test against the structure as shipped — see Design constraints.
