---
id: STORY-117
title: Reduce Qt object churn in the accessibility-name integration tests
status: done
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

## The re-measurement, after the change

Measured 2026-08-20 with ADR-0020's amplified reproducer rather than the plain full-suite method
above — `PYTHONMALLOC=malloc MallocScribble=1 MallocPreScribble=1` in front of
`uv run pytest tests/integration -q`, run sequentially, never concurrently, output redirected to
files. Five plain full-gate runs could not have separated signal from a background crash rate of
roughly one run in three, and a single full gate has taken 51 minutes and 102 minutes on this
machine — hours of wall-clock for a measurement that could not conclude.

| Arm                             | Runs | Clean | Native crash | Tests per clean run |
| ------------------------------- | ---- | ----- | ------------ | ------------------- |
| BEFORE (tree before this story) | 12   | 11    | 1            | 175 passed          |
| AFTER (tree after this story)   | 12   | 12    | 0            | 177 passed          |

**Read honestly, this is directionally right and statistically inconclusive.** One crash in twelve
against zero in twelve is not a significant difference — Fisher's exact test on that table gives
p = 1.0. ADR-0020 calibrated the amplifier on `pytest src`, where it fires on roughly half of all
runs; over `tests/integration` it produced roughly one in twelve, so a 12-run arm has very little
power to detect a change. Extending the arms until they could conclude would take many hours at
roughly 80 seconds a run.

What the arms do establish is the weaker pair of claims worth having: the churn reduction made
nothing worse, and it is not itself a source of crashes. The story anticipated exactly this
outcome — see "Unblocks and next steps" — and it stands as recorded, not as a failure.

The single BEFORE crash carried ADR-0020's signature exactly: exit 133 (SIGTRAP, which is how
macOS's libmalloc traps a corrupted heap) after 30 seconds, against a clean-run time of roughly 78
seconds, with **zero `FAILED` and zero `ERROR` lines**. pytest died before printing its summary, so
the `Fatal Python error:` banner never appeared either — on this tier the exit code, not the log
text, is the reliable crash detector.

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
14 passed.

The count is 14 rather than 12 because this story adds two tests to the file's original twelve:
`test_the_shell_and_the_dialogs_are_built_once_for_the_whole_module`, which proves AC-1's churn
budget, and `test_nothing_shared_between_tests_is_mutable_or_qt_owned`, which proves this
criterion structurally — the only thing shared between the file's tests is one snapshot, and every
value in it down to its leaves is an immutable string, so there is nothing for one test to mutate
under another and nothing Qt-owned left alive past its builder's teardown. A test is needed here,
not just the four recorded runs below: `scripts/trace.py` binds exactly one acceptance criterion
per test, and `validate_traceability.py` fails a `done` story whose criterion has an empty test
list.

## Test plan

- STORY-117-AC-1 — integration, `tests/integration/test_a11y_names_shell.py`,
  `test_the_shell_and_the_dialogs_are_built_once_for_the_whole_module`. It requests the module's
  snapshot and asserts the shell-build and dialog-build counters both read exactly 1, before and
  after a second request. Asserting `== 1` rather than `<= 2` is what makes it order-independent:
  a broken cache would make it observe its own ordinal position in the module and fail everywhere
  except first, and the second request covers the first-position case.
- STORY-117-AC-2 — integration, same file,
  `test_nothing_shared_between_tests_is_mutable_or_qt_owned`, which proves the criterion
  structurally: the only thing shared between this module's tests is one snapshot, and every value
  in it down to its leaves is an immutable string, so there is nothing for one test to mutate under
  another and no Qt object left alive past the teardown of the test that built it. The empirical
  half — the file under `-p no:randomly` and under three recorded seeds — is executed as a
  verification step, with all four results pasted into the story's closing notes.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-117.
- [x] The flake rate is re-measured before and after the change with ADR-0020's amplified
  reproducer — `PYTHONMALLOC=malloc MallocScribble=1 MallocPreScribble=1` in front of
  `uv run pytest tests/integration -q` — run sequentially, never concurrently, with output
  redirected to files rather than piped through `tail`, and both arms recorded beside the table
  in this story.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched files.
