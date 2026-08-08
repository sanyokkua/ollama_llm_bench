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
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#44-pipeline-and-evaluation-modules
  - 02_New_Benchmark_Widget/description.md#11-per-mode-payload--runstartevent
  - 10_Domain_and_Data/01_DOMAIN_MODEL.md#7-run-snapshot-and-immutability
  - 10_Domain_and_Data/01_DOMAIN_MODEL.md#35-benchmarktask
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#63-how-the-output-feeds-the-pipeline
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#14-task-file-loader
  - 05_Result_Widget/state_machine.md#3-per-tab-data-lifecycle
  - 05_Result_Widget/description.md#12-event-bus-integration
modules:
  - ui/new_benchmark/
  - backend/benchmark_pipeline/
  - backend/performance_task_generator/
  - backend/task_files/
  - ui/results/
acceptance_criteria:
  - STORY-085-AC-1
  - STORY-085-AC-2
  - STORY-085-AC-3
  - STORY-085-AC-4
  - STORY-085-AC-5
  - STORY-085-AC-6
  - STORY-085-AC-7
edge_cases: []
depends_on:
  - STORY-081
  - STORY-083
adrs: []
owner: coder
estimate: L
---

# STORY-085 — Drive a complete benchmark run from the UI through the real pipeline with fake providers

## Goal

Make a benchmark started from the user interface actually run, and make its results actually
appear. Today a run launched from New Benchmark settles `COMPLETED` with zero result rows and
issues no provider call at all, because nothing in production ever stages the run's tasks; and
even when rows exist, the Result surface keeps showing its empty state until the user changes
the selection. This story closes both production gaps and then proves the whole path with a
`pytest-qt` end-to-end test that starts a run from the New Benchmark UI against a faked provider
surface, drives the real dispatcher thread and the real five-phase pipeline (including the
judge), persists results, and asserts the Result surface reflects them — all fully offline.

### Why this story grew from test-only to feature + test

STORY-085 was originally written as a test-only story. Tracing the real code turned up two
production defects that make its acceptance criteria unachievable as written, so the repository
owner expanded this story to cover both fixes rather than splitting them out.

**Gap 1 — a run started from the UI has no tasks.**
`backend/benchmark_pipeline/_internal/lifecycle.py::_prepare_and_persist_run` reads its tasks
back out of `TasksStore` to build the initial result rows, but nothing in production ever writes
them:

```python
run_id = self._runs_store.create_run(run)
run = msgspec.structs.replace(run, run_id=run_id)
tasks = self._tasks_store.list_tasks(run_id)          # always empty
initial_results = _build_initial_results(run=run, tasks=tasks)
```

The method's own docstring admits `TasksStore` is "assumed to already carry this run's frozen
task rows, staged by a future New-Benchmark use case that does not exist yet".
`RunStartRequest.task_paths` and `RunStartRequest.performance_config` are assembled by the UI,
passed into `start()`, and never read. `make_performance_task_generator` is never called anywhere
in production. So a UI-started run settles `COMPLETED` with zero rows and makes no provider calls
at all.

**Gap 2 — the Result surface never repopulates when a run finishes.**
`ui/results/_internal/controller.py::_on_run_terminal` does not refresh the tabs, and
`_sync_details_tab` short-circuits when the run context is unchanged.
`SIGNAL_SUMMARY_DATA_CHANGED` / `SIGNAL_DETAILED_DATA_CHANGED` are declared and subscribed but
have no production emitter.

## In scope

- **Task 1 — stage a run's tasks at run creation** (`backend/benchmark_pipeline/`, consuming
  `backend/performance_task_generator/` and `backend/task_files/`). A new `RunTaskStager`
  Protocol turns a `RunStartRequest` into the run's frozen `BenchmarkTask` tuple, and
  `_prepare_and_persist_run` persists it before building the initial result rows. Full design
  below.
- **Task 2 — repopulate the Result surface when a run reaches a terminal status**
  (`ui/results/`). `_on_run_terminal` recomputes the Summary, Details and Charts tabs directly.
  Full design below.
- **Task 3 — the end-to-end proof.** One `pytest-qt` end-to-end test module under `tests/e2e/`
  that:
  - builds the wired application through `build_app` (reusing `tests/e2e/conftest.py`'s
    `build_smoke_app` / `offline_app_data_root` / `shutdown_handle` fixtures) and starts a run
    from the New Benchmark UI;
  - lets the real `pipeline-dispatcher` thread and the real benchmark/evaluation pipeline execute
    the run to a terminal status, including the judge layer for a graded run;
  - asserts the results are persisted and that the Result widget renders the persisted result
    rows.
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

