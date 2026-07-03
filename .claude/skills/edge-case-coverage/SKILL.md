---
name: edge-case-coverage
description: Use when a story cites an EC- id, or when deciding what edge-case tests a module needs.
---

# Edge Case Coverage

An edge case is a non-obvious behaviour the implementation must handle. Edge cases are catalogued with
stable identifiers so a test, a story, or a code comment can cite one precisely and permanently — an
identifier is never reassigned or renumbered once published.

Sources of truth:
- `docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md` — the catalog for ten of the scopes (the
  trigger, expected behaviour, and failure-to-avoid for each case).
- `docs/v3_specification/14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` — the bridge from
  each catalogued id to the test tier, the proving module, and the acceptance-criterion pattern that proves
  it.

## The identifier scheme

Every edge-case identifier has the form `EC-<SCOPE>-<N>`, where `<SCOPE>` is a short uppercase area tag
**owned by exactly one catalog document**, and `<N>` is a number unique within that scope. No number is
ever reused across scopes, so an identifier is globally unique and a citation is never ambiguous. A
sub-lettered case (for example `EC-PROV-4a`, `EC-PROV-4b`) is a closely related variant of the numbered
case it extends.

| Scope | Owner catalog | Area |
|---|---|---|
| `RUN` | `08-I` §1 | Run lifecycle |
| `TASK` | `08-I` §2 | Task files |
| `PROV` | `08-I` §3 | Providers and clients |
| `SET` | `08-I` §4 | Settings |
| `RES` | `08-I` §5 | Results, charts, exports |
| `LOG` | `08-I` §6 | Logging |
| `WS` | `08-I` §7 | Workspace and Task Editor |
| `PERF` | `08-I` §8 | Performance and concurrency |
| `PERSIST` | `08-I` §9 | Persistence |
| `PLAT` | `08-I` §10 | Platform |
| `IMP` | `10_Domain_and_Data/06_IMPORT_FORMATS.md` | Import validation |
| `EXP` | `10_Domain_and_Data/05_EXPORT_FORMATS.md` | Export formatting |
| `FL` | `10_Domain_and_Data/07_FILE_LAYOUT.md` | File layout / disk |
| `RD` | `10_Domain_and_Data/08_REDACTION_PATTERNS.md` | Redaction |
| `M` | `08_Cross_Cutting/08-M_app_lifecycle.md` | App lifecycle |

The last five scopes (`IMP`, `EXP`, `FL`, `RD`, `M`) are owned by their respective domain documents, not by
`08-I` — do not look for their entries in the `08-I` catalog, and do not invent or guess their exact
section numbers without opening the owning file.

## How the mapping works

Each `EC-` id in `06_EDGE_CASE_TO_TEST_MAPPING.md` resolves to three things:

1. **Test tier(s)** — one of `unit`, `widget`, `integration`, `property`, `architecture`. Some edge cases
   need two tiers (for example a structural guarantee proven by an architecture test *and* a behavioural
   fallback proven by a unit test).

   | Tier | Proves an edge case when… | Mechanism |
   |---|---|---|
   | unit | The behaviour lives inside one module, reachable with that module's logic alone. | Colocated test, often `@pytest.mark.parametrize`. |
   | widget | The behaviour is a UI affordance — a gated control, a banner, a dialog sequence. | A `pytest-qt` test driving a real widget. |
   | integration | The behaviour spans several modules and a real local resource. | A test in `tests/integration/` with a `tmp_path` database and service fakes. |
   | property | The behaviour is a universal property over an open input space. | A Hypothesis property test, `property`-marked. |
   | architecture | The behaviour is a structural guarantee the codebase must hold by construction. | An `import-linter` contract or AST architecture test. |

2. **Proving module** — the module from the module inventory whose `tests/`, or the top-level `tests/`
   subdirectory, holds the test.