- [x] `git diff` against the branch point shows no change under `src/`.
- [x] The traceability record validates with no orphan clause and no orphan test.

## Closing notes

### The churn actually removed

Measured directly, with the two build counters read at module teardown of a full run of the file:

```
CHURN-AT-TEARDOWN shell=1 dialogs=1
14 passed in 0.97s
```

One `build_app` and one seven-dialog construction, against the seven and forty-two this file cost
before. The file's own wall-clock fell to about one second.

### AC-2's four runs

`uv run pytest tests/integration/test_a11y_names_shell.py -q` under each of the four required
orderings:

| Ordering                        | Result             |
| ------------------------------- | ------------------ |
| `-p no:randomly`                | 14 passed in 1.03s |
| `-p randomly --randomly-seed=1` | 14 passed in 1.03s |
| `-p randomly --randomly-seed=2` | 14 passed in 1.05s |
| `-p randomly --randomly-seed=3` | 14 passed in 0.98s |

### The negative control

AC-1's churn test must be able to fail. Falsifying the condition rather than deleting the check —
the accessor still consults the cache, but under a key nothing is ever stored against, so every
lookup misses — turns the file red immediately: **13 failed, 1 passed in 1.03s**. Forcing the churn
test into first position, where its own counter assertion cannot catch the regression, still fails
the very next test to ask for the snapshot. The check fails in every ordering.

### Why the accepted plan's AC-1 test was changed

The plan had the churn test call the snapshot accessor twice, so that a regressed cache would be
caught even when that test ran first. Measured, that design does not fail — it **hangs**. A second
`build_app` against the same app-data root aborts on the single-instance advisory lock
(`launch_aborted reason=instance_lock_already_running`, STORY-079) and production correctly opens a
*fatal* `ErrorDialog`. That dialog is a plain `QDialog`, and this directory's autouse
`_dismiss_not_ready_modal` filter is deliberately scoped to `QMessageBox` alone so it can never race
with the tests that assert on a real `ErrorDialog` — so the dialog `exec()`s and blocks forever,
with no `pytest-timeout` configured to rescue the run. That is the precise failure mode AGENTS.md
warns about.

The second call was therefore replaced by a **rebuild guard** inside the accessor, which refuses a
second build instead of performing one. A future cache regression now fails fast and loudly in
whichever test asks for the snapshot second, in any ordering, rather than silently hanging the
suite. This is strictly stronger than the plan's design, not a concession.

### The gate

`just check` on the finished tree: see the run recorded at close-out. One earlier full-gate run on
this change was red on two tests — `tests/e2e/test_focus_ring_visibility.py`'s two focus-ring
assertions — and the evidence gathered on those is worth recording, because none of it reproduces
them:

| Probe                                               | Result                        |
| --------------------------------------------------- | ----------------------------- |
| Full gate, this tree                                | 2 failed, 2568 passed, 51m25s |
| Full suite, only `test_a11y_names_shell.py` ignored | 0 failed, 2556 passed, 1h42m  |
| `tests/e2e` alone, natively                         | 31 passed                     |
| `tests/integration tests/e2e` natively              | 208 passed in 3m41s           |
| a11y file + focus-ring file together, 8 runs        | 16 passed, every run          |
| focus-ring file alone, 8 runs (control)             | 2 passed, every run           |

The two tests need the real window to hold OS keyboard focus, and they fail only inside a full gate
that runs for the better part of an hour natively; the same two were already recorded failing under
`just check` before this story existed. Sixteen close-range attempts to make this file poison them
found no coupling. The exclusion arm passing is on its own consistent with either explanation, so
this is recorded as unattributed rather than claimed as excluded.

## Unblocks and next steps

Nothing depends on this story. It is worth doing before STORY-098 and STORY-099 land, because both
add further accessibility tests over further surfaces and will multiply whatever pattern this file
establishes.

If the re-measurement shows the flake rate unchanged after the churn is reduced, that is itself a
useful result: it would rule out this file as the cause and point the STORY-087 native-crash
follow-up elsewhere. Record that outcome rather than treating it as a failure of this story.
