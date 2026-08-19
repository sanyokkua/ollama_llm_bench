---
id: STORY-086
title: Add an opt-in, env-gated live smoke tier against a local Ollama and LM Studio
status: done
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
  - STORY-086-AC-5
  - STORY-086-AC-6
edge_cases: []
depends_on:
  - STORY-085
adrs:
  - ADR-0011
  - ADR-0019
owner: tester
estimate: M
---

# STORY-086 — Add an opt-in, env-gated live smoke tier against a local Ollama and LM Studio

## Goal

**Blocked:** stays `draft` until STORY-085 is `done`.

The offline test suite proves behaviour deterministically but never touches a real model server. The
project owner wants a way to prove the app works against a locally installed Ollama and LM Studio,
without weakening the rule that CI stays fully offline. This story adds a new, opt-in test tier —
selected only when an environment variable is set, excluded from `just check` and from both CI
workflows — that, per provider, probes health, discovers models, and executes one tiny real
benchmark run. When the server is absent, the tests skip cleanly. This tier is **additive
infrastructure authorised by ADR-0011**, not something the specification asks for; the specification
is cited below only for the constraints the tier must not violate.

## In scope

- A new `tests/live_local/` directory holding the tier's tests, carrying a `live_local` pytest
  marker (the marker name is fixed by ADR-0011).
- Per provider (Ollama and LM Studio, both served by the OpenAI-compatible adapter): probe the
  provider's health, discover at least one model, and execute one tiny real benchmark run to a
  terminal status against that live server.
- Clean auto-skip when the opt-in variable is unset or the target server is not reachable — no
  failure, no hang.
- `scripts/_traceability_lib.py` passes `-m ""` when collecting, so `just trace` still sees the
  deselected live tests and `just trace-check` does not report their acceptance criteria as
  unproven.
- The two provider modules share their probe/discover/run body through a `live_smoke` fixture in
  `tests/live_local/conftest.py`. They cannot share it by import: pytest registers a plain
  `conftest.py` under the bare name `conftest`, so with several conftests collected
  `from conftest import ...` silently returns whichever was imported last.
- **Added mid-story, owner-approved:** the two production fixes the tier's first real run uncovered
  (AC-5 and AC-6 below).

### The three mechanics that must be got right, or the build breaks

Each of these is stated concretely because getting any one wrong turns a green suite red for
everyone, including on a machine that has no Ollama installed at all.

**1. Register the marker, or every live test errors at collection.** `pyproject.toml`'s
`[tool.pytest.ini_options].addopts` includes `--strict-markers`, so an unregistered marker is a
collection **error**, not a warning. Add `"live_local: Opt-in tests against a real local Ollama / LM Studio server (ADR-0011); never run in CI"` to the existing `markers` list, alongside `unit`,
`integration`, `slow`, `property`, and `allow_qt_warnings`.

**2. Exclude the tier by default via `addopts`, and update both workflows.** `testpaths = ["src", "tests"]`, so a bare `uv run pytest` collects `tests/live_local/`. Several real commands are bare:
`just test`, the first line of `just coverage-layers`, `release.yml`'s `uv run pytest -q`
(quality-gate job), and `pr-gate.yml`'s coverage step `uv run pytest --cov=ollama_llm_bench --cov-report=term-missing` (which names no paths). `pr-gate.yml`'s other two test steps do name
explicit paths and are therefore already unaffected — but the coverage step is not, so **both**
workflow files still need updating.

**Chosen mechanism: `addopts = ["-m", "not live_local"]`** in `[tool.pytest.ini_options]`, added to
the existing `--import-mode=importlib`, `--strict-markers`, `--strict-config`, `-ra` entries. A
`collect_ignore` in a `tests/live_local/conftest.py` would also work, but `addopts` needs no
per-directory file and covers every bare invocation at once. `addopts` carries **no** `-m` entry
today, so there is nothing to conflict with. Running the tier on demand is then
`uv run pytest tests/live_local -m live_local` — a command-line `-m` overrides the one in `addopts`.

> **Coordination with STORY-094 (packaging).** STORY-094 introduces a **separate** `packaging`
> marker with its own opt-in environment variable. The two markers and the two variables are
> deliberately independent and must not be given colliding names. One shared constraint applies:
> **pytest honours only the last `-m` it is given**, so the two tiers must not each append their own
> `-m` to `addopts`. Whichever story lands second extends the single existing expression into
> `-m "not live_local and not packaging"` rather than adding a second `-m` entry.

