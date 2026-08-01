---
id: STORY-113
title: Declare each gateway-boundary DTO once in the adapters layer and import it from the widget modules
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#1-scope-and-conventions
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 16_Engineering_Standards/01_PROJECT_STRUCTURE.md#5-the-module-public-surface
  - 16_Engineering_Standards/01_PROJECT_STRUCTURE.md#8-import-boundaries
modules:
  - adapters/ui_gateways/
  - ui/results/
  - ui/settings_dialog/
acceptance_criteria:
  - STORY-113-AC-1
  - STORY-113-AC-2
  - STORY-113-AC-3
  - STORY-113-AC-4
  - STORY-113-AC-5
edge_cases: []
depends_on:
  - STORY-065
  - STORY-067
  - STORY-104
adrs:
  - ADR-0014
  - ADR-0017
owner: coder
estimate: L
---

# STORY-113 — Declare each gateway-boundary DTO once in the adapters layer and import it from the widget modules

## Goal

Two of the seven per-widget gateway objects do not actually satisfy the contract the widget that
consumes them declares. The Result widget's gateway and the Settings dialog's gateway each pass data
across the boundary through record types that are declared twice — once by the widget module, once
again by the adapter — and because those record types are nominal, the two declarations are two
different types. A type checker rejects handing the real Result gateway to a variable typed as the
Result widget's own gateway contract, and likewise for Settings. This story removes the duplication so
each of those eleven record types exists exactly once, and so all seven gateways are genuinely, and
provably, usable where their widget expects them.

## In scope

