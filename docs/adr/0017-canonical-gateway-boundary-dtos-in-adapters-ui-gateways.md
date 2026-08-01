# ADR-0017 — Make `adapters/ui_gateways/` the single declaration point for the gateway-boundary DTOs

**Status:** accepted
**Date:** 2026-08-01
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-0014, ADR-0015, ADR-0016, D-R-06, SPEC-074

## Context and problem statement

ADR-0014 houses the seven concrete `08-E` §7b UI adapter gateways in `adapters/ui_gateways/`. Two of
its decision items cannot both hold. Item 2 requires each `make_*_gateway` factory to return "the
corresponding **UI-declared** gateway Protocol type"; item 3 requires that `adapters/ui_gateways/`
"declares no gateway Protocol of its own" and never imports the UI module. Annotating a return type
with the UI-declared Protocol *is* importing the UI module, which the real `import-linter` contract
"Adapters never import the UI layer" (`pyproject.toml`, added by STORY-105) forbids. STORY-105 …
STORY-111 resolved the conflict in favour of the layering rule and shipped same-named mirror
declarations in `adapters/ui_gateways/protocols.py`, each documented as a deliberate duplicate. That
module's own docstring already records the contradiction and asks for a corrective ADR.

Mirroring the seven **Protocols** is harmless, because Python Protocols are structural: a concrete
class satisfies both copies with no import in either direction. Mirroring the **DTOs those Protocols
mention in their signatures** is not harmless, because `msgspec.Struct` and `StrEnum` types are
*nominal*. Two structurally identical `msgspec.Struct` declarations are two distinct types, so a
callback typed `Callable[[AdapterJudgeAnalysisGenerationResult], None]` is not assignable to one
typed `Callable[[UiJudgeAnalysisGenerationResult], None]`. Exactly two of the seven gateways mention
duplicated DTOs in their signatures, and exactly those two fail: assigning `_ResultGateway` to a
variable annotated `ui.results.protocols.ResultGateway`, or `_SettingsGateway` to one annotated
`ui.settings_dialog.protocols.SettingsGateway`, is a `mypy --strict` `[return-value]` error. The
other five gateways pass the identical check. STORY-104-AC-1's shipped architecture test compares
method *names* only, so it reports all seven as satisfied and does not see this.

The duplication is therefore not merely redundant text — it means two of the seven gateways do not
actually satisfy the Protocol the widget that consumes them declares. The question this ADR answers
is: **which module owns the single canonical declaration of a DTO that appears in a gateway
Protocol's signature, given that `adapters/*` may never import `ui/*`?**

## Decision drivers

- `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` §8's folder table admits exactly one legal
  direction between these two layers: `adapters/*` may import "PySide6, any `backend/*` package" and
  must not import `ui`; `ui/*` (widgets and dialogs) may import "`adapters/*`". A single canonical
  declaration must therefore live at or below the adapters layer.
- The result must be *nominally* satisfying, not merely structurally similar — `mypy --strict` is the
  authority, and the whole point is that the concrete gateway is assignable to the widget's own
  Protocol type.
- `ui/results/` may not import `backend/run_analysis` and `ui/settings_dialog/` may not import
  `backend/import_export` — architecture-test-enforced boundaries established by STORY-061/STORY-065
  and STORY-067 respectively. Any fix must leave both intact.
- The mirrored DTOs are not verbatim copies of their backend counterparts. The adapter's
  `ValidationFinding.target` coerces a file-level `ImportFinding.item_key is None` to `""`;
  `JudgeAnalysisGenerationResult.provider_name` carries a display-name snapshot the backend result
  has no field for; and `SettingsImportPreview`/`ProviderImportPreview` carry a `backend_preview`
  round-trip handle. A canonical home must be able to hold those gateway-boundary-specific shapes.
- `08-E` §1 classifies a type named in a contract signature but absent from the
  `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` catalog as "a small, contract-local type … declared
  inline in the section that introduces it" — one declaration, owned by the contract that introduces
  it, not a shared domain type.
- The correction must not require editing `docs/v3_specification/` (read-only) and must not require
  editing ADR-0014, which is accepted and therefore immutable.

## Considered options

- Option A — Keep both copies and add a per-DTO architecture test asserting the two declarations stay
  field-for-field identical.
