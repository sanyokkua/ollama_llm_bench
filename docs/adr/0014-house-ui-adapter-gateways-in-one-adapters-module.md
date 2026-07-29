# ADR-0014 — House the seven concrete UI adapter gateways in one new `adapters/ui_gateways/` module

**Status:** accepted
**Date:** 2026-07-29
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** D-R-06, SPEC-074, SPEC-075, ADR-0010

## Context and problem statement

Every widget and dialog reaches the backend through exactly one per-widget **gateway** object. The
rule is binding: `08-A_architecture_principles.md` §6 makes the adapter layer "the **only** layer
that holds backend Protocols", and D-R-06/SPEC-074 forbid a UI controller from holding a backend
Store or Service Protocol directly. `08-E_interfaces_contracts.md` §7b defines the seven gateways
by name and method — `MainWindowGateway` (12 methods), `NewBenchmarkGateway` (6),
`ResumeGateway` (22), `ProgressGateway` (14), `ResultGateway` (11), `SettingsGateway` (22),
`TaskEditorGateway` (4) — about 91 methods in total.

All seven Protocols are declared in the UI layer today (`ui/main_window/protocols.py`,
`ui/new_benchmark/protocols.py`, and so on) and **not one has a production implementation.** The
only things satisfying them are four test fakes in `testing.py` files and a handful of
widget-internal shims. The consequence is concrete and blocking: `make_main_window` requires
`gateway: MainWindowGateway`, so `build_app` (STORY-077) has nothing to pass, and wiring the two
workspaces additionally needs the New Benchmark, Progress, Result, Resume and Task Editor gateways.
No existing story owns this work.

The specification does not say where those implementations live, and that is the question this ADR
must answer: **where does the concrete implementation of each `08-E` §7b gateway live, and how is it
constructed and injected?** `08-E` §7b is explicitly contract-level — §1 states "No implementation
code" — so it fixes the shape and says nothing about the home. `01_MODULE_INVENTORY.md` §6 says the
adapter "wires behind that widget's gateway", placing the implementations in the adapters layer, but
the inventory's §5 adapters table lists only eleven modules (`qt_event_bus`, `qt_benchmark_flow`,
`qt_table_models`, `qt_runnables`, `store_qt_bridge`, `qt_inference_activity_bridge`,
`workspace_controller`, `notification_service`, `native_pickers`, `clipboard`,
`file_system_actions`) and **none of them is a per-widget gateway module.** A `modules:`
front-matter entry that is not present in that table fails `just trace-check`
(`scripts/_traceability_lib.py::load_module_inventory` does exact-set membership over the
backtick-quoted paths in the inventory file), so a new path cannot simply be invented.

## Decision drivers

- D-R-06/SPEC-074 must survive intact: a UI controller holds only its own gateway; the gateway is
  the object that holds the backend Stores and Services.
- The gateways are the adapter layer's designated home for Qt-specific concerns — thread
  marshalling, command-record construction, view-model conversion (SPEC-074) — so they belong in
  `adapters/*`, not in `ui/*` and not in `backend/*`.
- `01_PROJECT_STRUCTURE.md` §7 caps `compose.py` at roughly 50–200 lines of plain keyword-argument
  factory calls with "no logic".
- `01_PROJECT_STRUCTURE.md` §6 splits a module whose `_internal/` exceeds roughly 1500 lines into a
  parent feature with sub-feature packages; `08-A` §10 forbids god services.
- Every other adapters module carries an `Independent test target` of `yes`; a gateway must be unit
  testable against fake backend Protocols with no `QApplication`.
- Adding a module path the inventory does not list fails `just trace-check` — the same constraint
  that shaped ADR-0010, which deliberately housed the single-instance lock in the existing
  `backend/infra/` to avoid an inventory change.
- The correction should be the **smallest** one that yields a defensible structure, because
  `docs/v3_specification/` is read-only and has been corrected exactly once before, by explicit
  owner approval.

## Considered options

- Option A — Host the seven gateway implementations inside existing inventoried adapters modules.
- Option B — Define the seven gateways inline in `compose.py`.
- Option C — Add seven new sibling adapters modules, one per gateway (seven new inventory rows).
- Option D — Add one new adapters module, `adapters/ui_gateways/`, holding seven per-widget
  sub-feature packages under `_internal/` (one new inventory row).

## Decision outcome

Chosen option: **Option D**, because it is the only option that keeps each gateway a bounded,
independently testable unit without turning an existing module into a god-module or blowing the
composition root's line budget, and it costs the read-only inventory exactly **one** new row —
the smallest correction that yields a defensible structure.

Concretely:

1. **Home.** `src/ollama_llm_bench/adapters/ui_gateways/` is a normal adapters module with the
   standard five-file public surface. Its `_internal/` holds seven sub-feature packages — one per
   `08-E` §7b gateway — exactly mirroring how `ui/results/` hosts its `summary_tab/`,
   `details_tab/`, `charts_tab/` and `run_analysis_tab/` sub-features under `_internal/` without
   any of the four needing its own inventory row.
