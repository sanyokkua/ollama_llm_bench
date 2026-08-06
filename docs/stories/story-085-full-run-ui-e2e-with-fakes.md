---
id: STORY-085
title: Drive a complete benchmark run from the UI through the real pipeline with fake providers
status: ready
spec_clauses:
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#7-testing-the-qt-free-backend-headlessly
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double
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
the New Benchmark UI against a faked provider surface, drives the real dispatcher thread and the
real five-phase pipeline (including the judge), persists results, and asserts the Result surface
reflects them — all fully offline.

## In scope

- One `pytest-qt` end-to-end test module under `tests/e2e/` that:
  - builds the wired application through `build_app` (reusing `tests/e2e/conftest.py`'s
    `build_smoke_app` / `offline_app_data_root` / `shutdown_handle` fixtures) and starts a run from
    the New Benchmark UI;
  - lets the real `pipeline-dispatcher` thread and the real benchmark/evaluation pipeline execute
    the run to a terminal status, including the judge layer for a graded run;
  - asserts the results are persisted and that the Result widget renders the persisted result rows.
- Fully-offline execution: nothing leaves the machine.

### How the provider is faked — decided, not left open

**There is no central `FakeProvider` class in this repository.** Each backend provider module ships
its own fake on its own `testing.py`:

| Module                                | Fake class                   |
| ------------------------------------- | ---------------------------- |
| `backend/provider_openai_compatible/` | `FakeOpenAICompatibleClient` |
| `backend/provider_anthropic/`         | `FakeAnthropicClient`        |
| `backend/provider_gemini/`            | `FakeGeminiClient`           |

Those three fakes are the substitution mechanism for the unit and integration tiers, and they are
what a story that constructs the pipeline directly should use. **This end-to-end test cannot reach
them**, and the coder must not spend a session discovering that: `build_app(*, app, loop)` takes only
a `QApplication` and a `QEventLoop`, and builds its `client_builders` mapping —
`ProviderType.OPENAI_COMPATIBLE` / `ANTHROPIC` / `GEMINI` to the three concrete client factories —
inline inside `build_app` itself. There is no injection seam, and monkey-patching one in is banned by
the coding standard ("Monkey-patching → Redesign with a Protocol seam").

**Decision: the end-to-end test fakes the provider at the transport level, using the §7a
`pytest-httpserver` wire stub**, not a `testing.py` fake. Concretely: the test seeds an
OpenAI-compatible provider row whose `base_url` points at a `pytest-httpserver` instance bound to
`127.0.0.1` on an ephemeral port, serving canned chat/embedding/model-list payloads. This needs zero
production change, keeps the real adapter → real SDK → real HTTP client path in the test, and is the
mechanism the testing standard already sanctions for standing in for a provider without a live
model. Adding an injection seam to `build_app` purely for this test is explicitly **not** part of
this story.

## Out of scope

- The launch/idle/shutdown smoke path and the `NOT_READY` degraded-launch path — owned by STORY-081;
  this story starts and completes an actual run instead.
- Any change to the pipeline, the evaluation phases, the widgets, or `compose.py` — all already
  delivered; this story only exercises them together and asserts the observable end-to-end
  behaviour. In particular, no provider-injection seam is added to `build_app`.
- The opt-in live-server tier against a real local Ollama / LM Studio — owned by STORY-086, which
  depends on this story.

## Spec inputs

- `16_Engineering_Standards/07_TESTING_STANDARD.md#2-the-test-pyramid` — the end-to-end tier (5–10%
  of the suite) is the full application launched and smoke-tested; this run-through belongs to it.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#7-testing-the-qt-free-backend-headlessly` — the
  pipeline is exercised against a faked `LLMClient` surface with real `tmp_path`-backed persistence
  stores sharing one connection, so result rows are asserted directly and deterministically offline.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double`
  — `pytest-httpserver` on `127.0.0.1` with an ephemeral port, the adapter constructed with that
  server's URL as the provider base URL, no interception of SDK internals: this is the substitution
  mechanism this test uses, and the reason it can stay offline without a `build_app` seam.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — local and CI runs
  are deliberately kept in parity, differing on the Qt platform knob: **local runs use the native
  platform, CI uses the offscreen plugin**. See "Which Qt platform" below.
- `08_Cross_Cutting/08-M_app_lifecycle.md#6-running-state` — a run reaches a persisted terminal
  status (`COMPLETED` / `FAILED` / `STOPPED`), and a graded result carries a binary `PASS`/`FAIL`
  verdict.