**3. The opt-in environment variable is `OLLAMA_BENCH_LIVE_LOCAL_TESTS`, set to `1`.** Named to
match the `live_local` marker and to be unmistakably distinct from STORY-094's packaging variable.
It is read once in `tests/live_local/conftest.py`; when it is unset or not `1`, every test in the
directory skips.

## Out of scope

- The offline full-run-from-UI end-to-end test — owned by STORY-085 (this story's prerequisite; the
  live tier reuses its run-through shape against real servers).
- Any change to the provider adapter, the readiness service, or the pipeline — all already
  delivered; this story only adds the opt-in tier that drives them against real local servers.
- Cloud providers (OpenAI/Azure, Anthropic, Gemini) — the owner's request is specifically local
  Ollama and LM Studio.
- Adding the live tier to any CI workflow, or to `just check`. It is local-and-on-demand only, and
  ADR-0011 fixes that boundary.

## Spec inputs

The testing standard **never describes a live tier** — CI is deliberately fully offline, and there
is no nightly workflow. Nothing below mandates this tier; each line states the constraint the tier
must respect or the shape it must borrow. The authority for the tier's existence is **ADR-0011**
(accepted 2026-07-23), whose Decision outcome §1 names the `live_local` marker, the opt-in
environment variable, the `tests/` location, the exclusion from `just check` and CI, and the
clean auto-skip — and assigns all of it to this story.

- `16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout` — **take from it:** where a
  cross-cutting tier lives (the top-level `tests/` tree, not a colocated module directory) and the
  fact that every pytest marker is declared in `[tool.pytest.ini_options]` under `--strict-markers`.
  This clause does not list a `live_local` marker; ADR-0011 authorises adding one.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol` —
  **take from it:** the constraint that the offline `LLMClient` contract suite's real leg runs
  against the wire stub and never a live server. This story must not alter that suite or add a live
  leg to it; the live tier is a separate surface that leaves the contract suite untouched.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — **take from it:**
  the offline-CI constraint the tier must not violate. CI runs under the offscreen Qt platform with
  no live-server access, and there is no scheduled/nightly workflow (DD-36), so there is no CI
  surface this tier could legitimately be attached to. It must be excluded from the pull-request
  gate and run only locally, on demand.
- `08_Cross_Cutting/08-M_app_lifecycle.md#5-the-readiness-probe` — **take from it:** the real
  behaviour the tier exercises. The readiness self-check probes every enabled provider for
  reachability and at least one available model; the live tier drives that same real probe against
  the local servers instead of a stub.

## Design constraints

- The tier is opt-in by `OLLAMA_BENCH_LIVE_LOCAL_TESTS=1` and carries the `live_local` marker; the
  default `just check` / CI selection never runs it.

- A missing opt-in variable or an unreachable server results in a clean `pytest.skip`, never a
  failure and never a hang — the reachability check uses a bounded connection timeout.

- The tiny live run uses the real OpenAI-compatible adapter, the real readiness service, and the
  real pipeline; no fake and no wire stub stands in for the provider in this tier — that is the
  entire point of it.

- **The tier was planned to add no production-code change — that is no longer true, by owner
  decision.** The tier is test infrastructure plus the `pyproject.toml` marker/`addopts` entries
  and the two workflow updates; but on its first real run against a live Ollama it found two
  spec-violating defects in `src/`, neither of which the offline suite can see by construction.
  The owner approved fixing both inside this story (2026-08-19), so the story also ships:

  - a fix in `backend/benchmark_pipeline/_internal/units.py` (with `stability_phase.py`) so a
    non-grading run reaches `COMPLETED` instead of parking in `AWAITING_KEYWORD_CHECK` —
    acceptance criterion **STORY-086-AC-5**;
  - a fix in `backend/provider_openai_compatible/_internal/client_impl.py` so the streaming call's
    transport `read` timeout is the call's own budget instead of a fixed 0.5 s — acceptance
    criterion **STORY-086-AC-6**, ratified by **ADR-0019**.

  The `src/` licence extends to those two defects only. The second fix's remaining work — the
  timer-driven heartbeat the specification's own wording describes, and the byte-for-byte
  identical construct in `backend/provider_anthropic/_internal/client_impl.py` that was left
  unchanged because its transport is unverified — is carried by **STORY-120**.

## Acceptance criteria

### STORY-086-AC-1

Given `OLLAMA_BENCH_LIVE_LOCAL_TESTS=1` and a local Ollama server running,
when the live smoke test runs,
then it probes Ollama's health, discovers at least one model, and executes one tiny real benchmark
run to a terminal status.

### STORY-086-AC-2