1. **Public surface.** `api.py` exposes seven factories — `make_main_window_gateway`,
   `make_new_benchmark_gateway`, `make_resume_gateway`, `make_progress_gateway`,
   `make_result_gateway`, `make_settings_gateway`, `make_task_editor_gateway` — each returning the
   corresponding UI-declared gateway Protocol type. This matches the "per-table model factories"
   and "per-dialog factory functions" shape already used by `adapters/qt_table_models/` and
   `ui/common_dialogs/`.
1. **Protocol ownership stays in the UI module.** `adapters/ui_gateways/` declares no gateway
   Protocol of its own. Each gateway Protocol keeps living in the widget module that consumes it
   (`ui/main_window/protocols.py`, …) and each concrete class satisfies it **structurally** — no
   subclassing, no import of the UI module from the adapters module. This preserves the existing
   `import-linter` direction (`adapters/*` must not import `ui`).
1. **Construction and injection.** `compose.py` constructs each gateway exactly once, after the
   backend services and before the widgets, by calling the factory with plain keyword arguments —
   the backend Protocol handles it reads out of its own internal `ApplicationContext`
   (`08-E` §23). Each gateway also receives the single `TaskRunner` handle for the methods
   `08-E` marks *blocking*. `compose.py` then passes each gateway into exactly one widget factory.
   No gateway is ever handed the `ApplicationContext` itself (SPEC-075), and no widget receives more
   than its own gateway plus the few UI-layer services it is permitted to see.
1. **The four Common-Dialogs gateways need no separate implementation.** `RunSummaryGateway`,
   `RenameRunGateway`, `ResumeSummaryGateway` and `RetrySelectionGateway` are method-name subsets of
   `NewBenchmarkGateway` and `ResumeGateway`, so those two concrete classes satisfy them
   structurally with no shim — the pattern already documented in
   `ui/common_dialogs/protocols.py`'s module docstring.

### What the owner must ratify

One correction to `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md`,
comprising four edits:

| #   | Location                  | Edit                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | §5 Adapters Modules table | Add one row for `adapters/ui_gateways/`: purpose "Implement the seven per-widget UI adapter gateways of `08-E` §7b over the backend Protocols, so no UI module holds a backend Store/Service Protocol"; public API the seven `make_*_gateway` factories; notable dependencies PySide6, `backend/*` Protocols, `backend/infra` (`TaskRunner`); independent test target `yes`; implementer note "seven sub-feature packages under `_internal/`, one per gateway; carries no business logic — delegation, view-model conversion and thread marshalling only". |
| 2   | §3 Module Layering Map    | Add `UIGW["adapters/ui_gateways/"]` to the `ADAPTERS` subgraph.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 3   | §8 count table            | Adapters row: Modules `11` → `12`, test target `yes` `11` → `12`. Total row: `62` → `63`, `yes` `53` → `54`.                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 4   | §8 closing prose          | Extend the sentence that records the adapters row rising "from nine to eleven modules" to record the twelfth.                                                                                                                                                                                                                                                                                                                                                                                                                                              |

Until that correction lands, STORY-104 … STORY-111 cite the inventoried **UI module whose gateway
Protocol they satisfy** in `modules:` rather than `adapters/ui_gateways/`, on the STORY-076/ADR-0010
precedent that a Phase-11 story may cite the module it wires. That keeps `just trace-check` green
while the correction is pending; each story records the substitution in its Design constraints and
must add `adapters/ui_gateways/` once the row exists.

### Consequences

- Positive — Every UI widget factory becomes constructible, unblocking STORY-077 and therefore all
  of Phase 11. D-R-06/SPEC-074 hold by construction: the gateways are the only objects holding
  backend Protocols on the UI side. Each gateway is a bounded sub-feature package, unit testable
  against fake backend Protocols with no `QApplication`. `compose.py` gains seven factory calls
  rather than roughly 91 method bodies.
- Negative — It costs a correction to the read-only specification, which is why this ADR is
  `proposed` rather than `accepted`. Until the owner ratifies it, eight stories stay `draft` and
  their `modules:` entries name the UI module served rather than the module that actually gains the
  code — a documented, deliberate imprecision that must be repaired when the row lands.
- Negative — `adapters/ui_gateways/` will be the largest adapters module in the tree (roughly
  1200–1800 lines across its seven sub-features). The sub-feature split is what keeps it inside the
  `01_PROJECT_STRUCTURE.md` §6 rule, but the parent module's `api.py` will re-export seven factories
  where every other adapters module re-exports one or two.