- **A provider-injection seam in `build_app`.** Still out. The end-to-end test fakes the provider
  at the transport level (above); `build_app`'s inline `client_builders` mapping is not touched.
- **Emitters for `SIGNAL_SUMMARY_DATA_CHANGED` / `SIGNAL_DETAILED_DATA_CHANGED`.** These two
  signals deliberately stay emitter-less in this story. Wiring them would insert the 250 ms
  event-bus debounce (`05_Result_Widget/description.md` §12) between run completion and a visible
  table, for no benefit over the direct recompute Task 2 performs. Making the Result surface
  fully event-driven — live per-row repaint during a run, not just at terminal — is a **worthy
  follow-up story** and should be written as one; it is not this story's job.
- **Renaming the run-creation entry point to `make_run_creation_use_case`.** The
  `backend/benchmark_pipeline/` row of `01_MODULE_INVENTORY.md` §4.4 names
  `make_run_creation_use_case` on its public-surface list, and no symbol of that name exists in
  the code. This story satisfies the *behaviour* that row describes — freezing the run's tasks at
  run creation — via `RunTaskStager` inside the existing `start()` path. Reconciling the named
  symbol with the code (rename, add, or correct the inventory) is a separate concern to raise with
  the owner; do not rename anything as part of this story.
- The launch/idle/shutdown smoke path and the `NOT_READY` degraded-launch path — owned by
  STORY-081; this story starts and completes an actual run instead.
- Any change to the evaluation phases, the widgets other than `ui/results/`'s terminal handler, or
  `compose.py` beyond the one new `task_stager=` wiring argument.
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
- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#44-pipeline-and-evaluation-modules` — the
  `backend/benchmark_pipeline/` row: this module "hosts the cross-module use cases (run creation,
  …) and the `PerformanceTaskGenerator`", "never raises to its caller", and `start` is
  fast-synchronous. That row is the authority for putting task staging inside this module and for
  the requirement that a `TaskFileError` becomes a failed run, not a raise.
- `02_New_Benchmark_Widget/description.md#11-per-mode-payload--runstartevent` — the payload the UI
  builds: `task_paths` (task-file paths; empty in `SYNTHETIC`) and `performance_config` (matrix
  config if `SYNTHETIC`, else null). These are exactly the two fields the stager reads, and this
  clause fixes which one is populated in which mode.
- `10_Domain_and_Data/01_DOMAIN_MODEL.md#7-run-snapshot-and-immutability` — "Every task is copied
  verbatim into `benchmark_tasks` and its keyword lists into `benchmark_task_terms`" at run
  creation, and "One `benchmark_results` row is created per `(task, provider, model)`
  combination". This is the clause the current code violates by staging nothing.
- `10_Domain_and_Data/01_DOMAIN_MODEL.md#35-benchmarktask` — `BenchmarkTask` is "**Created by:** the
  run-creation use case, which copies each task into the database at run creation" and is "frozen
  at run creation"; `task_origin` is `FILE` for a YAML-loaded task and `SYNTHETIC` for a
  matrix-generated one.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#63-how-the-output-feeds-the-pipeline`
  — "The run-creation use case calls `generate` exactly once while building a `SYNTHETIC` run. The
  returned tasks are persisted as `benchmark_tasks` rows"; §3 of the same document fixes the count
  at `len(input_sizes) × len(output_sizes) × repeats`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#14-task-file-loader` — the loader is
  loader-tolerant (a malformed individual task is skipped with a logged warning, never raised),
  de-duplicates by `task_id` with first occurrence winning, and raises `TaskFileError` **only** for
  a file that cannot be read or parsed as YAML at all. Its threading note names the run-creation
  use case as the caller.
- `05_Result_Widget/state_machine.md#3-per-tab-data-lifecycle` — a tab moves
  `EmptyState → Loaded` when data for the selected run first exists. A run finishing with rows
  persisted is exactly that transition, and today it never happens.
- `05_Result_Widget/description.md#12-event-bus-integration` — `_run_finished`, `_run_stopped` and
  `_run_failed` are subscribed signals of the Result widget; this is the handler the refresh hangs
  off.

## Design constraints

### Design — task staging

Add a **pure** `RunTaskStager` Protocol to `backend/benchmark_pipeline/protocols.py`:

```python
def build(self, request: RunStartRequest, /) -> tuple[BenchmarkTask, ...]: ...
```

Implement it in `backend/benchmark_pipeline/_internal/task_staging.py`, holding two
already-implemented collaborators — `PerformanceTaskGenerator` and `TaskFileLoader`:

| `request.run_mode`                | Behaviour                                                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RunMode.SYNTHETIC`               | `PerformanceTaskGenerator.generate(request.performance_config)`. A `None` `performance_config` yields `()`.                                             |
| `RunMode.TASKS`, `RunMode.GRADED` | For each path in `request.task_paths`, `TaskFileLoader.load(path)`; concatenate in path order; de-duplicate by `task_id`, keeping the first occurrence. |

Error handling. `TaskFileLoader.load` raises `TaskFileError` (a `UserError` leaf) for a file that
cannot be read or parsed as YAML at all. That exception **must be caught and surfaced as data —
never raised out of `start()`**. The `backend/benchmark_pipeline/` inventory row is explicit that
this module "never raises to its caller". A per-task content problem is not an error at all here:
the loader already skips it with a logged warning.

**How it is surfaced — resolved during implementation.** Staging runs *before* the run header is
created, so there is no `run_id` to settle `FAILED` against. `start()` therefore treats an
unreadable path exactly the way it already treats a held single-inference gate: emit
`_run_start_failed` (`RunStartFailedEvent`, `ErrorKind.OTHER`, carrying the loader's message),
release the gate, and return the no-run-created sentinel. Both paths share one
`_reject_run_start` helper. The rejected alternative — create a run header purely to mark it
`FAILED` — would leave a junk row in the run list for a run that never executed anything.

Ordering. `_prepare_and_persist_run` is reordered so the tasks are known **before** the run header
is created. That is what makes `total_tasks` derivable at insert time instead of the currently
hard-coded `0` and the stale in-code note about `RunStatusPatch` having no `total_tasks` field.

> **Resolved during implementation — `total_tasks` is the result-row count, not the task count.**
> The original plan said `total_tasks = len(staged)`. Two spec surfaces say otherwise and agree
> with each other: `10_Domain_and_Data/01_DOMAIN_MODEL.md` §2 defines `benchmark_runs.total_tasks`
> as "expected `benchmark_results` rows", and `08_Cross_Cutting/08-Q_event_payload_schemas.md`
> defines the `_run_started` payload's `total_tasks` as "Count of `BenchmarkResult` rows the run
> will produce". The code agrees too: `completed_tasks` is computed by counting terminal *result
> rows*, so a task-count denominator would report progress as 6/3 on a three-task run across two
> test models. Shipped as `len(staged) × len(request.test_models)`, which is exactly the row count
> `_build_initial_results` produces. Flagged to the owner as a deviation from the written plan.

Wiring. `make_benchmark_pipeline` gains one keyword-only argument, `task_stager: RunTaskStager`.
`compose.py` constructs it from `make_performance_task_generator()` and `make_task_file_loader()` —
both already exist and are already exported from their modules' package roots.

**Accepted trade-off — a file read on the GUI thread.** `start()` is fast-synchronous on the GUI
thread (`01_MODULE_INVENTORY.md` §4.4) and `TaskFileLoader.load` is documented as blocking, so
staging inside `start()` means a brief local file read on the GUI thread. This is accepted:
`start()` already performs three database writes on that thread; the files were just read when the
user added them in New Benchmark, so they are OS-cached; and task-file counts are small. The
rejected alternative was carrying the already-loaded tasks on `RunStartRequest`, which would widen
a cross-boundary DTO for a marginal gain. Do not re-litigate this — it is settled.

### Design — Result refresh

In `ui/results/_internal/controller.py::_on_run_terminal`, call `self._summary_tab.recompute_and_push()`,
`self._details_tab.recompute_and_push()` and `self._charts_tab.recompute_and_push()` directly. All
three methods are already public on the concrete tab controllers.

**Do not implement this by clearing `_details_tab_context`** (or the summary/charts equivalents) to
defeat the change-detection short-circuit. That route goes through `set_run_context`, which resets
`_selected_result_id = None` — so a user who has a Details row selected when the run finishes would
silently lose their selection. Recomputing directly keeps the selection intact.

**Which test actually proves this — corrected during implementation.** The plan predicted that
deleting the three `recompute_and_push()` calls would fail the end-to-end
`test_result_widget_reflects_persisted_results`. It does not, and the negative control was run to
confirm that: against an instant wire stub a one-task run reaches its terminal state before the
queued `_run_started` event is delivered to the GUI thread, so the run-start `set_run_context`
already renders the *final* rows and the table is correct with or without the fix. The
negative-controlled proof is therefore the colocated
`ui/results/tests/test_controller.py::test_run_terminal_recomputes_summary_details_and_charts`,
which drives the events in the order a real, slower run produces them and does fail without the
fix. The e2e test still asserts the terminal cell values (Verdict `PASS`, Status not pending)
rather than only the row count, since row count alone is satisfied by the run-start render.

### Discovered during implementation — the embedding client was never given its model

The end-to-end test found a third production defect, not predicted when this story was written:
**no `GRADED` run with a golden answer could ever succeed in the real application.**

`OpenAICompatibleClient.embed` reads its model from `OpenAICompatibleClientSettings.embedding_model`,
and `compose.py` built every OpenAI-compatible client from the default settings bundle, where that
field is `None`. `embed` therefore raised before issuing any request, `EmbeddingService` degraded
that to an empty vector, and the DD-48 run-start embedding probe failed the run before a single
inference call — `run_analysis` reading "embedding endpoint cannot embed: the run-start probe
returned an empty vector". The field had **no assignment anywhere in production**; the models.py
docstring ("`embedding_model` is `None` for a client never used for `embed`") shows the composition
root was always meant to set it.

Fixed in `compose.py`: the `OPENAI_COMPATIBLE` builder partial now binds
`OpenAICompatibleClientSettings(embedding_model=<embedding.selected_model_name>)`. The field is read
only by `embed`, so binding the app-wide selection onto every OpenAI-compatible client changes no
other behaviour. Anthropic/Gemini embedding is untouched and out of scope here.

This is a scope addition beyond the two gaps this story was expanded for; it is included because
AC-1 through AC-4 are unreachable without it.

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

- `backend/benchmark_pipeline/`, `backend/performance_task_generator/` and `backend/task_files/` are
  Qt-free; the new `_internal/task_staging.py` imports no PySide6.
- `RunTaskStager` is declared in `backend/benchmark_pipeline/protocols.py` and re-exported through
  `api.py` — not in `_internal/`, which is unreachable to `compose.py`.
- The stager is pure: it takes a `RunStartRequest` and returns tasks. It performs no persistence,
  emits no events, and holds no mutable state; `_prepare_and_persist_run` owns the write.
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

### STORY-085-AC-5

Given a `RunStartRequest` whose `run_mode` is `RunMode.SYNTHETIC` and whose `performance_config`
declares `I` input sizes, `O` output sizes and `R` repeats,
when the run is started,
then `TasksStore.list_tasks(run_id)` returns exactly `I × O × R` persisted tasks for that run — one
per `(input size × output size × repeat)` combination.

### STORY-085-AC-6

Given a `RunStartRequest` whose `run_mode` is `RunMode.TASKS` or `RunMode.GRADED` and whose
`task_paths` names two readable task files holding disjoint tasks,
when the run is started,
then `TasksStore.list_tasks(run_id)` returns every task from both files, in `task_paths` order.

### STORY-085-AC-7

Given a Result surface currently showing a run whose result rows are already persisted, with no
change to the selected run and no user interaction,
when a run-terminal event (`_run_finished`, `_run_stopped` or `_run_failed`) is delivered,
then the Summary, Details and Charts tabs each re-read the persisted rows and push a refreshed view
model.

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
- STORY-085-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_task_staging.py`,
  `test_synthetic_run_stages_one_task_per_grid_cell`.