- Moving eleven duplicated declarations to a single canonical home in `adapters/ui_gateways/`, per
  ADR-0017: `JudgeAnalysisGenerationOutcome` and `JudgeAnalysisGenerationResult` (the Result
  gateway's run-analysis callback payload), and `Severity`, `ValidationFinding`, `PreviewGroup`,
  `SettingsImportPreviewRow`, `SettingsImportPreview`, `SettingsImportResult`,
  `ProviderImportPreviewRow`, `ProviderImportPreview` and `ProviderImportResult` (the Settings
  gateway's import/export preview family).
- Re-exporting the nine settings names from `adapters/ui_gateways/api.py` and `__init__.py` so
  consumers reach them from the package root. The two `JudgeAnalysisGeneration*` names are already
  re-exported there and need no change.
- Deleting the local declarations in `ui/results/protocols.py` and `ui/settings_dialog/models.py`,
  replacing them with an import from `ollama_llm_bench.adapters.ui_gateways`, and keeping every name
  in each module's own `__all__` so no other file inside those two widget modules changes its import.
- Adding a new verification that binds each of the seven `make_*_gateway` factory results to a
  variable annotated with the corresponding widget module's own gateway contract — a real
  type-checked assignability proof, which the existing method-name comparison cannot give.
- Two small consequential tidies inside the touched modules: `ui/settings_dialog/protocols.py` may
  drop its `TYPE_CHECKING` forward-reference block, because the `models.py` ↔ `protocols.py` cycle it
  was working around disappears once the preview types no longer live in `models.py`; and
  `adapters/ui_gateways/__init__.py`'s docstring line claiming one gateway is still unimplemented is
  stale (all seven shipped) and is corrected in passing.

## Out of scope

- The seven gateway `Protocol` classes themselves keep their deliberate mirror declarations in
  `adapters/ui_gateways/protocols.py`. Protocols are structural, so mirroring them is safe, and the
  layering rule that forced them is unchanged — ADR-0017 covers the record types only.
- `ExportFilenameHelper`, declared locally by `ui/results/` and `ui/resume_benchmark/` — it is a
  collaborator contract with no duplicated record type and no adapters-side counterpart. STORY-077
  owns it per ADR-0010.
- `RunValidator`, declared locally by `ui/new_benchmark/` — still an unowned follow-up recorded in
  STORY-104's Notes, needing a scope decision from the owner.
- Wiring the gateways into `build_app` and the widget factories — STORY-077.
- Re-opening STORY-104. Its two criteria are proven and its seven child stories are done; this story
  defines its own criteria rather than re-numbering STORY-104's, because acceptance-criterion
  identifiers are permanent and a `done` story is never edited to absorb later work
  (`02_STORY_FORMAT.md` §3, §8). STORY-104's existing architecture test stays in place and keeps
  passing; STORY-113-AC-2 adds the stronger proof beside it.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the adapter is the
  exclusive boundary and exposes exactly one gateway contract per widget, built from standard-library
  and `msgspec` types only; the gateway is where view-model conversion lives. This is why the
  gateway-boundary record types belong to the adapter, not to a shared domain catalog.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#1-scope-and-conventions` — a type named in a contract
  signature but absent from the `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` catalog is "a small,
  contract-local type … declared inline in the section that introduces it". Take from it: one
  declaration, owned by the contract that introduces it — the justification for a single canonical
  home rather than a per-consumer copy.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — the Result gateway's contract
  surface, whose `regenerate_run_analysis` completion payload is one of the two duplicated families.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway` — the Settings gateway's
  contract surface. Its shape here is the one amended by ADR-0015 and ADR-0016 as it stands in
  `ui/settings_dialog/protocols.py` today, not the pre-amendment verbatim text; this story must not
  alter any method signature.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter layer is the
  only layer that holds backend contracts, and the controller calls the gateway and never sees a
  backend contract. Take from it: the widget importing a record type *from the adapter* is consistent
  with D-R-06, whereas importing it from the backend service would not be.
- `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#8-import-boundaries` — the folder table: `adapters/*`
  may import PySide6 and any `backend/*` package but must not import `ui`; `ui/*` widgets and dialogs
  may import `adapters/*`. This fixes the one legal direction for a single canonical declaration.
- `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#5-the-module-public-surface` — consumers import
  from the package root, never through `.api` or `._internal`. Take from it: the nine settings names
  must be re-exported through `adapters/ui_gateways/api.py` and `__init__.py`, and the widget modules
  import `from ollama_llm_bench.adapters.ui_gateways import …`.

## Design constraints

- **Direction is fixed and non-negotiable.** The canonical declaration lives in
  `adapters/ui_gateways/protocols.py`; the widget modules import it. The reverse is impossible — the
  `import-linter` contract "Adapters never import the UI layer" forbids it, and that contract is not
  to be weakened or given an `ignore_imports` entry for this story.
- **Do not import the backend types instead.** `ui/results/` must keep importing no
  `backend.run_analysis` symbol and `ui/settings_dialog/` must keep importing no
  `backend.import_export` symbol. Both are enforced today by
  `tests/architecture/test_result_widget_boundaries.py` and
  `tests/architecture/test_story_067_settings_general_and_transactions.py`; neither test's forbidden
  list may be relaxed.
- **The canonical shapes are the adapter's current ones, unchanged.** Keep
  `ValidationFinding.target` as a plain `str` (the adapter coerces a file-level finding's absent
  `item_key` to `""`), keep `JudgeAnalysisGenerationResult.provider_name` as the display-name snapshot
  the adapter resolves, and keep `backend_preview: object` as a **required keyword-only field** on
  both preview structs. Do not give `backend_preview` a `None` default: the adapter casts and uses it
  in `apply_settings_import`/`apply_provider_import`, so a default would trade a construction-time
  error for a run-time one.
- **The `backend_preview` field becomes visible to the Settings dialog and its tests.** Every
  UI-side construction site of `SettingsImportPreview`/`ProviderImportPreview` — chiefly the fixtures
  in `ui/settings_dialog/testing.py` and `ui/settings_dialog/tests/` — must now supply it. The
  dialog itself must continue to treat it as opaque: it is round-tripped untouched and never read,
  rendered, logged, or compared.
- **No gateway method signature changes.** This story moves declarations; it changes no parameter,
  no return type, and no threading marker. In particular the ADR-0015/ADR-0016 callback shapes on
  `test_provider`, `discover_models`, `probe_all` and `probe_embedding` stay exactly as they are.
- **Every module keeps its five-file public surface.** The nine settings names are declared in
  `adapters/ui_gateways/protocols.py` (not `models.py`), alongside the two `JudgeAnalysisGeneration*`
  names that already live there, so the whole gateway boundary is described in one file; `api.py`
  and `__init__.py` re-export them, and `_internal/settings/gateway.py` keeps importing them from
  `..protocols` as it does today.
- **Keep the surviving mirror guard green.**
  `tests/architecture/test_result_gateway_protocol_mirrors.py` guards `chart_data`'s return type
  across the two still-mirrored `ResultGateway` Protocol copies. It stays and must keep passing.
- **Criterion tier.** STORY-113-AC-1 and AC-2 are structural-contract criteria proven by
  architecture-tier tests, following the shape STORY-104-AC-1 established in this repository for the
  same subject matter; AC-3 … AC-5 are ordinary behavioural criteria.

## Acceptance criteria

### STORY-113-AC-1

Each gateway-boundary record type is one object, not two: for every name below, the symbol the widget
module exposes and the symbol `ollama_llm_bench.adapters.ui_gateways` exposes are the identical
object.

| Record type                      | Canonical declaration   | Widget-module symbol that must be the same object |
| -------------------------------- | ----------------------- | ------------------------------------------------- |
| `JudgeAnalysisGenerationOutcome` | `adapters/ui_gateways/` | `ui.results.protocols`                            |
| `JudgeAnalysisGenerationResult`  | `adapters/ui_gateways/` | `ui.results.protocols`                            |
| `Severity`                       | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `ValidationFinding`              | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `PreviewGroup`                   | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `SettingsImportPreviewRow`       | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `SettingsImportPreview`          | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `SettingsImportResult`           | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `ProviderImportPreviewRow`       | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `ProviderImportPreview`          | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |
| `ProviderImportResult`           | `adapters/ui_gateways/` | `ui.settings_dialog.models`                       |

These eleven names are the complete set of record types that a gateway Protocol's signature mentions
and that was declared in two places before this story.

### STORY-113-AC-2

Given a source file that constructs each of the seven gateways through its `make_*_gateway` factory
with fake collaborators and binds each result to a variable annotated with that gateway's contract as
declared by its own widget module — `ui.main_window.protocols.MainWindowGateway`,
`ui.new_benchmark.protocols.NewBenchmarkGateway`, `ui.progress.protocols.ProgressGateway`,
`ui.results.protocols.ResultGateway`, `ui.resume_benchmark.protocols.ResumeGateway`,
`ui.settings_dialog.protocols.SettingsGateway` and `ui.task_editor.protocols.TaskEditorGateway` —
when `mypy --strict` checks that file, then it reports no error for any of the seven bindings.

### STORY-113-AC-3

Given a settings-import preview obtained from the concrete Settings gateway's
`build_settings_import_preview`, when that preview object is passed back unchanged to
`apply_settings_import`, then the underlying import/export service receives the identical backend
preview object that produced it.

### STORY-113-AC-4

Given a provider-import preview obtained from the concrete Settings gateway's
`build_provider_import_preview`, when that preview object is passed back unchanged to
`apply_provider_import`, then the underlying import/export service receives the identical backend
preview object that produced it.

### STORY-113-AC-5

Given the run-analysis service returns a generated outcome, when the concrete Result gateway's
`regenerate_run_analysis` worker settles, then the value delivered to `on_complete` is an instance of
the same `JudgeAnalysisGenerationResult` type that `ui/results/` declares its callback against.

## Test plan

- STORY-113-AC-1 — architecture, table-driven (one `@pytest.mark.parametrize` row per record type,
  eleven rows), `tests/architecture/test_gateway_boundary_dto_single_declaration.py`,
  `test_gateway_boundary_dto_is_declared_once`. Each row resolves the name on the widget module and
  on `ollama_llm_bench.adapters.ui_gateways` and asserts the two are the same object. This file lives
  at the top level rather than in either module's colocated `tests/` because it is inherently a
  cross-module check, following `tests/architecture/test_result_gateway_protocol_mirrors.py`'s stated
  precedent.
- STORY-113-AC-2 — architecture, `tests/architecture/test_gateway_protocol_assignability.py`,
  `test_every_gateway_is_assignable_to_its_widget_declared_protocol`. The seven widget-module
  Protocols are imported under `TYPE_CHECKING` and used only as annotations, so the static proof is
  carried by the repository-wide `mypy --strict` gate over `testpaths`; the pytest body additionally
  builds all seven through their real factories with fake collaborators and calls one method on each,
  proving the bindings hold at run time too. This reuses the technique
  `tests/unit/test_common_dialog_gateway_structural_satisfaction.py` (STORY-104-AC-2) established,
  applied to all seven gateways.
- STORY-113-AC-3 — unit, colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_apply_settings_import_round_trips_the_original_backend_preview`. A fake import/export service
  records the object it is handed and the test asserts it is the same object the build call returned.
- STORY-113-AC-4 — unit, same file,
  `test_apply_provider_import_round_trips_the_original_backend_preview`.
- STORY-113-AC-5 — unit, colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_result_gateway.py`,
  `test_regenerate_run_analysis_delivers_the_ui_declared_result_type`. Asserts the captured callback
  argument is an instance of the type imported from `ui.results.protocols`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-113.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/ui_gateways/`, `ui/results/`
  and `ui/settings_dialog/`, with no new `ignore_imports` entry and no weakened contract.
- [ ] The already-`done` stories whose declarations or tests this story touches stay green with no
  criterion re-interpreted: STORY-061 and STORY-065 (`ui/results/` boundaries and the run-analysis
  callback payload), STORY-066 and STORY-067 (`ui/settings_dialog/`'s validation-finding and
  import-preview families and the atomic Save/Reset surface), STORY-108 and STORY-110 (the two
  concrete gateways). Their full test suites pass unchanged.
- [ ] STORY-104's own tests — `tests/architecture/test_gateway_implementations_exist.py` and
  `tests/unit/test_common_dialog_gateway_structural_satisfaction.py` — still pass, and
  `tests/architecture/test_result_gateway_protocol_mirrors.py` still passes.
- [ ] No gateway method signature changed; the ADR-0015/ADR-0016 callback shapes are byte-identical.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Why the adapters layer wins and not the UI layer.** The two requirements in play cannot both be
  satisfied nominally: ADR-0014's decision item 2 wants each factory to return the *widget-declared*
  contract type, while its item 3 and the real `import-linter` contract forbid `adapters/*` from
  importing `ui/*`. `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` §8's folder table permits
  `ui/*` → `adapters/*` and forbids the reverse, so the adapters layer is the only place a single
  declaration can sit. ADR-0017 records that reasoning and the alternatives weighed against it.
- **Why the duplicated Protocols are harmless but the duplicated records are not.** A `Protocol` is
  structural, so one concrete class satisfies both copies with no import either way. A
  `msgspec.Struct` and a `StrEnum` are nominal, so two field-identical declarations are two
  incompatible types — which is why a callback parameter typed against one copy makes the whole
  gateway unassignable to the Protocol that mentions the other. This is why keeping both copies and
  merely testing that they stay field-for-field identical cannot fix the defect.
- **This closes one of the two unowned follow-ups STORY-104 recorded.** STORY-104's Notes named both
  the missing corrective ADR (now ADR-0017) and this de-duplication. The other follow-up it names —
  `RunValidator`'s scope, and STORY-071's related note that the widget-local
  `SyntheticSizeRuleValidator` must be subsumed rather than duplicated by a future backend validator
  — remains unowned and still needs an owner decision.
