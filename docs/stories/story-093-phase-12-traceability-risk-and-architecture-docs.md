---
id: STORY-093
title: Close Phase 12 with per-edge-case test attribution, an auditable risk-mitigation sweep, and the real architecture and data-model docs
status: done
spec_clauses:
  - 14_Process_and_Traceability/03_TRACEABILITY.md#4-generating-the-record
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#1-purpose-and-scope
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#3-risk-summary-matrix
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-013--secret-leakage-through-one-of-the-two-redaction-surfaces-being-bypassed
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-006--long-running-batched-pipeline-holding-partial-results
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-007--sqlite-wal-corruption-and-crash-recovery
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#3-the-single-writer-discipline
  - 12_Quality_and_NFRs/04_ERROR_RECOVERY.md#4-the-result-row-recovery-sweep
modules:
  - backend/errors/
  - backend/persistence/results/
acceptance_criteria:
  - STORY-093-AC-1
  - STORY-093-AC-2
  - STORY-093-AC-3
  - STORY-093-AC-4
  - STORY-093-AC-5
edge_cases: []
depends_on:
  - STORY-076
  - STORY-077
  - STORY-078
  - STORY-079
  - STORY-080
  - STORY-081
  - STORY-082
  - STORY-083
  - STORY-084
  - STORY-085
  - STORY-086
  - STORY-087
  - STORY-088
  - STORY-089
  - STORY-091
  - STORY-092
  - STORY-114
adrs: []
owner: coder
estimate: M
---

# STORY-093 — Close Phase 12 with per-edge-case test attribution, an auditable risk-mitigation sweep, and the real architecture and data-model docs

## Goal

**Unblocked on 2026-08-20.** This is the phase closer and is picked up last, so it stayed `draft`
until every story in its `depends_on` list was resolved. That condition now holds. Sixteen of the
seventeen are `done`; the seventeenth, STORY-082, is `superseded` by STORY-101 in the
circuit-breaker probe remediation, which counts as resolved rather than outstanding — the same
reading the already-`done` STORY-030 and STORY-075 rely on, since both depend on STORY-023, also
superseded by STORY-101. STORY-092 was the last dependency still open, and it closed on
2026-08-20.

Bring the project's own quality record to a state where it can be trusted. Three things are wrong
today. The traceability generator credits every edge case a story claims with every test that story
has, so an edge case can read as "proven" by a test that has nothing to do with it. The risk
register's mitigations have never been checked off against anything concrete. And the architecture
documentation is still the Phase-0 stub that says the real documentation does not exist yet. This
story fixes the attribution, produces a risk checklist where every row points at a real artifact,
and writes the architecture and data-model documents for the system that was actually built.

## In scope

- **A way for a test to say which edge case it proves.** Extend the existing docstring-declaration
  convention: alongside the mandatory first-line `Proves: STORY-NNN-AC-N`, a test may declare
  `Covers: EC-<SCOPE>-<n>` (one or more, comma-separated) on a later line of the same docstring.
  Add the matching regex and `CollectedTest` field in `scripts/_traceability_lib.py`, and build a
  `covers_index` in `scripts/trace.py` exactly the way `proves_index` is built today.
- **Fixing the edge-case map to use it.** `scripts/trace.py`'s `_build_edge_cases_map` currently
  attributes *every* acceptance criterion of a claiming story to *every* edge case that story
  names — a cross product, not a mapping. Replace that with the `covers_index` lookup, keeping a
  fallback (below) so no currently-covered edge case regresses.
- **A risk-mitigation verification checklist** covering all sixteen rows of the risk summary matrix,
  where each row names the concrete artifact that verifies it.
- **A property test for the two redaction surfaces (R-013)** — the one risk mitigation the register
  names that has no proving test today.
- **The real architecture documentation**: rewrite `docs/architecture/README.md` and add
  `docs/architecture/data-model.md`, replacing the Phase-0 stub.

## Out of scope

- Migrating the roughly 101 existing `edge_cases:` claims across 41 stories to carry `Covers:`
  declarations. That is deliberately left as incremental work each future story does for its own
  edge cases; see the fallback in AC-2, which is what makes the migration incremental instead of a
  single unshippable change.
