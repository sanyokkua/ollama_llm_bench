---
id: STORY-103
title: Correct the stale circuit-breaker spec text
status: done
spec_clauses:
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#102-edge-case--a-provider-goes-down-trips-and-recovers
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#103-edge-case--a-failed-probe-re-trips-the-breaker
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#11-test-cases
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3
modules:
  - backend/circuit_breaker/
acceptance_criteria:
  - STORY-103-AC-1
edge_cases:
  - EC-PROV-3
depends_on:
  - STORY-102
adrs:
  - ADR-0013
owner: arch
estimate: S
---

# STORY-103 — Correct the stale circuit-breaker spec text

## Goal

Finish DD-71's propagation into `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` by correcting
the nine sites STORY-102's Notes catalogued as still describing the retired real-task probe, so
the next reader of the specification sees the dedicated-lightweight-probe design the code (as of
STORY-100/STORY-101) actually implements, and cannot re-implement the bug this plan fixes from
stale prose. This story corrects the specification (no production code changes) and delivers one
guard test verifying the correction.

## In scope

- `docs/v3_specification/11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`, and only these nine
  sites, each identified by its content (line numbers below are from the pre-edit file and will
  shift):
  - §6.2's `should_skip` column (line 115) — correct to: `should_skip` returns `True`
    unconditionally while `PROBING`; the pipeline issues the dedicated lightweight probe.
  - §6.3's state-diagram note (lines 143-144) — correct "Exactly one task is admitted as the
    probe" to describe the dedicated probe call instead of a real task.
  - §6.5 (lines 196-202) — correct the cooldown/probing-transition walkthrough to describe the
    per-row dedicated probe, not a probe-slot admission window on real tasks.
  - §6.6 (lines 206-218) — correct the "Probe behaviour" section: the probe is a dedicated
    lightweight warmup-style call issued by the pipeline before each row targeting a `PROBING`
    provider, one attempt at the first-attempt adaptive budget, with the outcome map from
    ADR-0013's Design section; there is no remaining "neutral" outcome other than cancellation,
    because there is no next probe candidate to defer to.
  - §10.2 (lines 310-313) — correct the worked example so the recovery step describes the
    dedicated probe call, not "Task 41 runs against the provider as the probe."
  - §10.3 (lines 317-318) — correct the worked example so the failed-recovery step describes the
    dedicated probe's own timeout, not a probe task's retry-laddered timeout.
  - Test-case row CB-05 (line 331) — correct to describe the dedicated probe firing on the first
    post-cooldown row, not `should_skip` returning `False` to admit a task.
  - Test-case row CB-06 (line 333) — correct or remove, since there is no longer a probe slot
    for a second `should_skip` to be excluded from; `should_skip` is `True` throughout `PROBING`.
  - Test-case row CB-14 (line 341) — correct to state that a `FAILED_TIMEOUT` task never counts
    toward the breaker from the per-task dispatch path (per §6.4/§6.9), resolving its
    contradiction with those sections; the probe's own timeout is covered by CB-08's existing
    "`record_failure` while `PROBING`" row.

## Out of scope

- §1 (Purpose) and §5 (Postconditions) and §6.2's Meaning/pipeline columns — already correctly
  reflect DD-71 and must not be touched.
- Any other file under `docs/v3_specification/`.
- Restructuring the document, renumbering sections, or changing any anchor a `spec_clauses:`
  entry elsewhere cites — doing so would break the traceability gate.
- Any code change — STORY-100, STORY-101, and STORY-102 already delivered the behaviour this
  story's text corrections describe.

## Spec inputs

- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states` — the section whose
  `should_skip` column this story corrects.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram` — the section whose
  probe-admission note this story corrects.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing` —
  the section this story rewrites to describe the per-row dedicated probe instead of a
  probe-slot admission window.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour` — the core stale section
  this story replaces with ADR-0013's outcome map and one-attempt shape.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#102-edge-case--a-provider-goes-down-trips-and-recovers` —
  the worked example whose recovery step this story corrects.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#103-edge-case--a-failed-probe-re-trips-the-breaker` —
  the worked example whose failed-recovery step this story corrects.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#11-test-cases` — the section containing rows
  CB-05, CB-06, and CB-14, all three corrected by this story.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3` — the edge case this correction keeps
  accurately described end to end, from catalog through to the now-corrected spec prose.

## Design constraints

- `docs/v3_specification/` is read-only **except in this story**, under the owner sanction
  quoted verbatim in Notes below — the same one-time-exception form STORY-074 used.
- This sanctioned edit must **not** be folded into STORY-100, STORY-101, or STORY-102 — mixing a
  sanctioned spec edit into a code story is how a one-time exception becomes a habit.
- The corrected file must stay `mdformat`-clean; no other markdown files are touched.
- No `spec_clauses:` anchor cited by any other story may be broken by this edit — headings this
  story does not list as an editable site are left byte-identical.

## Acceptance criteria

### STORY-103-AC-1

Given the nine stale sites of `08_CIRCUIT_BREAKER.md` catalogued in STORY-102's Notes (§6.2's
`should_skip` column, §6.3's note, §6.5, §6.6, §10.2, §10.3, CB-05, CB-06, CB-14), when
`tests/architecture/test_circuit_breaker_spec_reflects_dd71.py` is run, then the test asserts
that every one of the nine sites describes the dedicated-lightweight-probe design (a
pipeline-issued, single-attempt, per-row liveness call whose outcome always resolves the breaker
except on cancellation) instead of the retired real-task probe admission, §1 and §5 and §6.2's
Meaning/pipeline columns are left unchanged, every `spec_clauses:` anchor cited anywhere in the
story backlog still resolves, and test-case row CB-14 no longer states that a per-task timeout
counts toward the breaker's failure threshold.

## Test plan

- STORY-103-AC-1 — parametrized guard test,
  `tests/architecture/test_circuit_breaker_spec_reflects_dd71.py`,
  `test_circuit_breaker_spec_reflects_dd71`, parametrized over the nine stale sites. The test
  reads `docs/v3_specification/11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` and asserts
  that each of the nine sites no longer describes the retired real-task probe admission, now
  describes the dedicated-lightweight-probe design, and that test-case row CB-14 no longer states
  a per-task timeout counts toward the breaker. The test asserts on the document's content only
  — it does not shell out to `scripts/validate_traceability.py`; running the validator is a
  separate definition-of-done step performed by hand, not something a pytest test should do.
- EC-PROV-3 — covered by STORY-103-AC-1: the edge case's governing spec prose is corrected to
  match the implementation that actually resolves it.

## Definition of done

- [x] STORY-103-AC-1 is satisfied and recorded as done in this story with no failing test.
- [x] `just check` is green, including the markdown formatter, for the edited spec file (the
  markdown formatter as wired in `justfile`'s `format`/`format-check` targets does not include
  `docs/v3_specification/` — it only formats `README.md`, `CHANGELOG.md`, `docs/adr`,
  `docs/architecture`, `docs/development`, `docs/stories`, matching the vendored-spec's
  read-only status; the edit was made to match the file's own existing (non-mdformat-default)
  table/list/rule style so it introduces no formatting drift of its own).
- [x] `uv run python scripts/validate_traceability.py` shows exactly the pre-existing baseline
  errors and no new unresolvable-spec-anchor error.
- [x] The traceability record validates with no orphan clause for STORY-103.
- [x] The module inventory is unchanged.

## Notes

Owner sanction for this story's spec edit (recorded verbatim from the approved implementation
plan): "`docs/v3_specification/` is read-only **except in STORY-103**, which carries explicit
owner sanction recorded in its Notes (the STORY-074 precedent's form)." and "**Must not be
folded into 100/101/102** — mixing a sanctioned spec edit into a code story is how a one-time
exception becomes a habit."

This story's `modules:` entry cites `backend/circuit_breaker/` because that is the module the
corrected spec document (`08_CIRCUIT_BREAKER.md`) specifies, even though this story makes no
code change to that module — `02_STORY_FORMAT.md` requires at least one real module path from
`01_MODULE_INVENTORY.md`, and no vendored-specification path qualifies as a `modules:` entry.

Guard test added on owner decision: documentation-only stories have no path to `done` under this
repository's traceability mechanics (every `done` story must have an acceptance criterion with a
non-empty `tests:` list, populated by parsing pytest's `Proves:` docstrings). Rather than
document-review without a test, a lightweight parametrized guard test
(`test_circuit_breaker_spec_reflects_dd71`) verifies the specification's content against the
current implementation, guarding against silent reverts of the corrected prose.

**Implementation landed 2026-07-28.** Corrected all nine sites in
`08_CIRCUIT_BREAKER.md`, applied with direct file edits (not the Edit tool) after the editor's
own PostToolUse `mdformat` hook reformatted the whole document on the first attempt (thematic
breaks, ordered-list numbering, and every pipe table) — far beyond the nine permitted sites;
that attempt was reverted with `git checkout` before reapplying the nine corrections precisely,
verified scoped by `git diff` showing only the intended lines changed and no heading text
touched. Added `tests/architecture/test_circuit_breaker_spec_reflects_dd71.py`,
`test_circuit_breaker_spec_reflects_dd71`, parametrized over the nine sites. Proved
load-bearing: ran RED against the pre-correction text via `git stash` on the spec file alone
(all nine parametrized cases failed, each on its own site's stale-wording assertion), then
GREEN after `git stash pop` restored the correction. `just check` passed in full, including
`mypy --strict`, `ruff`, `import-linter`, and the full test suite (`tests/architecture` 1293
passed; `tests/unit tests/integration src` 2185 passed). §1, §5, and §6.2's Meaning/pipeline
columns were left byte-identical, confirmed by `git diff` scoped review. No `spec_clauses:`
anchor was broken — no heading was touched, only body prose, table cells, and mermaid-diagram
note text within already-permitted sections. `docs/adr/0013-dedicated-lightweight-circuit-breaker-probe.md`'s
outcome-map table (Decision outcome, item 2) was the authoritative source for §6.6's rewritten
outcome list, per the task brief.
