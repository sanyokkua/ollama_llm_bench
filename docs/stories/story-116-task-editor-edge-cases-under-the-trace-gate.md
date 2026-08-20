---
id: STORY-116
title: Bring the Task Editor edge-case catalog under the traceability gate
status: done
spec_clauses:
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#19-coverage-summary
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#191-the-traceability-validator-validate_traceabilitypy
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#10-mapping--workspace-and-task-editor
  - 14_Process_and_Traceability/03_TRACEABILITY.md#5-validating-the-record
  - 09_Task_Editor/description.md#9-edge-cases
modules:
  - ui/task_editor/
acceptance_criteria:
  - STORY-116-AC-1
  - STORY-116-AC-2
  - STORY-116-AC-3
edge_cases: []
depends_on:
  - STORY-093
adrs: []
owner: coder
estimate: S
---

# STORY-116 — Bring the Task Editor edge-case catalog under the traceability gate

## Goal

**Unblocked on 2026-08-20.** STORY-093 — its only `depends_on` entry — closed on that date, so this story is now `ready`. The specification addition this story needs
is already sanctioned — see below — so `depends_on` is now the only thing holding it.

**The specification edit is approved.** On 2026-08-05 the product owner sanctioned **both** halves
of the request in Notes: the fifteen mapping rows **and** the three index corrections that admit
`EC-TE-*` as a scope. This is the second such sanctioned correction, after the 2026-07-22 precedent.
No behavioural clause changes — every added row restates what `09_Task_Editor/description.md` §9
already defines.

Why the edit is unavoidable: `scripts/validate_traceability.py` fails the build for *every*
edge-case identifier that a catalog defines but the mapping document does not list, and it does so
unconditionally (lines 104-105). The moment the Task Editor catalog is registered, all fifteen of
its identifiers — `EC-TE-01` through `EC-TE-15` — have no row in
`14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`, so all fifteen fail at once.

**Land the two halves in the same commit.** The failure is symmetric: adding the mapping rows
*without* registering the catalog makes each new row a dangling row (`mapped_ids - catalog_ids`,
line 102-103) and turns the gate red just as surely as the reverse. Never stage one half on its own.

What the story fixes, once unblocked: the fifteen Task Editor edge cases the specification defines —
a task file that is malformed YAML, two tasks sharing a `task_id`, a file that changed on disk while
open, saving a file a running benchmark is reading, and eleven more — are invisible to
`just trace-check` today. Nothing checks that any of them is mapped, claimed by a story, or proven by
a test. STORY-114 states in its Definition of done that `EC-TE-11` has a passing test; that checkbox
is verified by a human reading the test, because the gate cannot see the identifier at all. This
story makes the gate see the whole family.

## In scope

- **Registering the catalog.** Add `09_Task_Editor/description.md` to
  `scripts/_traceability_lib.py`'s `EDGE_CASE_CATALOGS` list (line 28), which today names six catalog
  documents and omits it. The existing `scan_catalog_ids` already recognises the pipe-table-row form
  the Task Editor's §9 table uses, so no parsing change is needed.
- **The fifteen mapping rows.** `EC-TE-01` through `EC-TE-15` each get a row in
  `06_EDGE_CASE_TO_TEST_MAPPING.md` §10 ("Mapping — Workspace and Task Editor", already the home of
  the four `EC-WS-` rows), following that document's four-column shape: behaviour under test, tier,
  proving module, criterion pattern. Each row restates its `09_Task_Editor/description.md` §9 catalog
  entry in intent — it adds no new behaviour and changes no existing clause.
- **Admitting `EC-TE-*` as a scope.** §19's group/owner index table lists six scopes and their owning
  catalogs and does not mention the Task Editor; a `Task Editor (TE) → 09_Task_Editor/description.md`
  row is added so the specification's own index agrees with what the validator now enumerates.
- **Per-identifier attribution using STORY-093's mechanism.** Where a row's identifier is claimed by
  a story, the proving test declares it with the `Covers: EC-<SCOPE>-<n>` docstring line STORY-093
  introduces — this story adds no second attribution mechanism.

## Out of scope

