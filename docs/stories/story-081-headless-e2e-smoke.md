---
id: STORY-081
title: Add the headless end-to-end smoke tier for launch, idle, and clean shutdown
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 08_Cross_Cutting/08-M_app_lifecycle.md#5-the-readiness-probe
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-5
modules:
  - ui/main_window/
  - backend/readiness/
acceptance_criteria:
  - STORY-081-AC-1
  - STORY-081-AC-2
edge_cases:
  - EC-M-5
depends_on:
  - STORY-076
  - STORY-077
  - STORY-078
  - STORY-079
  - STORY-080
adrs:
  - ADR-0010
owner: tester
estimate: M
---

# STORY-081 — Add the headless end-to-end smoke tier for launch, idle, and clean shutdown

## Goal

Prove that the fully wired application starts, becomes usable, and shuts down cleanly — the Phase-11
definition of done. Launched headless under the offscreen Qt platform, the application runs the whole
launch sequence, shows the main window, settles into a navigable idle state, and quits cleanly. The
tier also proves the degraded path: when the startup readiness probe fails every check, the
application resolves to `NOT_READY`, gates run start, and stays navigable so the user is never handed
an enabled Start button for an environment that cannot run a benchmark.

## In scope

- The `tests/e2e/` smoke tier that builds the application through `build_app` and drives it under the
  offscreen Qt platform plugin: launch through the full sequence, show the main window, reach the
  idle state, and run the clean shutdown.
- The degraded-launch scenario: a readiness probe that fails every check resolves the application to
  `NOT_READY`, gates run start, surfaces the failure in the status bar and an explanatory modal, and
  leaves the user interface navigable.

## Out of scope

- The entry point and exception hooks (STORY-076), the object graph and `AppHandle` (STORY-077), the
  launch glue (STORY-078), the single-instance lock (STORY-079), and the quit sequence (STORY-080) —
  this story exercises them end to end, it does not implement them.
- The readiness probe algorithm and its `READY` / `DEGRADED` / `NOT_READY` resolution — already
  delivered by STORY-016; this story asserts the `NOT_READY` launch effect only.
- Any live LLM-server contact — the e2e tier runs fully offline with a faked provider surface.

## Spec inputs

- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the full ordered launch to
  the running state, ending at `app.exec()`, which the smoke test drives.
- `08_Cross_Cutting/08-M_app_lifecycle.md#5-the-readiness-probe` — the deferred-tick readiness probe
  runs on a background worker and resolves to `READY` / `DEGRADED` / `NOT_READY`; a `NOT_READY`
  environment gates run start and is surfaced in the status bar and an explanatory modal while the
  interface stays navigable.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid` — the end-to-end tier is 5–10%
  of the suite: the full application launched and smoke-tested.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — e2e runs under the
  offscreen Qt platform plugin, within the 60-second end-to-end per-test budget.
- `08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-5` — when the readiness probe fails completely,
  readiness resolves to `NOT_READY`, run start is gated, the interface stays navigable, and the failure
  is surfaced in the status bar and through an explanatory modal.

## Design constraints

- The e2e tier runs under the offscreen Qt platform plugin and contacts no live LLM server (fully
  offline, per the CI test environment).
- The smoke test completes within the 60-second end-to-end per-test time budget.
- The clean-shutdown assertion exercises the ordered shutdown of `AppHandle` (STORY-077/STORY-080) —
  no worker thread outlives the shutdown and the database is checkpointed and closed.

## Acceptance criteria

### STORY-081-AC-1

Given the application is launched headless under the offscreen Qt platform,
when it runs the full launch sequence,
then it shows the main window, reaches a navigable idle state, and shuts down cleanly within the
end-to-end time budget.

### STORY-081-AC-2

Given the startup readiness probe fails every check,
when the deferred readiness tick resolves,
then application readiness is `NOT_READY`, run start is gated, the user interface stays navigable, and
the failure is surfaced in the status bar and an explanatory modal (EC-M-5).

## Test plan

- STORY-081-AC-1 — e2e, `tests/e2e/test_launch_idle_shutdown_smoke.py`,
  `test_app_launches_reaches_idle_and_shuts_down_cleanly`.
- STORY-081-AC-2 — e2e, `tests/e2e/test_launch_not_ready_gating.py`,
  `test_readiness_probe_total_failure_resolves_not_ready_and_gates_run_start`. Covers EC-M-5.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-081.
- [ ] EC-M-5 has a passing test.
- [ ] The headless smoke test (launch → idle → clean shutdown) passes.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
