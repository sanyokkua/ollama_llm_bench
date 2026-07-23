---
id: STORY-085
title: Drive a complete benchmark run from the UI through the real pipeline with fake providers
status: draft
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#7-testing-the-qt-free-backend-headlessly
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment
  - 08_Cross_Cutting/08-M_app_lifecycle.md#6-running-state
modules:
  - ui/new_benchmark/
  - backend/benchmark_pipeline/
  - ui/results/
acceptance_criteria:
  - STORY-085-AC-1
  - STORY-085-AC-2
  - STORY-085-AC-3
  - STORY-085-AC-4
edge_cases: []
depends_on:
  - STORY-081
  - STORY-083
adrs: []
owner: tester
estimate: M
---

# STORY-085 — Drive a complete benchmark run from the UI through the real pipeline with fake providers

## Goal

Close the biggest remaining test gap: no test drives a whole benchmark from the user interface. The
existing coverage stops at the backend/dispatcher boundary, and the headless smoke tier (STORY-081)
deliberately runs no benchmark. This story adds a `pytest-qt` end-to-end test that starts a run from
the New Benchmark UI with fake providers, drives the real dispatcher thread and the real five-phase
pipeline (including the judge), persists results, and asserts the Result surface reflects them — all
fully offline.

## In scope

- A `pytest-qt` end-to-end test (under `tests/e2e/`) that:
  - builds the wired application and starts a run from the New Benchmark UI, using fake providers
    (each provider's `testing.py` `LLMClient` fake);
  - lets the real `pipeline-dispatcher` thread and the real benchmark/evaluation pipeline execute the
    run to a terminal status, including the judge layer for a graded run;
  - asserts the results are persisted and that the Result widget renders the persisted result rows.
- Fully-offline execution: no live LLM server is contacted; fakes stand in for every provider call.

## Out of scope

- The launch/idle/shutdown smoke path and the `NOT_READY` degraded-launch path — owned by STORY-081;
  this story starts and completes an actual run instead.
- Any change to the pipeline, evaluation, or widgets — already delivered; this story only exercises
  them together and asserts the observable end-to-end behaviour.
- The opt-in live-server tier against real Ollama / LM Studio — owned by STORY-086.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid` — the end-to-end tier (5–10%
  of the suite) is the full application launched and smoke-tested; this run-through belongs to it.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#7-testing-the-qt-free-backend-headlessly` — the
  pipeline is exercised with a faked `LLMClient` and real `tmp_path`-backed persistence stores sharing
  one connection, so result rows and events are asserted directly and deterministically offline.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — the run executes
  under the offscreen Qt platform plugin, fully offline, within the end-to-end time budget.
- `08_Cross_Cutting/08-M_app_lifecycle.md#6-running-state` — a run reaches a persisted terminal status
  (`COMPLETED`/`FAILED`/`STOPPED`), and a graded result carries a binary `PASS`/`FAIL` verdict.

## Design constraints

- The test contacts no live LLM server; every provider call is served by a `testing.py` fake
  (offline, per the CI test environment).
- The test drives the real dispatcher thread and the real pipeline — not an inline stand-in — so the
  serial, one-in-flight-unit execution path is genuinely exercised.
- The run's results are read from a real `tmp_path` SQLite database (never in-memory).
- The end-to-end test completes within the 60-second end-to-end per-test budget.

## Acceptance criteria

### STORY-085-AC-1

Given the wired application with fake providers,
when a run is started from the New Benchmark UI,
then the real dispatcher thread and pipeline execute it to a terminal `COMPLETED` run whose results
are persisted.

### STORY-085-AC-2

Given a graded run started from the New Benchmark UI with fake providers,
when the pipeline completes,
then each graded result carries a binary `PASS`/`FAIL` verdict (never `UNKNOWN`) and the verdicts are
persisted.

### STORY-085-AC-3

Given a completed run,
when the Result widget shows that run,
then the Result surface renders the persisted result rows for the run.

### STORY-085-AC-4

Given the run executes end to end,
when the whole flow runs,
then no live LLM server is contacted — every inference is served by a provider `testing.py` fake.

## Test plan

- STORY-085-AC-1 — e2e (`pytest-qt`, offscreen), `tests/e2e/test_full_run_from_ui_smoke.py`,
  `test_run_started_from_ui_completes_and_persists_results`.
- STORY-085-AC-2 — e2e (`pytest-qt`, offscreen), same file,
  `test_graded_run_produces_binary_verdicts`.
- STORY-085-AC-3 — e2e (`pytest-qt`, offscreen), same file,
  `test_result_widget_reflects_persisted_results`.
- STORY-085-AC-4 — e2e (`pytest-qt`, offscreen), same file,
  `test_full_run_contacts_no_live_server`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-085.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
