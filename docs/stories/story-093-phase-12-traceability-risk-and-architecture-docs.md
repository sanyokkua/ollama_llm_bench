---
id: STORY-093
title: Close Phase 12 with per-EC union traceability, a risk-mitigation verification sweep, and the real architecture and data-model docs
status: draft
spec_clauses:
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#1-purpose-and-scope
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#3-risk-summary-matrix
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-013--secret-leakage-through-one-of-the-two-redaction-surfaces-being-bypassed
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#3-the-single-writer-discipline
modules:
  - backend/errors/
  - backend/persistence/app_settings/
acceptance_criteria:
  - STORY-093-AC-1
  - STORY-093-AC-2
  - STORY-093-AC-3
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
  - STORY-090
  - STORY-091
  - STORY-092
adrs: []
owner: coder
estimate: M
---

# STORY-093 — Close Phase 12 with per-EC union traceability, a risk-mitigation verification sweep, and the real architecture and data-model docs

## Goal

Bring the traceability and quality record to a clean, verifiable close so `just trace-check` exits
with zero failures repo-wide. Three deliverables: fix the traceability generator so each edge case's
proving tests are computed as the union across every story that claims it (a defect recorded in
STORY-074's notes); run a risk-mitigation verification sweep confirming every risk in the register
has its stated mitigation present or explicitly waived; and replace the placeholder architecture and
data-model documents with real ones describing the built system.

## In scope

- Fixing `scripts/trace.py`'s edge-case map so a given `EC-` id resolves to the **union** of proving
  tests across all stories that claim it, rather than every claiming story's full test set being
  attributed to each of its edge cases (STORY-074 Notes item 6), and confirming `just trace-check`
  reports zero failures repo-wide afterward.
- A risk-mitigation verification sweep against the risk register: for each of the 16 risks, confirm
  its stated mitigation is verifiably present (a test, an architecture check, or a documented
  waiver), spot-check not exhaustive, with the two-surface redaction boundary (R-013) confirmed by a
  property/fuzz test and the single-writer / crash-recovery data-integrity guarantees (R-006, R-007)
  confirmed present.
- Writing the real `docs/architecture.md` and `docs/data-model.md`, replacing the Phase-0 stubs, per
  the repository-documentation docs tree.

## Out of scope

- Re-authoring or changing any prior story's acceptance criteria or tests; this story fixes the
  generator and adds the risk-sweep verification, it does not restate earlier coverage.
- Editing the vendored specification or the risk register itself — the sweep verifies mitigations
  against the register, it does not alter it.
- The per-layer coverage gate and the accessibility-floor verification — owned by
  `just coverage-layers` and STORY-091 respectively; this story does not re-implement them.

## Spec inputs

- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#1-purpose-and-scope` — the edge-case
  to-test mapping the generator must reflect accurately; each edge case maps to its own proving
  test(s), which is what the per-EC union fix restores.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#3-risk-summary-matrix` — the authoritative list of
  the 16 risks whose mitigations the sweep verifies present or waived.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-013--secret-leakage-through-one-of-the-two-redaction-surfaces-being-bypassed`
  — R-013's mitigation: every provider adapter wraps SDK exceptions through `redact`, the `app.*`
  namespace has the `redact_for_log` processor, and the redaction module is fuzzed so no denylist
  pattern survives; the sweep confirms this with a property/fuzz test in `backend/errors/`.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#3-the-single-writer-discipline` — the single-writer
  discipline (R-006, R-007): one locked writer connection with `BEGIN IMMEDIATE`, which the sweep
  confirms present in `backend/persistence/app_settings/`.

## Design constraints

- `scripts/trace.py` is deterministic: after the per-EC union fix, re-running the generator must
  produce a byte-identical `traceability.yaml`, so the "record fresh" check stays green.
- The redaction fuzz test is a property (`Hypothesis`) test in `backend/errors/`; the data-integrity
  checks run against a real `tmp_path` SQLite database, never in-memory.
- `docs/architecture.md` and `docs/data-model.md` follow the repository-documentation writing
  standards (imperative mood, real module paths, Mermaid for diagrams) and cite the spec as the
  authority rather than duplicating it.

## Acceptance criteria

### STORY-093-AC-1

Given the fixed traceability generator, when `just trace` regenerates the record and `just trace-check` runs, then each `EC-` id lists exactly the union of its own claiming stories' proving
tests, and `just trace-check` reports zero failures repo-wide.

### STORY-093-AC-2

Given the 16 risks in the risk register, when the risk-mitigation verification sweep runs, then each
risk's stated mitigation is confirmed present (or explicitly waived), including a passing
property/fuzz test proving no denylist pattern survives either redaction surface (R-013).

### STORY-093-AC-3

Given the Phase-0 documentation stubs, when Phase 12 closes, then `docs/architecture.md` and
`docs/data-model.md` exist and describe the built three-layer architecture and the persistence data
model, replacing the stubs.

## Test plan

- STORY-093-AC-1 — integration, `tests/integration/test_traceability_per_ec_union.py`,
  `test_edge_case_map_unions_only_its_own_claiming_stories_tests`.
- STORY-093-AC-2 — property (`Hypothesis`), colocated
  `src/ollama_llm_bench/backend/errors/tests/test_redaction_fuzz.py`,
  `test_no_denylist_pattern_survives_either_redaction_surface`; plus a risk-sweep checklist recorded
  in the story Notes for the non-code mitigations.
- STORY-093-AC-3 — integration (docs-presence), `tests/integration/test_docs_present.py`,
  `test_architecture_and_data_model_docs_exist_and_are_not_stubs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-093.
- [ ] `just trace-check` exits 0 with zero gaps repo-wide.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