- Re-authoring or changing any prior story's acceptance criteria or tests. This story fixes the
  generator and adds the risk sweep; it does not restate earlier coverage.
- Editing the vendored specification or the risk register. The sweep verifies mitigations *against*
  the register; it never alters it.
- The per-layer coverage gate and the accessibility-floor verification — owned by
  `just coverage-layers` and STORY-091 respectively.
- Any change to the `Proves:` convention itself. It stays exactly as it is: the first docstring
  line, one acceptance-criterion id.

## Spec inputs

- `14_Process_and_Traceability/03_TRACEABILITY.md#4-generating-the-record` — the three-pass
  generation algorithm and the existing declaration convention: `pytest --collect-only` is run, each
  test's docstring is read, and a test that proves an acceptance criterion declares it on the
  docstring's first line in the fixed form `Proves: STORY-NNN-AC-N`. The `Covers:` line this story
  adds follows the same shape rather than inventing a second mechanism.
- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#1-purpose-and-scope` — each `EC-`
  identifier maps to its *own* proving test in a named tier and a named module; the record must
  reflect that mapping, which is precisely what the cross product destroys.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#3-risk-summary-matrix` — the sixteen rows R-001
  through R-016 whose mitigations the sweep verifies. R-001 is marked retired and superseded by
  R-016; the checklist records that disposition rather than silently skipping the row.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-013--secret-leakage-through-one-of-the-two-redaction-surfaces-being-bypassed`
  — R-013's stated mitigation: every provider adapter wraps SDK exceptions through `redact`, the
  `app.*` namespace carries the `redact_for_log` processor, and the redaction module is fuzzed so no
  denylist pattern survives. The fuzz half does not exist yet.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-006--long-running-batched-pipeline-holding-partial-results`
  — R-006's mitigation: results are persisted incrementally so a long run never holds partial state
  only in memory.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-007--sqlite-wal-corruption-and-crash-recovery`
  — R-007's mitigation: WAL journalling plus the startup recovery sweep.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#3-the-single-writer-discipline` — exactly one locked
  write connection using `BEGIN IMMEDIATE`; the sweep confirms this is what the code does.
- `12_Quality_and_NFRs/04_ERROR_RECOVERY.md#4-the-result-row-recovery-sweep` — the result-row
  recovery sweep run at startup, owned by `backend/persistence/results/`, which is the concrete
  artifact the checklist cites for R-006 and R-007.

## Design constraints

- `scripts/trace.py` must stay deterministic: after the change, re-running the generator produces a
  byte-identical `traceability.yaml`, so the "record fresh" check stays green. Keep the sorted-key,
  sorted-list discipline the existing builders use.
- The `Covers:` declaration is **additive and optional**. A test that declares no `Covers:` line
  keeps working exactly as before; nothing in the existing suite has to change for the record to
  regenerate cleanly.
- **The fallback is the reason this story is shippable.** Around 101 edge-case claims are spread
  across 41 story files. Requiring every one of their proving tests to carry a `Covers:` line before
  the change lands would make this a multi-session change touching a hundred test functions, and
  would turn `just trace-check` red until all of it was finished. Instead, an edge case that no test
  declares keeps today's attribution, and each future story tightens its own edge cases as it
  touches them.
- The redaction property test is a Hypothesis test colocated in `backend/errors/`, marked
  `property`, and exercises **both** surfaces named in R-013 — `redact()` and the `redact_for_log`
  structlog processor. It must not assert against the `run.*` stream, which is deliberately
  un-redacted apart from the chained SDK-exception detail.
- The data-integrity checks named in the sweep run against a real `tmp_path` SQLite database, never
  an in-memory one, matching how `backend/persistence/results/` is already tested.
- `scripts/` is not on pytest's `pythonpath` (which is `["src"]`), so a test importing the
  traceability helpers must either insert the repository's `scripts/` directory into `sys.path` or
  extend `pythonpath` to `["src", "scripts"]` in `[tool.pytest.ini_options]`. Either is acceptable;
  pick one and do not leave it to a late guess.
