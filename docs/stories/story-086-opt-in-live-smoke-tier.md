---
id: STORY-086
title: Add an opt-in, env-gated live smoke tier against a local Ollama and LM Studio
status: draft
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment
  - 08_Cross_Cutting/08-M_app_lifecycle.md#5-the-readiness-probe
modules:
  - backend/provider_openai_compatible/
  - backend/readiness/
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-086-AC-1
  - STORY-086-AC-2
  - STORY-086-AC-3
  - STORY-086-AC-4
edge_cases: []
depends_on:
  - STORY-085
adrs:
  - ADR-0011
owner: tester
estimate: M
---

# STORY-086 — Add an opt-in, env-gated live smoke tier against a local Ollama and LM Studio

## Goal

The offline test suite proves behaviour deterministically but never touches a real model server. The
project owner wants a way to prove the app works against a locally installed Ollama and LM Studio,
without weakening the rule that CI stays fully offline. This story adds a new, opt-in test tier —
selected only when an environment variable is set, excluded from `just check` and CI — that, per
provider, probes health, discovers models, and executes one tiny real benchmark run. When the server
is absent, the tests skip cleanly. This deliberate, documented extension of the testing standard is
recorded in ADR-0011.

## In scope

- A new env-gated pytest marker tier (a `live_local` marker, selected only when the tier's opt-in
  environment variable is set) living under `tests/`, excluded by default from `just check` and CI.
- Per provider (Ollama and LM Studio, both served by the OpenAI-compatible adapter): probe the
  provider's health, discover at least one model, and execute one tiny real benchmark run to a
  terminal status against that live server.
- Clean auto-skip when the opt-in variable is unset or the target server is not reachable — no
  failure, no hang.

## Out of scope

- The offline full-run-from-UI end-to-end test — owned by STORY-085 (this story's prerequisite; the
  live tier reuses its run-through shape against real servers).
- Any change to the provider adapter, readiness service, or pipeline — already delivered; this story
  only adds the opt-in tier that drives them against real local servers.
- Cloud providers (OpenAI/Azure, Anthropic, Gemini) — the owner's request is specifically local
  Ollama and LM Studio.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout` — pytest markers are declared in
  `[tool.pytest.ini_options]` under `--strict-markers`; the new tier adds its marker there and lives
  at the top-level `tests/` tree.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol` — no
  offline contract-suite leg ever contacts a live LLM server; the live tier is a separate,
  additional, opt-in surface, never part of the offline gate.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — CI is fully offline
  and there is no scheduled/nightly workflow (DD-36); the live tier must therefore be excluded from
  the pull-request gate and run only locally on demand.
- `08_Cross_Cutting/08-M_app_lifecycle.md#5-the-readiness-probe` — the readiness self-check probes
  every enabled provider for reachability and at least one available model; the live tier exercises
  that real probe against the local servers.

## Design constraints

- The tier is opt-in by environment variable and carries the `live_local` marker; the default
  `just check` / CI selection never runs it (honouring the offline-CI rule and DD-36).
- A missing opt-in variable or an unreachable server results in a clean `pytest.skip`, never a
  failure and never a hang (bounded connection timeout).
- The tiny live run uses the real OpenAI-compatible adapter, the real readiness service, and the real
  pipeline; no fakes stand in for the provider in this tier.

## Acceptance criteria

### STORY-086-AC-1

Given the live-tier opt-in environment variable is set and a local Ollama server is running,
when the live smoke test runs,
then it probes Ollama's health, discovers at least one model, and executes one tiny real benchmark
run to a terminal status.

### STORY-086-AC-2

Given the live-tier opt-in environment variable is set and a local LM Studio server is running,
when the live smoke test runs,
then it probes LM Studio's health, discovers at least one model, and executes one tiny real benchmark
run to a terminal status.

### STORY-086-AC-3

Given the live-tier opt-in environment variable is unset, or the target server is not reachable,
when the suite is collected and run,
then the live tests are skipped cleanly and no live server is contacted.

### STORY-086-AC-4

Given the default `just check` / CI test selection,
when the suite is run,
then the `live_local` tier is excluded and no test in it executes.

## Test plan

- STORY-086-AC-1 — live (`live_local` marker), `tests/live_local/test_ollama_live_smoke.py`,
  `test_ollama_probe_discover_and_tiny_run`.
- STORY-086-AC-2 — live (`live_local` marker), `tests/live_local/test_lmstudio_live_smoke.py`,
  `test_lmstudio_probe_discover_and_tiny_run`.
- STORY-086-AC-3 — live (`live_local` marker), `tests/live_local/test_live_tier_gating.py`,
  `test_live_tests_skip_when_opt_in_unset_or_server_absent`.
- STORY-086-AC-4 — architecture, `tests/architecture/test_live_tier_excluded_from_gate.py`,
  `test_live_local_marker_excluded_from_default_selection`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-086.
- [ ] The `live_local` marker is declared and excluded from the default gate selection.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