- **Writing fourteen new tests.** Only an identifier that some story names in its `edge_cases:`
  front-matter needs a proving test: `validate_traceability.py` lines 106-108 skip any catalog id
  absent from `story_ec_ids` with the comment "not yet claimed by any story — partial coverage, not a
  failure", which is the deliberate tolerance `03_TRACEABILITY.md` §7 describes for construction-time
  partial coverage. Today exactly one `EC-TE-` id is claimed — `EC-TE-11`, by STORY-114 — and
  STORY-114 already plans its proving test. The deliverable here is fifteen mapping rows, not fifteen
  tests.
- **Claiming the other fourteen identifiers for any story.** Deciding which story owns `EC-TE-06`
  (a file changed on disk while open) or `EC-TE-10` (a save failed from disk full or permission
  denied) is real product work with real behaviour behind it; STORY-114's notes already record
  `EC-TE-10` as genuinely unowned. This story deliberately leaves those claims for the stories that
  implement the behaviour.
- **Any change to the Task Editor's behaviour, widgets, or controller.** `ui/task_editor/` is cited
  as the module the `EC-TE-` identifiers describe; no file under `src/ollama_llm_bench/ui/task_editor/`
  is edited.
- **Changing `02_STORY_FORMAT.md`'s `edge_cases` field rule.** Its §5 field table enumerates the
  scoped catalogs as `EC-IMP-*`, `EC-EXP-*`, `EC-FL-*`, `EC-RD-*`, `EC-M-*` and likewise omits
  `EC-TE-*`. The identifier still validates — `trace.py`'s regex is `EC-[A-Z]+-\d+[a-f]?`, which
  accepts `EC-TE-11` — so nothing is broken by leaving it. It is recorded in Notes as a fourth place
  the owner may want to include in the same sanction, not silently changed here.
- **The `Covers:` mechanism itself** — delivered by STORY-093, consumed here.

## Spec inputs

- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#19-coverage-summary` — "This mapping
  must contain a row for **every** edge case defined in **every** catalog", "one row per catalogued
  identifier across all scopes", plus the group/owner index table that names the six scopes admitted
  today. The Task Editor is absent from that table, which is why the omission is a specification gap
  and not merely a script bug.
- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#191-the-traceability-validator-validate_traceabilitypy`
  — the three-step algorithm the scripts implement: collect `catalog_ids` from the catalogs, collect
  `mapped_ids` from this mapping and `story_ids` from story front-matter, and fail on either set
  difference. This is the clause that makes "register the catalog" and "add the fifteen rows"
  inseparable: doing the first without the second is guaranteed to turn the gate red.
- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#10-mapping--workspace-and-task-editor`
  — the section the fifteen rows belong in, and the column shape they must follow. It already holds
  `EC-WS-1` through `EC-WS-4`, two of which (`EC-WS-3`, `EC-WS-4`) name `ui/task_editor/` as the
  proving module, so the section is the established home for this material.
- `14_Process_and_Traceability/03_TRACEABILITY.md#5-validating-the-record` — the gate's check table.
  Its "Edge-case covered" row enumerates the scoped catalogs as import, export, file layout,
  redaction, and lifecycle, and does not include the Task Editor — a second place the specification
  itself defines the family out of the gate.
- `09_Task_Editor/description.md#9-edge-cases` — the catalog: a fifteen-row table defining `EC-TE-01`
  through `EC-TE-15`, each with a scenario and its required handling. This is the source the mapping
  rows restate.

## Design constraints

- **The two halves must land together, in one change.** Registering the catalog without the mapping
  rows turns `just trace-check` red with fifteen failures; adding the mapping rows without
  registering the catalog turns it red with fifteen *dangling row* failures (`mapped_ids − catalog_ids`, checked at lines 102-103). Neither half is independently shippable.
- **The mapping rows restate; they never legislate.** Each row's "behaviour under test" cell is a
  faithful short restatement of its `09_Task_Editor/description.md` §9 entry. No row may introduce a
  behaviour, a threshold, or a message the catalog does not already state — that would be authoring
  specification under cover of a bookkeeping fix.
- **`scripts/trace.py` must stay deterministic.** After the change, re-running the generator produces
  a byte-identical `traceability.yaml`, so the "record fresh" check stays green. `EDGE_CASE_CATALOGS`
  is iterated into a set, so list position does not affect output; keep the list in the same
  document-path ordering it already uses.