- `docs/architecture/README.md` and `docs/architecture/data-model.md` follow the repository
  documentation standards — imperative mood, real module paths, Mermaid for diagrams, a language tag
  on every fenced block — and cite the specification as the authority rather than duplicating it.

## Acceptance criteria

### STORY-093-AC-1

Given a story that names two edge cases and has three acceptance-criteria tests, and exactly one of
those tests declares `Covers:` naming exactly one of the two edge cases, when the traceability
record is generated, then that edge case lists only that one test — not the story's other two
acceptance-criteria tests.

### STORY-093-AC-2

Given an edge case that no test anywhere declares with a `Covers:` line, when the traceability
record is generated, then that edge case lists the union of its claiming stories'
acceptance-criteria tests, exactly as it did before this change.

### STORY-093-AC-3

Given the sixteen rows R-001 through R-016 of the risk summary matrix, when the risk-mitigation
verification checklist is read, then every row names the concrete artifact that verifies its
mitigation — a `path/to/file.py:LINE` reference, a test function name, or a named CI workflow
step — or carries an explicitly written waiver stating why no artifact exists. No row is verified by
prose alone, and R-001 is recorded as retired and superseded by R-016.

### STORY-093-AC-4

For every log record and every exception message containing a value drawn from the secret denylist,
neither redaction surface emits output in which any denylist pattern survives: `redact()` applied at
the adapter boundary, and the `redact_for_log` processor applied to the `app.*` stream.

### STORY-093-AC-5

Given the Phase-0 architecture stub, when Phase 12 closes, then `docs/architecture/README.md` and
`docs/architecture/data-model.md` both exist, describe respectively the built three-layer
architecture and the persistence data model, and neither contains the stub's placeholder sentence
beginning "Until that documentation exists".

## Test plan

- STORY-093-AC-1 — unit, `tests/unit/test_traceability_edge_case_map.py`,
  `test_edge_case_lists_only_the_test_that_declares_it`. Builds two synthetic `Story` records and a
  synthetic proves/covers index in memory and calls the record builder directly; runs no
  subprocess and reads no real story file.
- STORY-093-AC-2 — unit, same file,
  `test_edge_case_without_a_covers_declaration_keeps_the_legacy_attribution`.
- STORY-093-AC-3 — integration (checklist content presence),
  `tests/integration/test_risk_mitigation_checklist.py`,
  `test_every_risk_row_names_a_concrete_artifact_or_a_waiver`. Reads the checklist document written
  by this story, asserts one row per risk id R-001 through R-016, and asserts each row's evidence
  cell matches a `file:line`, a `test_*` function name, or an explicit waiver marker. The checklist
  itself lives at `docs/development/risk_mitigation_checklist.md`, beside the mockup-conformance
  review already kept there.
- STORY-093-AC-4 — property (Hypothesis, `property`-marked), colocated
  `src/ollama_llm_bench/backend/errors/tests/test_redaction_fuzz.py`,
  `test_no_denylist_pattern_survives_either_redaction_surface`.
- STORY-093-AC-5 — integration (documentation presence),
  `tests/integration/test_architecture_docs_present.py`,
  `test_architecture_readme_and_data_model_exist_and_are_not_stubs`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-093.
- [x] `just trace` regenerates a byte-identical record on a second run, and `just trace-check` exits
  0 with zero gaps repo-wide.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules and for `scripts/`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
- [x] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [x] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-116** — bring the Task Editor edge-case catalog under the traceability gate, so the fifteen
  `EC-TE-` identifiers the specification defines are finally checked by `just trace-check` instead of
  being invisible to it. **STORY-093 is its only `depends_on` entry**, so completing this story
  satisfies its dependency condition immediately. It once carried a second, non-dependency blocker —
  it needs fifteen rows added to `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`, which
  is inside the read-only specification tree — but **the product owner granted that sanction on
  2026-08-05**, covering both the mapping rows and the three index corrections, and it is recorded in
  STORY-116's Notes. **Flip it `draft` → `ready` unconditionally when this story is `done`.**

**What to do on completion**

1. Flip STORY-116 `draft` → `ready`. This story is its only dependency and its specification sanction
   is already granted, so no further condition applies.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so flipping this
   story to `done` makes it stale — then `just trace-check`.
