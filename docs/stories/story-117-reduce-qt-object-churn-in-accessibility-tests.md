---
id: STORY-117
title: Reduce Qt object churn in the accessibility-name integration tests
status: ready
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#5-fixtures
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#11-coverage-targets-and-time-budgets
modules:
  - ui/main_window/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-117-AC-1
  - STORY-117-AC-2
edge_cases: []
depends_on:
  - STORY-097
adrs: []
owner: coder
estimate: S
---

# STORY-117 — Reduce Qt object churn in the accessibility-name integration tests

## Goal

`tests/integration/test_a11y_names_shell.py`, added by STORY-097, builds the entire application
seven times and constructs all seven shared modal dialogs six times over — 42 dialog
constructions — inside a single pytest process. Measurement during STORY-097's close-out shows
this measurably increases the whole suite's flake rate. Rebuild the same coverage with far fewer
Qt objects, without weakening a single assertion.

## The measurement that motivated this

Eleven full-suite runs during STORY-097's final gate, alternating between the pre-story commit
`6ca3bbb` and the post-story commit, run sequentially and without `QT_QPA_PLATFORM=offscreen`:

| Commit                       | Runs | Clean | Native SIGSEGV | `ui/resume_benchmark` menu-action failures |
| ---------------------------- | ---- | ----- | -------------- | ------------------------------------------ |
| `6ca3bbb` (before STORY-097) | 5    | 4     | 0              | 0                                          |
| after STORY-097              | 6    | 2     | 2              | 2                                          |

The one non-clean baseline run was an unrelated Gemini HTTP timing race, not a crash.

**The failures are not defects in STORY-097's code.** `ui/resume_benchmark/` is untouched by that
story; the dialog factory those tests mock has an unchanged signature; and
`test_controller_menu_actions.py` passes 18 of 18 in isolation on three consecutive runs. Both
observed failures share a shape — a `QAction` is triggered but its handler never runs — which is a
Qt object-lifetime symptom, not a naming one.

What changed is pressure. This repository already documents a roughly one-in-three native crash
inside CPython's cyclic garbage collector whose leading suspect is Qt widget accumulation
(recorded as an open follow-up from STORY-087). STORY-097 added a large amount of exactly that.

## In scope

- Rebuild `tests/integration/test_a11y_names_shell.py` so it constructs the application shell and
  the seven shared dialogs far fewer times, while asserting exactly what it asserts today.
- Re-measure the flake rate afterwards with the same method, and record the result.

## Out of scope

- Diagnosing the underlying native crash or the menu-action lifetime bug. Those are the STORY-087
  follow-up's territory; this story only removes the pressure this test file adds.
- Any change to production code under `src/`.
- The sibling accessibility stories' own test files (STORY-098, STORY-099), unless they adopt the
  same fixture and inherit the fix for free.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#5-fixtures` — a fixture uses the smallest scope
  that works, and `scope="session"` is reserved for genuinely expensive resources. Building the
  whole application is such a resource; the current file rebuilds it per parametrized case.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#11-coverage-targets-and-time-budgets` — the
  integration tier's per-test budget, and the requirement that the full pull-request suite
  completes inside four minutes.

## Design constraints

- **`qtbot` is function-scoped and cannot be promoted.** Any wider-scoped fixture must therefore
  not depend on `qtbot`; a factory fixture is the established pattern here.
- **Widening a Qt fixture's scope is the known-risky move in this repository.** A previous story
  hit session-wide contamination through a leaked Qt quit flag that produced dozens of unrelated
  failures. Whatever scope is chosen must be proven not to leak state between tests — for example
  by asserting the shell's state is pristine at the start of each case, or by rebuilding on a
  detected mutation.
- Every assertion in the file today must survive unchanged. The pinned strings stay hardcoded
  literals rather than imports of the production constants, so a spec-to-implementation drift
  still cannot pass silently.
- The walker must keep excluding Qt's own internal parts of composite controls
  (`_has_composite_ancestor`) and must keep `QComboBox` and `QAbstractItemView` in its interactive
  set.

## Acceptance criteria

### STORY-117-AC-1

`tests/integration/test_a11y_names_shell.py` builds the application shell no more than twice and
constructs the seven shared modal dialogs no more than twice per full run of that file, while all
12 of its existing tests still pass with their present assertions.

### STORY-117-AC-2

No test in the file observes state left behind by another: running the file with
`-p no:randomly` and running it under at least three different `pytest-randomly` seeds both yield
12 passed.

## Test plan

- STORY-117-AC-1 — integration, `tests/integration/test_a11y_names_shell.py` itself, plus a
  counting assertion: a test that records how many times the shell factory and the dialog builder
  are invoked across the module and asserts each is at most two.
- STORY-117-AC-2 — executed as a verification step rather than a self-asserting test: run the file
  under `-p no:randomly` and under three recorded seeds, and paste all four results into the
  story's closing notes.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-117.
- [ ] The full suite is re-measured with the same method used above — at least five sequential
  runs, no `QT_QPA_PLATFORM=offscreen`, never concurrent — and the crash/flake count is recorded
  beside the table in this story.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched files.
- [ ] `git diff` against the branch point shows no change under `src/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.

## Unblocks and next steps

Nothing depends on this story. It is worth doing before STORY-098 and STORY-099 land, because both
add further accessibility tests over further surfaces and will multiply whatever pattern this file
establishes.

If the re-measurement shows the flake rate unchanged after the churn is reduced, that is itself a
useful result: it would rule out this file as the cause and point the STORY-087 native-crash
follow-up elsewhere. Record that outcome rather than treating it as a failure of this story.