- STORY-085-AC-6 — unit, same file, `test_tasks_mode_stages_tasks_from_every_task_path`.
- STORY-085-AC-7 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_controller.py`,
  `test_run_terminal_recomputes_summary_details_and_charts` — additionally covered end to end by
  `test_result_widget_reflects_persisted_results` above.

Supporting coverage that proves no acceptance criterion but must exist before the story is done:
a `TaskFileError` from an unreadable path is surfaced as `_run_start_failed` and does not propagate
out of `start()` (extend the existing
`src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_never_raises.py`), and the terminal
refresh preserves a selected Details row rather than clearing it (same
`ui/results/tests/test_controller.py`).

Every end-to-end test must pass both under `just test-e2e` (offscreen) and under `just check` (native
platform). Run both before calling the story done.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-085.
- [ ] A run started from the New Benchmark UI in every mode persists a non-empty task set and issues
  at least one provider call.
- [ ] The new tests pass under `just test-e2e` (offscreen) **and** under `just check` (native
  platform), with no `QT_QPA_PLATFORM` set inside the test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The stale "SCOPE BOUNDARY (STORY-029 Task 9)" docstring and the `total_tasks` `NOTE` comment in
  `backend/benchmark_pipeline/_internal/lifecycle.py` are removed or corrected — a stale docstring is
  fixed in the same commit as the code it documents.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] The `total_tasks` reading flagged under "Design — task staging" has been raised with the owner.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report, including the follow-up story
  for emitting `_summary_data_changed` / `_detailed_data_changed`.

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
