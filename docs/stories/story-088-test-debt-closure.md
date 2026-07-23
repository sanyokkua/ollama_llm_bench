---
id: STORY-088
title: Close three known test debts — Gemini contract leg, run-log retention, and a shared resume fixture
status: draft
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double
  - 12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary
modules:
  - backend/provider_gemini/
  - backend/log_file_writer/
  - ui/resume_benchmark/
acceptance_criteria:
  - STORY-088-AC-1
  - STORY-088-AC-2
  - STORY-088-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: tester
estimate: M
---

# STORY-088 — Close three known test debts — Gemini contract leg, run-log retention, and a shared resume fixture

## Goal

Clear three specific, independently verifiable test debts. First, the shared `LLMClient`
contract-test suite runs OpenAI-compatible and Anthropic legs but has no Gemini leg, so the Gemini
adapter and its fake are not proven interchangeable. Second, the spec-required run-log-retention
integration test appears to be missing — the resource-limits table requires an explicit integration
test for the startup prune of run-log files. Third, a fake `compose_filename` sanitizer is duplicated
across three resume-widget test files; it should be one shared conftest fixture.

## In scope

- Adding the Gemini real (wire-stub-backed) and fake legs to the shared `LLMClient` contract-test
  suite, so the same Protocol-level assertions run against the Gemini adapter and its `testing.py`
  fake, both passing.
- Adding the run-log-file retention integration test: run-log files are pruned at startup to at most
  200 files and at most 90 days, oldest-first, leaving no orphans.
- Consolidating the triplicated fake `compose_filename` sanitizer used by the resume-widget export
  tests (`test_actions.py`, `test_controller.py`, `test_controller_menu_actions.py`) into a single
  shared conftest fixture, with the three files consuming it.

## Out of scope

- Any change to the Gemini adapter, the log writer, or the resume widget's production code — these
  are test-authoring and test-refactor debts, not feature work; if a test surfaces a genuine defect,
  it is escalated as its own story.
- The run-log panel buffer bound (a separate UI concern) — this story covers the on-disk run-log file
  retention prune only.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol` — every
  swap-point Protocol with a real implementation and a `testing.py` fake carries one shared
  contract-test suite run against both; the Gemini `LLMClient` must have both legs on that suite.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double`
  — the `LLMClient` real leg runs against the `pytest-httpserver` wire stub via the SDK's base-URL
  override, fully offline; the Gemini real leg uses that same transport-level stub.
- `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md#7-resource-limits-summary` — run-log file retention is
  capped at ≤ 200 files and ≤ 90 days with no orphans, enforced by an oldest-first / age-based prune
  at startup, and the enforcement row names an integration test as its mechanism.

## Design constraints

- The Gemini real leg contacts no live model — it runs against the wire stub on `127.0.0.1`, matching
  the offline-CI rule and the existing OpenAI/Anthropic legs.
- The run-log-retention test runs against real run-log files created in `tmp_path` (never in-memory)
  and asserts the post-prune file set.
- The consolidated resume fixture preserves the exact filenames the three resume export tests already
  depend on; no assertion in those tests changes except the source of the fake.

## Acceptance criteria

### STORY-088-AC-1

Given the shared `LLMClient` contract-test suite,
when it is parametrized to include the Gemini real (wire-stub) and Gemini fake implementations,
then both Gemini legs run the suite's assertions and pass.

### STORY-088-AC-2

Given a run-log directory containing more than 200 files and files older than 90 days,
when the startup run-log prune runs,
then the remaining run-log files are at most 200 and at most 90 days old, pruned oldest-first, with no
orphaned files left.

### STORY-088-AC-3

Given a resume-widget export action,
when a run is exported,
then the target filename is the shared conftest fake's `compose_filename` result, and all three
resume export test files obtain that fake from the single shared fixture.

## Test plan

- STORY-088-AC-1 — contract (wire stub, offline), `tests/contract/test_llm_client_contract.py`,
  parametrized `gemini_real` / `gemini_fake` legs on the existing suite (e.g.
  `test_chat_returns_chat_response` and the probe/no-raise assertions run for the Gemini legs).
- STORY-088-AC-2 — integration (`tmp_path`), `tests/integration/test_run_log_retention.py`,
  `test_startup_prune_caps_run_logs_to_200_files_and_90_days`.
- STORY-088-AC-3 — integration (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py` (and the two sibling resume test
  files), `test_export_uses_shared_compose_filename_fixture`, all consuming the shared fixture from
  `src/ollama_llm_bench/ui/resume_benchmark/tests/conftest.py`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-088.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