Given `OLLAMA_BENCH_LIVE_LOCAL_TESTS=1` and a local LM Studio server running,
when the live smoke test runs,
then it probes LM Studio's health, discovers at least one model, and executes one tiny real
benchmark run to a terminal status.

### STORY-086-AC-3

Given `OLLAMA_BENCH_LIVE_LOCAL_TESTS` is unset, or the target server is not reachable within the
bounded connection timeout,
when the suite is collected and run,
then every test in `tests/live_local/` is skipped and no live server is contacted.

### STORY-086-AC-4

Given a bare `uv run pytest` invocation (the shape used by `just test`, `just coverage-layers`,
`release.yml`'s quality gate, and `pr-gate.yml`'s coverage step),
when the suite runs,
then no test carrying the `live_local` marker is selected.

### STORY-086-AC-5

Given a benchmark run whose mode does not grade (for example `TASKS`) and the shipped default
settings (the keyword and cosine checks both enabled),
when inference succeeds,
then the result row reaches `COMPLETED` rather than parking in `AWAITING_KEYWORD_CHECK`.

Authority: `08_Cross_Cutting/08-B_benchmark_state_machine.md:245` —
`RUNNING_INFERENCE --> COMPLETED: inference succeeded, mode does not grade`.

### STORY-086-AC-6

Given a streaming chat call,
when the provider withholds output for longer than a second,
then the call's transport read timeout is the call's own remaining adaptive budget rather than a
fixed sub-second constant, so a cold model is not failed as a timeout.

Authority: ADR-0019.

## Test plan

- STORY-086-AC-1 — live (`live_local` marker), `tests/live_local/test_ollama_live_smoke.py`,
  `test_ollama_probe_discover_and_tiny_run`.
- STORY-086-AC-2 — live (`live_local` marker), `tests/live_local/test_lmstudio_live_smoke.py`,
  `test_lmstudio_probe_discover_and_tiny_run`.
- STORY-086-AC-3 — unit, `tests/unit/test_live_tier_gating.py`,
  `test_live_tests_skip_when_opt_in_unset_or_server_absent` — deliberately **outside** the tier and
  unmarked, so it runs in the offline gate. A criterion asserting "these tests skip on a machine
  with no server" must be proven on machines with no server; a proving test inside the tier would
  itself be skipped there.
- STORY-086-AC-4 — architecture, `tests/architecture/test_live_tier_excluded_from_gate.py`,
  `test_live_local_marker_excluded_from_default_selection` — reads `pyproject.toml` and asserts
  (a) `live_local` appears in `[tool.pytest.ini_options].markers`, and (b) `addopts` contains an
  `-m` expression that excludes `live_local`. This test runs in the offline gate and is the one
  guard that survives on a machine with no Ollama installed.
- STORY-086-AC-5 — unit (colocated),
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_units.py`,
  `test_finalize_inference_success_completes_non_grading_mode_with_all_toggles_enabled`
  (parametrised over `SYNTHETIC` and `TASKS`) — enables all three grading toggles, so it cannot
  pass against the pre-fix code.
- STORY-086-AC-6 — unit (colocated),
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_deadline.py`,
  `test_stream_read_timeout_handed_to_the_sdk_is_the_request_budget` (pins the timeout value as it
  reaches the transport) and `test_cold_start_within_budget_streams_instead_of_timing_out` (pins
  the consequence: a 1.5 s header withhold inside an 8 s budget streams instead of raising).

## Definition of done

- [ ] **Met for five criteria of six — AC-2 is the exception, and it is not ticked.** Every
  acceptance criterion has a proving test named in the Test plan, and AC-1, AC-3, AC-4, AC-5 and
  AC-6 each have a recorded passing run. AC-2 does not. LM Studio on the development machine is
  wedged: it holds `:1234` open but never answers HTTP (`curl -m 8 http://localhost:1234/v1/models`
  returns `http_code=000` after the full timeout, while Ollama answers `200` in 0.034 s), so
  `test_lmstudio_probe_discover_and_tiny_run` degrades to a clean, bounded skip
  ("answered TCP but talking to it raised `HttpTimeoutError`", ~10.6 s) rather than passing.
  The test exists, is correct, and is proven to degrade cleanly — but **a skip is not a pass**, and
  its passing leg stays unexercised until the owner restarts LM Studio and re-runs `just test-live`.
- [x] `live_local` is declared in `pyproject.toml`'s `markers` list, so `--strict-markers` does not
  error at collection — proven by
  `tests/architecture/test_live_tier_excluded_from_gate.py::test_live_local_marker_excluded_from_default_selection`,
  which the reviewer independently falsified in four sabotage variants.