- Option B — Declare each affected DTO once in `adapters/ui_gateways/`, re-export it from that
  module's public surface, and have the owning UI module import and re-export it instead of
  re-declaring it.
- Option C — Delete both copies and let `ui/results/` and `ui/settings_dialog/` use the backend types
  (`backend.run_analysis.RunAnalysisResult`, `backend.import_export.models.*`) directly, as the
  adapters already may.
- Option D — Move the affected DTOs into `backend/domain/`, which both `adapters/*` and `ui/*` are
  already permitted to import.

## Decision outcome

Chosen option: **Option B**, because it is the only option that produces a single nominal type
without breaking an existing enforced import boundary, and it runs with the one import direction the
layering table already permits (`ui/*` → `adapters/*`) rather than against the one it forbids.

Concretely:

1. **Canonical home.** `adapters/ui_gateways/protocols.py` is the single declaration point for every
   DTO that appears in a gateway Protocol's signature and is not already in `backend/domain/`. The
   eleven affected names are:

   | Family                        | Names                                                                                                                                                                                                     |
   | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `ResultGateway` (STORY-065)   | `JudgeAnalysisGenerationOutcome`, `JudgeAnalysisGenerationResult`                                                                                                                                         |
   | `SettingsGateway` (STORY-067) | `Severity`, `ValidationFinding`, `PreviewGroup`, `SettingsImportPreviewRow`, `SettingsImportPreview`, `SettingsImportResult`, `ProviderImportPreviewRow`, `ProviderImportPreview`, `ProviderImportResult` |

1. **Public surface.** All eleven are re-exported from `adapters/ui_gateways/api.py` and
   `__init__.py`, so consumers import them from the package root per
   `01_PROJECT_STRUCTURE.md` §5. The two `JudgeAnalysisGeneration*` names are already re-exported
   there; the nine settings names are added.

1. **The UI modules import, never re-declare.** `ui/results/protocols.py` and
   `ui/settings_dialog/models.py` delete their local declarations and import the canonical names from
   `ollama_llm_bench.adapters.ui_gateways`, keeping them in their own `__all__` so every existing
   downstream import inside those widget modules keeps resolving unchanged.

1. **The seven Protocols stay mirrored.** This decision covers DTOs only. The seven gateway
   `Protocol` classes keep their deliberate mirror declarations in `adapters/ui_gateways/protocols.py`
   — structural typing makes those safe, and item 3's layering rule that forced them stays in force.
   ADR-0014's decision item 3 is corrected only to the extent that `adapters/ui_gateways/` does
   declare gateway-shape types of its own, and is the canonical owner of the DTO subset above.

1. **What "satisfies the Protocol" now means.** With the DTOs unified, every one of the seven
   concrete gateways is assignable to its widget module's own Protocol type under `mypy --strict`.
   That becomes the verification standard, replacing method-name comparison as the sole check.

### Consequences