## Design constraints

### Which Qt platform — decided, not left open

`just test-e2e` (justfile line 46) runs `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q`, and
both CI workflows set `QT_QPA_PLATFORM: offscreen` as a workflow-level `env`. But `just check`
(justfile line 67) runs `uv run pytest tests/unit tests/integration tests/e2e -q` **without** that
variable, so on a developer machine the same test runs under the native platform.

**Decision: the test must pass under both platforms; it must not pin a platform of its own.** Do not
set `QT_QPA_PLATFORM` inside the test, and do not skip on a platform. `just check` is the gate every
developer runs before pushing, and a test that only passes offscreen would fail it; §12's whole point
is that local (native) and CI (offscreen) runs stay in parity. In practice this means: never assert
on real window geometry, real screen coordinates, focus, or activation, and never require a
compositor — assert on widget state and persisted data instead. If a specific assertion genuinely
cannot hold under one platform, drop that assertion rather than pinning the platform, and record why
in the story notes.

### Other constraints

- The test contacts no live LLM server and opens no socket beyond `127.0.0.1`; every provider call is
  served by the local `pytest-httpserver` wire stub.
- The test drives the real dispatcher thread and the real pipeline — not an inline stand-in — so the
  serial, one-in-flight-unit execution path is genuinely exercised.
- The run's results are read from a real `tmp_path`-backed SQLite database file, never an in-memory
  one.
- The test completes within the 60-second end-to-end per-test budget.

## Acceptance criteria

### STORY-085-AC-1

Given the wired application with its provider base URL pointed at the local wire stub,
when a run is started from the New Benchmark UI,
then the real dispatcher thread and pipeline execute it to a terminal `COMPLETED` run whose result
rows are persisted.

### STORY-085-AC-2

Given a graded run started from the New Benchmark UI against the wire stub,
when the pipeline completes,
then every graded result carries a binary `PASS` or `FAIL` verdict — never `UNKNOWN` — and those
verdicts are persisted.

### STORY-085-AC-3

Given a completed run,
when the Result widget shows that run,
then the Result surface renders the persisted result rows for that run.

### STORY-085-AC-4

Given the run executes end to end,
when the whole flow runs,
then every HTTP request the application issued went to the local wire stub's `127.0.0.1` address —
no live LLM server was contacted.

## Test plan

- STORY-085-AC-1 — e2e (`pytest-qt`, platform-agnostic), `tests/e2e/test_full_run_from_ui_smoke.py`,
  `test_run_started_from_ui_completes_and_persists_results`.
- STORY-085-AC-2 — e2e (`pytest-qt`, platform-agnostic), same file,
  `test_graded_run_produces_binary_verdicts`.
- STORY-085-AC-3 — e2e (`pytest-qt`, platform-agnostic), same file,
  `test_result_widget_reflects_persisted_results`.
- STORY-085-AC-4 — e2e (`pytest-qt`, platform-agnostic), same file,
  `test_full_run_contacts_no_live_server` — asserts against the wire stub's recorded request log
  that every request it received is the full set the run issued, and that no enabled provider row
  carries a non-loopback `base_url`.

Every one of these must pass both under `just test-e2e` (offscreen) and under `just check` (native
platform). Run both before calling the story done.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-085.
- [ ] The new tests pass under `just test-e2e` (offscreen) **and** under `just check` (native
  platform), with no `QT_QPA_PLATFORM` set inside the test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-086** — the opt-in live tier against a local Ollama / LM Studio. STORY-085 is its **only**
  dependency, so flip STORY-086 `draft` → `ready` **immediately** once STORY-085 is `done`.
- **STORY-093** — the Phase-12 traceability, risk, and architecture documentation story. Flip it
  `draft` → `ready` **only once every other story it depends on is `done`**: STORY-076 through
  STORY-089, STORY-091, STORY-092, and STORY-114.

**What to do on completion**

Once STORY-085's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependencies in the closing report. STORY-086 qualifies
   immediately; STORY-093 will not.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural next pick is STORY-086, which this story just unblocked and which reuses this
   run-through's shape against real local servers.