1. **Propose the recorded gaps as the next work**, ranked, in the closing report — STORY-116 is the
   one immediately actionable successor, and it is small, so name what follows it too. Two bodies of
   un-storied work are already recorded and need stories written for them:
   1. **The five permanent no-op stubs in `src/ollama_llm_bench/_compose_shims.py`**, disclosed in
      STORY-077's notes as "a future story's job" with no such story ever written. They are live
      behaviour gaps, not dead code: `_NoRunValidator` means Start-time validation always reports no
      problems, `_NoModelFetcher` means the Generate-Analysis model picker always shows an empty
      list, `_AlwaysOkRunLogWriteStatus` means a log-write failure never surfaces to the user, plus
      `_NoOpManualProviderProbeCommand` and `_NoActiveRunTaskPaths`.
   1. **The roughly 29 mockup-conformance defects from STORY-087**, recorded in
      `docs/development/mockup_conformance_review.md`. Rank the two most serious first: the Run
      Summary dialog prints raw internal provider UUIDs where a provider name belongs
      (`ui/common_dialogs/_internal/view_model_select.py:48,81,91`) on the confirmation shown just
      before a run starts, violating the rule that those ids are never user-visible; and 19 of the
      22 styling roles the widget code sets have no stylesheet rule, so those controls fall back to
      default Qt appearance instead of the mockups'.

## Notes

- **The defect AC-1 fixes, precisely.** `scripts/trace.py` lines 70–86 (`_build_edge_cases_map`)
  loop over each story's edge cases and, for each one, union in the proving tests of *every*
  acceptance criterion that story has:
  `for ec_id in story.edge_cases: for ac_id in story.acceptance_criteria: ec_to_tests[ec_id].update(...)`.
  A story with four acceptance criteria and three edge cases therefore records all four tests
  against all three edge cases. The union *across* claiming stories is already correct; the defect
  is entirely the inner cross product within one story. This was recorded as item 6 of STORY-074's
  notes.
- **Why `Covers:` and not a pytest marker.** The generator learns about tests through
  `pytest --collect-only -q`, whose output is node ids only — it carries no marker information — and
  then reads each node's docstring from source with `ast`. A marker would require a second
  collection mechanism; a docstring line reuses the machinery that already reads `Proves:`. This is
  a build-tooling convention rather than an application-architecture decision, so it is recorded
  here rather than in an ADR.
- **AC-1 and AC-5 have no module owner.** AC-1 changes `scripts/`, and AC-5 writes Markdown under
  `docs/architecture/` — neither is a module in `01_MODULE_INVENTORY.md`. Every story must cite at
  least one inventory module, so `modules:` cites the two modules AC-3 and AC-4 genuinely verify:
  `backend/errors/` (the two redaction surfaces R-013 names) and `backend/persistence/results/`
  (the module the inventory records as owning the `recover_in_flight_results` startup sweep, which
  is the artifact the checklist cites for R-006 and R-007). This mirrors the disclosure
  STORY-094/095/096 make for their own non-`src` deliverables.
- **`backend/persistence/app_settings/` was the wrong module to cite** and has been replaced. It
  owns the `app_settings` and `app_meta` tables; the crash-recovery sweep R-006 and R-007 turn on
  belongs to `backend/persistence/results/`.
- **STORY-082 stays in `depends_on` even though it is `superseded`.** A superseded dependency counts
  as satisfied — the precedent is the `done` STORY-030 and STORY-075, each of which depends on a
  superseded story. STORY-090 has been removed from this list because it is superseded by ADR-0018
  with no replacement work; STORY-114 has been added because it delivers the Task Editor's
  quit-confirmation wiring, which is part of the same phase this story closes.
- **STORY-115 and STORY-116 are deliberately *not* in `depends_on`.** Both are newly discovered work
  found after this story was written, not part of the Phase-12 closeout scope. STORY-116 in
  particular depends on this story *and* is blocked on a product-owner decision about the read-only
  specification, so adding it here would deadlock this story behind a decision it does not control.
- **Fourteen of the sixteen risk rows were previously "verified" by prose.** AC-3 now requires a
  named artifact per row, which is what makes the sweep auditable by someone who was not present
  when it was done.