- [x] `addopts` excludes `live_local` by default, and a bare `uv run pytest` collects zero tests
  from `tests/live_local/` on a machine with no live server — measured: a bare collect reports
  `4001/4003 tests collected (2 deselected)`, exactly the tier's two tests, and zero `live_local/`
  node IDs.
- [x] Both `.github/workflows/pr-gate.yml` and `.github/workflows/release.yml` are updated and
  verified to select no `live_local` test — checked by running each workflow's test command
  verbatim in collect-only mode and grepping the node IDs for `live_local/`: zero hits from both.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules — every static
  stage of `just check` passed on each of three attempts: `ruff check` "All checks passed!",
  `ruff format --check` "1194 files already formatted", `mypy --strict` "Success: no issues found
  in 1064 source files", `lint-imports` clean, and `tests/architecture` `1364 passed`.
- [x] **The full gate is green under CI-parity conditions, and both red signals are measured as
  pre-existing.** A fourth `just check` ran without any segfault: `2 failed, 2566 passed in 2030.05s (0:33:50)`, every static stage green. The only two failures are
  `tests/e2e/test_focus_ring_visibility.py`'s two tests, the already-recorded native-vs-offscreen
  artifact — `just check` does not pin `QT_QPA_PLATFORM`, whereas CI does. Verified by measurement,
  not assertion: `just test-e2e` (offscreen, exactly as `pr-gate.yml` sets it) gives `31 passed in 31.17s`, exit 0, both tests included; the two tests run alone natively pass identically on this
  branch (`2 passed in 3.07s`) and on base `4f01baa` (`2 passed in 3.22s`); and base's own full
  `just check` gave `2561 passed`, exit 0.
  The earlier three `exit=139` segfaults are a **pre-existing PySide6 6.8.3 use-after-free**, now
  root-caused and measured at an identical rate on base and on this branch (1/21 vs 1/11 normal;
  6/12 vs 6/12 under a heap amplifier), with `test_deadline.py` explicitly cleared (6/12 with it,
  6/12 without). Owned by STORY-121 / ADR-0020.
- [x] The traceability record validates with no orphan clause and no orphan test —
  `validate_traceability.py: OK (120 stories, 4005 test(s) collected, zero gaps).`
- [x] The module inventory is unchanged — this story adds no module; the two production fixes land
  inside `backend/benchmark_pipeline/` and `backend/provider_openai_compatible/`, both already
  inventoried and already named in this story's `modules:`.
- [x] Every story under **Unblocks** whose remaining dependencies are now `done` has been checked
  and `just trace` re-run. STORY-120 (sole dependency: this story) flipped `draft` → `ready`.
  STORY-093 stays `draft`: of its dependencies, STORY-092 is `ready` and STORY-082 is `superseded`,
  so its list can never be satisfied as written and needs an architect to drop or re-point that row.
  STORY-121 is newly written as `draft` and depends on nothing.
- [x] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-093** — the Phase-12 traceability, risk, and architecture documentation story. Flip it
  `draft` → `ready` **only once every other story it depends on is `done`**: STORY-076 through
  STORY-089, STORY-091, STORY-092, and STORY-114. STORY-086 is one input among many.
  **Checked at this story's closeout and left `draft`:** two of its seventeen dependencies are not
  `done` — STORY-092 is `ready` (authored, unimplemented) and STORY-082 is `superseded` (replaced
  by ADR-0013 and STORY-100..103, so it can never become `done`; whoever flips STORY-093 will have
  to drop that row or record the supersession explicitly).
- **STORY-120** — the timer-driven inference heartbeat and the unresolved Anthropic streaming read
  timeout, both spun out of this story's Bug B. Added here because it was authored during this
  story, after the section above was written. Its only `depends_on` entry is STORY-086, so it
  becomes `ready` by the rule in `14_Process_and_Traceability/02_STORY_FORMAT.md` §8 as soon as
  this story is `done` — flip it then, together with the `status:` flip here.

**What to do on completion**

Once STORY-086's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependencies in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   With the live tier landed, the remaining gates on STORY-093 are the ones still open — check
   STORY-084, STORY-088, STORY-089, STORY-091, STORY-092, and STORY-114 and rank whichever are
   `ready`.

## Notes

- **The `live_local` and `packaging` markers are deliberately independent.** STORY-094 owns a
  separate `packaging` marker and its own environment variable for the packaging smoke tier. Neither
  story's marker gates the other's tests, and neither variable enables the other's tier. The only
  shared surface is the single `-m` expression in `addopts` — see the coordination note in
  **In scope**.