- **Per-identifier attribution uses STORY-093's `Covers:` docstring line**, not a pytest marker and
  not a second convention. STORY-093's AC-1 delivers exactly this: a test declaring
  `Covers: EC-<SCOPE>-<n>` on a later line of the same docstring that carries `Proves:`, with a
  fallback that leaves an undeclared edge case on its previous attribution. That fallback is what
  keeps this story small.
- `scripts/` is not on pytest's `pythonpath` (which is `["src"]`), so a test importing the
  traceability helpers must either insert the repository's `scripts/` directory into `sys.path` or
  extend `pythonpath` to `["src", "scripts"]`. STORY-093 faces the identical constraint and picks
  one; reuse whatever it chose rather than introducing a second approach.

## Acceptance criteria

### STORY-116-AC-1

Given the traceability library's catalog list, when the edge-case catalogs are scanned, then the set
of identifiers found includes exactly the fifteen `EC-TE-01` through `EC-TE-15` defined in
`09_Task_Editor/description.md` §9 — no more and no fewer.

### STORY-116-AC-2

Given the registered Task Editor catalog and the extended mapping document, when the traceability
validator's edge-case check runs, then it reports no "defined in a catalog but has no row in the
mapping" failure and no "dangling row" failure for any `EC-TE-` identifier.

### STORY-116-AC-3

The validator demands a proving test for a Task Editor identifier only when a story claims it:

| `EC-TE-` identifier                        | Named in some story's `edge_cases:` | Validator outcome                                                     |
| ------------------------------------------ | ----------------------------------- | --------------------------------------------------------------------- |
| `EC-TE-11`                                 | yes — STORY-114                     | requires a proving test, and finds STORY-114's                        |
| the other fourteen (`EC-TE-01`…`EC-TE-15`) | no                                  | reported as neither uncovered nor untested — partial coverage is fine |

## Test plan

- STORY-116-AC-1 — unit, `tests/unit/test_traceability_task_editor_catalog.py`,
  `test_task_editor_catalog_contributes_its_fifteen_ids`. Calls `load_all_catalog_ids()` and asserts
  the `EC-TE-`-prefixed subset equals the fifteen ids parsed independently from
  `09_Task_Editor/description.md` §9, so the test cannot pass by hard-coding the same list twice.
- STORY-116-AC-2 — integration, `tests/integration/test_traceability_gate_covers_task_editor.py`,
  `test_no_task_editor_id_is_unmapped_or_dangling`. Runs the validator's `check_edge_cases_covered`
  against the real catalogs, mapping, and stories, and asserts no returned failure string mentions an
  `EC-TE-` identifier for either the unmapped or the dangling condition.
- STORY-116-AC-3 — integration, table-driven `@pytest.mark.parametrize` with one case per row and no
  loop in the test body, same file, `test_proving_test_is_demanded_only_for_a_claimed_id`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-116.
- [x] The product owner's sanction for the specification addition is recorded in this story's Notes,
  with a date, before any edit to `docs/v3_specification/` is made. **Granted 2026-08-05**, covering
  the fifteen mapping rows and the three index corrections.
- [x] The catalog registration and the mapping rows land in the **same** commit — either half alone
  turns `just trace-check` red.
- [x] `just trace` regenerates a byte-identical record on a second run, and `just trace-check` exits
  0 with zero gaps repo-wide.
- [x] `mypy --strict` and `ruff` pass for `scripts/`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
- [x] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [x] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

Nothing. No story's `depends_on` names STORY-116, so finishing it makes no `draft` → `ready` flip
available and the flip checkbox above is satisfied vacuously — say so explicitly in the closing
report rather than leaving it ambiguous.

**What to do on completion**

1. There is no successor story to flip; confirm that in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so flipping this story
   to `done` makes it stale — then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural successors are stories that *claim* the newly visible identifiers, because the gate
   can finally hold them to it. Rank `EC-TE-10` first — a save that fails from disk full, permission
   denied, or a removed directory, which STORY-114's notes record as genuinely unowned and which
   silently loses a user's edits — then `EC-TE-06` (a task file changed on disk while open) and
   `EC-TE-09` (reloading a file with unsaved edits), both of which have partial implementations from
   STORY-112 but no owning edge-case claim.