- Neutral — **An open question this ADR does not settle, and must not.** `08-E` §7b marks several
  gateway methods *blocking* while pinning a synchronous return — `SettingsGateway.test_provider`,
  `probe_all`, `probe_embedding`, `discover_models` and the import/export methods among them — and
  the already-shipped Settings dialog calls them directly from GUI-thread slots
  (`ui/settings_dialog/_internal/providers_tab/controller.py`, `sub_dialogs/provider_edit_view.py`).
  SPEC-074 makes the gateway responsible for thread marshalling, but
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §11 lists "blocking on a unit's `Future`
  from the GUI thread" as an anti-pattern and states the GUI thread never blocks. Those three
  clauses cannot all hold for a method that is *blocking* and returns synchronously. Settling it
  needs its own ADR; STORY-110 (the Settings gateway) records the conflict and may not move to
  `ready` before that ADR exists.
- Neutral — The `FileChangeWatcher` collaborator Protocol (`ui/task_editor/protocols.py`) is **not**
  covered by this decision. It is not an `08-E` §7b gateway, and its home — the existing
  `adapters/file_system_actions/` — needs no inventory change, so STORY-112 settles it in its own
  Design constraints without an ADR (`04_ADR_FORMAT.md` §2: a cheaply reversible placement is not
  ADR material).

## Pros and cons of the options

### Option A — Host the gateways inside existing inventoried adapters modules

- Good — Needs no inventory correction at all, and there is precedent for an inventoried adapters
  module exposing a gateway: the `adapters/qt_inference_activity_bridge/` row already says it
  "exposes the UI-facing gate gateway".
- Bad — Every gateway is cross-capability by construction, so no capability-scoped module can host
  one honestly. `MainWindowGateway` spans `SettingsService`, `ReadinessService` and
  `BenchmarkFlowApi`; `SettingsGateway` spans six backend modules. Putting it in
  `adapters/qt_benchmark_flow/` would contradict that row's own stated purpose ("Qt-side facade over
  `backend/benchmark_pipeline`", "thin proxy") and its Notable-dependencies column.
- Bad — Concentrating seven unrelated widget facades in one existing module produces exactly the god
  module `08-A` §10 forbids, and pushes that module's `_internal/` past the ~1500-line split
  threshold anyway — so the split has to happen, and Option A only delays it.

### Option B — Define the seven gateways inline in `compose.py`

- Good — Zero inventory change; the gateways sit next to the wiring that injects them.
- Bad — Arithmetically impossible against the budget. Roughly 91 method bodies plus seven class
  declarations is several hundred lines in a file capped at 50–200 lines total, of which the wiring
  itself already accounts for about 80–120.
- Bad — `01_PROJECT_STRUCTURE.md` §7 says `compose.py` is "manual factory calls" with no logic, and
  §5 bans loose single-file modules. Gateways carry real logic (thread marshalling, view-model
  conversion, the atomic two-store Save).
- Bad — `compose.py` has no colocated `tests/` directory, so seven gateways would be reachable only
  through integration tests, against the `yes` test target every other adapters module carries.

### Option C — Seven new sibling adapters modules, one per gateway

- Good — Maps one-to-one onto `08-E` §7b.1–§7b.7; each module is small, single-purpose and
  independently testable; each story touches exactly one module.
- Bad — Costs seven new inventory rows and rewrites three cells plus a prose sentence in the §8
  count table (adapters 11 → 18, total 62 → 69). That is a far larger edit to a read-only document
  than the structure warrants, for no structural gain over Option D.
- Bad — Seven sibling top-level modules that only ever differ by which widget they serve reads as
  the technical-layer directory `01_PROJECT_STRUCTURE.md` §4 explicitly rejects, rather than as
  seven features.

### Option D — One new `adapters/ui_gateways/` module with seven sub-features

- Good — One inventory row. Directly precedented: `ui/results/` hosts four sub-feature packages
  under `_internal/`, none of which needs its own row, and `01_PROJECT_STRUCTURE.md` §6 names
  "parent feature with sub-features" as the sanctioned answer to a module this size.
- Good — Each gateway stays a bounded unit with its own tests; each story touches one module;
  `compose.py` gains seven factory calls.
- Bad — The parent module's `api.py` re-exports seven factories, a wider public surface than any
  other adapters module, and the module becomes the largest in `adapters/`.
- Bad — Still requires an owner-approved edit to a read-only specification file, so it cannot be
  accepted unilaterally.

## Links

- Related ADRs: ADR-0010 (Phase-11 composition root; established both the "cite the module you
  wire" precedent and the preference for avoiding inventory additions)
- Spec clauses: `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#23-the-application-context`,
  `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer`,
  `14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules`,
  `14_Process_and_Traceability/01_MODULE_INVENTORY.md#6-ui-modules`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#5-the-module-public-surface`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#6-sub-features-and-layering-depth`,
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md#7-the-composition-root`
- Stories: STORY-104 (umbrella), STORY-105, STORY-106, STORY-107, STORY-108, STORY-109, STORY-110,
  STORY-111 apply this decision; STORY-077 consumes it