3. **Criterion pattern** — Given/When/Then, Table-driven, or Invariant, from the
   `acceptance-criteria-authoring` skill. An edge case whose expected behaviour is itself a status/mode
   table (like `EC-RUN-5`'s resume-by-status table) almost always maps to Pattern B.

When a story cites `EC-RUN-5`, look it up in the mapping table to get: tier(s) `unit; integration`, modules
`backend/benchmark_pipeline/`; `tests/integration/`, pattern `Table-driven` — then write the criterion and
test accordingly.

## Coverage validation: `just trace-check`

The traceability validator (`scripts/validate_traceability.py`, run via `just trace-check` in the
pull-request gate) enforces completeness by reading the **catalogs** as the source of truth, not the
mapping document:

1. Collect `catalog_ids` — every `EC-…` id defined across **all** catalog documents (the ten `08-I` scopes
   plus `IMP`, `EXP`, `FL`, `RD`, `M`).
2. Collect `mapped_ids` — every id with a row in `06_EDGE_CASE_TO_TEST_MAPPING.md`; and `story_ids` — every
   id named in some story's `edge_cases:` front-matter.
3. Fail the gate if either set difference is non-empty:
   - `catalog_ids − mapped_ids` → an **uncovered** edge case (catalogued but missing a mapping row).
   - `mapped_ids − catalog_ids` → a **dangling** mapping row (cites an id no catalog defines).
   - any catalog id absent from `story_ids` and from the test suite → an **untested** edge case.

This is deliberately checked **against the catalogs**, not against a separate hand-maintained total or
against the mapping list itself — an earlier version of the mapping asserted a fixed count and validated
against that count, which was circular and proved nothing about actual catalog coverage. Never add a count
assertion as a substitute for enumerating the catalogs.

## Quick reference: a representative sample of catalogued edge cases

Pulled directly from `08-I_edge_cases.md` so you don't have to open the file for common lookups:

| EC id | One-line description |
|---|---|
| `EC-RUN-1` | Start clicked while a run is already RUNNING is a no-op; the gate is held synchronously so no second pipeline or run record is created. |
| `EC-RUN-1a` | Two admission calls (double-click Start/Resume, or a raced Resume-Summary Confirm) — the first wins the gate atomically, the second is a complete no-op. |
| `EC-RUN-4` | Window closed mid-run prompts a stop-and-quit modal; graceful stop within the timeout marks the run STOPPED, a force-quit leaves it INCOMPLETE for the next-launch orphan sweep. |
| `EC-RUN-5` | Resume of a STOPPED run sets it INCOMPLETE and re-runs rows per a status table; COMPLETED rows (including FAIL verdicts) are left untouched. |
| `EC-PROV-1` | A model that returns 404 at inference time is a non-retryable failure; the row is marked FAILED_INFERENCE and the pipeline advances. |
| `EC-PROV-4` | A `(provider, model, role=INFERENCE)` bucket hitting consecutive max-timeout failures is excluded from the run for INFERENCE only; JUDGE exclusion is independent. |
| `EC-PROV-6` | The env var named by a provider's api-key field being unset/empty leaves the provider enabled but reports MISSING_ENV; starting a run with its models is blocked. |
| `EC-PROV-7` | The credential field accepts only an env-var NAME; a literal secret is rejected inline at entry, with no conversion dialog. |
| `EC-TASK-2` | Two tasks sharing a `task_id` are both flagged as hard errors within one file (Save disabled); across files the loader keeps the first and warns. |
| `EC-RES-2` | The composite `(provider_id, model_name)` is the unit of aggregation everywhere — Summary, Details, all twelve charts, every export; rows are never merged. |
| `EC-PERSIST-1` | A database schema-version mismatch at startup is a hard error (newer/cross-major) or an additive-only forward step (older, same lineage); never a silent mutation. |
| `EC-PERSIST-2` | The startup orphan-run sweep leaves every crash-orphaned run INCOMPLETE with a recovery note, and resets non-terminal result rows to PENDING. |
| `EC-PERF-1` | A background worker mutating UI state directly is forbidden by construction; every cross-thread message passes through the event bus. |
| `EC-PLAT-3` | A monitor disconnect repositions the window onto an available display; geometry that fits no display is clamped on the next launch. |
| `EC-WS-2` | Quitting with dirty editor buffers and a run in progress shows two confirmation modals in sequence; cancelling either aborts the quit entirely. |

## Cross-references

- `docs/v3_specification/14_Process_and_Traceability/03_TRACEABILITY.md` — the validator's place in the pull-request gate.
- `docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md` — the test pyramid and tier mechanics referenced above.
- The `acceptance-criteria-authoring` skill — the three criterion patterns an edge case's proving test follows.