- Positive — Each of the eleven DTOs exists exactly once, so the "any change to one side of a pair
  must be mirrored in the other" hazard that STORY-108's spec-conformance review already caught once
  (`chart_data`'s return type) is removed for the DTO half of the seam. All seven gateways become
  nominally assignable to their widget-declared Protocol, which is what STORY-077's wiring needs.
- Negative — `ui/results/protocols.py` and `ui/settings_dialog/models.py` gain a module-level import
  of `adapters.ui_gateways`, whose package root transitively imports the seven gateway
  implementations and their backend dependency graph. That is a materially heavier import than a leaf
  DTO module, and it is accepted: both widget modules already import several `adapters/*` packages at
  module level (`ui/settings_dialog/models.py` imports `adapters.clipboard`,
  `adapters.file_system_actions`, `adapters.native_pickers`, `adapters.notification_service` today),
  and no cycle is possible because `adapters/*` can never import `ui/*`.
- Negative — The UI-visible `SettingsImportPreview`/`ProviderImportPreview` now carry the
  `backend_preview` field, which is meaningless to the Settings dialog and is an opaque `object` it
  must round-trip untouched. Every UI-side construction site (chiefly test fixtures) must supply it.
  This is accepted rather than defaulted, because the adapter's `apply_settings_import`/
  `apply_provider_import` cast and use it, and a defaulted `None` would move a construction-time
  error to a run-time one.
- Negative — `adapters/ui_gateways`'s public surface widens from nineteen names to twenty-eight,
  reinforcing ADR-0014's own recorded downside that this module has the widest public surface in
  `adapters/`.
- Neutral — This ADR does **not** supersede ADR-0014. ADR-0014's decision — the module's home, its
  seven factories, its sub-feature layout under `_internal/`, and its `compose.py` wiring — remains
  in force in full; only the "declares no gateway Protocol of its own" clause of its decision item 3
  is corrected here. `04_ADR_FORMAT.md` §7 models supersession as replacing a whole decision, which
  is not what happened, and ADR-0014 may not be edited in place (§6), so a related-to link is the
  correct record.
- Neutral — The `ExportFilenameHelper` Protocol declared locally in `ui/results/protocols.py` and
  `ui/resume_benchmark/` is out of this decision's scope. It is a collaborator Protocol with no
  duplicated DTO and no adapters-side counterpart; STORY-077 owns it per ADR-0010.

## Pros and cons of the options

### Option A — Keep both copies plus a field-for-field mirror-sync test

- Good — Zero import-graph change; extends the existing
  `tests/architecture/test_result_gateway_protocol_mirrors.py` precedent with no production edit.
- Bad — Cannot work. `msgspec.Struct` and `StrEnum` are nominal types, so two field-identical
  declarations remain two incompatible types; the `mypy --strict` failure survives a perfectly
  passing mirror test. The test would assert the very property that is already true and still leave
  the defect in place.
- Bad — Doubles the maintenance surface permanently for eleven types, on a seam that has already
  drifted once.

### Option B — `adapters/ui_gateways/` declares once; the UI imports it

- Good — One nominal type per DTO; both failing gateways become assignable to their widget-declared
  Protocol under `mypy --strict`.
- Good — Runs with the permitted import direction (`ui/*` → `adapters/*`) and needs no change to any
  `import-linter` contract, architecture test, or specification file.
- Good — Keeps the gateway-boundary-specific shapes (`target` coercion, `provider_name`,
  `backend_preview`) in the layer that produces them.
- Bad — Two UI modules gain a heavy package-root import, and the UI-visible preview structs gain a
  field the dialog does not read.

### Option C — Let the UI modules use the backend types directly

- Good — Also yields one nominal type, with no new adapters-side public surface.
- Bad — Breaks the two boundaries STORY-061/STORY-065 and STORY-067 established and enforce by
  architecture test (`ui/results/` must not import `backend.run_analysis`; `ui/settings_dialog/` must
  not import `backend.import_export`), and contradicts D-R-06's rule that the widget reaches the
  backend only through its gateway.
- Bad — The backend types do not carry the gateway-boundary fields. `RunAnalysisResult` has no
  `provider_name`; `ImportFinding.item_key` is optional where the UI needs a plain `str`; the preview
  entries carry `ProviderConfigDraft` values the dialog must never see.

### Option D — Move the DTOs into `backend/domain/`

- Good — The lightest possible import for both consumers, and `backend/domain/` is already on the
  `ui/*` allow-list, so nothing about the layering changes.
- Bad — These are gateway-boundary presentation types, not domain values. `08-E` §1 classifies a type
  absent from the `02_DTOS_AND_ENUMS.md` catalog as contract-local to the section that introduces it,
  and `backend/domain/`'s import rule permits only the standard library and `msgspec` — an opaque
  `backend_preview` handle onto a `backend/import_export` object has no place there.
- Bad — Costs a correction to the read-only `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` catalog and the
  module inventory, which is exactly the cost ADR-0010 and ADR-0014 both worked to minimise, for a
  structure that is worse on ownership grounds.

## Links

- Related ADRs: ADR-0014 (houses the gateways in `adapters/ui_gateways/`; its decision item 3 is
  corrected here), ADR-0015 and ADR-0016 (fixed the amended `SettingsGateway` shape this decision
  must preserve)
- Spec clauses:
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#1-scope-and-conventions`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway`,
  `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#5-the-module-public-surface`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#8-import-boundaries`
- Stories: STORY-113 applies this decision; STORY-104 (umbrella) recorded the gap it closes;
  STORY-065, STORY-067, STORY-108 and STORY-110 created the duplicated declarations it removes;
  STORY-077 consumes the result