## Notes

- **The blocker, in plain terms.** `scripts/validate_traceability.py` contains, unconditionally:

  ```python
  for ec_id in sorted(catalog_ids - mapped_ids):
      failures.append(f"{ec_id} is defined in a catalog but has no row in the mapping")
  ```

  `catalog_ids` comes from the documents listed in `scripts/_traceability_lib.py`'s
  `EDGE_CASE_CATALOGS`; `mapped_ids` comes from
  `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`, which contains zero `EC-TE-` rows.
  Add the Task Editor catalog and all fifteen identifiers land in `catalog_ids - mapped_ids` on the
  next `just trace-check`. The mapping document is inside the read-only specification tree, so
  clearing them requires an owner-sanctioned edit to it. **That sanction was granted on 2026-08-05**
  and covers both the fifteen mapping rows and the three index corrections listed below, so this
  story is no longer decision-blocked — only STORY-093 remains.

- **The two halves are symmetric, and neither may land alone.** Registering the catalog without the
  rows fails on `catalog_ids - mapped_ids` (lines 104-105); adding the rows without registering the
  catalog fails on `mapped_ids - catalog_ids` (lines 102-103, "dangling row"). Both directions turn
  `just trace-check` red, so the script change and the specification rows belong in one commit.

- **There is a precedent, and this is the same shape of request.** On 2026-07-22 the project owner
  explicitly sanctioned a one-time correction to the vendored specification's own traceability
  tables — recorded in STORY-074's notes as "the sole exception ever made to the read-only-spec
  rule". That correction added an `EC-RUN-1a` row and an `EC-PROV-1a` row to
  `06_EDGE_CASE_TO_TEST_MAPPING.md` §4/§6, and an `EC-PERSIST-6` entry to `08-I_edge_cases.md` §9,
  each restating an existing catalog entry verbatim in intent. No behavioural clause was touched; the
  correction reconciled the specification's internal bookkeeping with itself. The request here is
  identical in kind and larger only in count.

- **Four places the specification currently defines `EC-TE-*` out of the gate**, so the owner can
  decide the scope of the sanction in one pass:

  1. `06_EDGE_CASE_TO_TEST_MAPPING.md` §10 — no `EC-TE-` rows (the fifteen this story adds).
  1. `06_EDGE_CASE_TO_TEST_MAPPING.md` §19 — the group/owner index table lists six scopes and not the
     Task Editor.
  1. `03_TRACEABILITY.md` §5 — the "Edge-case covered" check row enumerates the scoped catalogs and
     omits the Task Editor.
  1. `02_STORY_FORMAT.md` §5 — the `edge_cases` field rule enumerates the scoped catalogs and omits
     `EC-TE-*`. This one is cosmetic: the identifier regex already accepts `EC-TE-11`, which is why
     STORY-114's front-matter validates today.

- **`ui/task_editor/` is cited but not edited.** The deliverable is a change under `scripts/` plus
  Markdown rows in the specification; neither is a module in `01_MODULE_INVENTORY.md`, and every
  story must cite at least one inventory module. `modules:` therefore cites `ui/task_editor/` — the
  module whose behaviour every `EC-TE-` identifier describes, and the module
  `06_EDGE_CASE_TO_TEST_MAPPING.md` §10 already names as the proving module for two of its existing
  rows. This mirrors the disclosure STORY-093, STORY-094, STORY-095, and STORY-096 each make for
  their own non-`src` deliverables.

- **`edge_cases:` is deliberately empty.** This story fixes the *gate*; it discharges no edge case.
  Claiming an `EC-TE-` identifier here would record coverage for Task Editor behaviour that this
  story neither implements nor tests.

- **STORY-114 must also be `done` before this lands, and it will be.** Once the catalog is
  registered, `EC-TE-11` becomes a claimed identifier (STORY-114 names it in its `edge_cases:`
  front-matter, not only in its Definition of done), so the validator will demand a proving test for
  it — and that test is STORY-114's to write. No extra `depends_on` entry is needed: STORY-093, this
  story's only declared dependency, itself depends on STORY-114, so STORY-114 is necessarily `done`
  before STORY-093 is, and therefore before this story can become `ready`.
