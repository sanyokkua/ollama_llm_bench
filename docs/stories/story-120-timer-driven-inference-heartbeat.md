---
id: STORY-120
title: Deliver the live waiting-for-first-token counter with a timer-driven heartbeat and resolve the Anthropic streaming read timeout
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-RUN-19
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#69-live-inference-progress-emission
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#61-the-unified-contract
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#62-transport-streaming-and-time-to-first-token
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation
  - 04_Progress_Widget/description.md#711-inference-progress-sub-row-context--benchmark_task
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#9-ui-update-coalescing
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#11-concurrency-stack-stdlib--qt-only--no-asyncio-no-anyio
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules
modules:
  - backend/benchmark_pipeline/
  - backend/provider_openai_compatible/
  - backend/provider_anthropic/
acceptance_criteria:
  - STORY-120-AC-1
  - STORY-120-AC-2
  - STORY-120-AC-3
  - STORY-120-AC-4
  - STORY-120-AC-5
  - STORY-120-AC-6
edge_cases:
  - EC-RUN-19
depends_on:
  - STORY-086
adrs:
  - ADR-0019
owner: coder
estimate: M
---

# STORY-120 — Deliver the live waiting-for-first-token counter with a timer-driven heartbeat and resolve the Anthropic streaming read timeout

## Goal

When a user starts a benchmark against a cold local model, the Progress widget is supposed to
show `Waiting for first token — N.N s` with the seconds ticking upward, so the user can tell the
model is alive rather than hung. **That counter has never ticked.** Progress emission is driven
entirely by chunk arrivals, and a model that has not begun generating sends no chunks, so during
exactly the wait the counter exists to cover, nothing is emitted and the display sits frozen at
its seeded `0.0 s`. This story makes the counter real by producing the progress heartbeat from a
timer rather than from chunk arrivals, and it settles the same latent transport bug in the
Anthropic adapter that ADR-0019 fixed in the OpenAI-compatible one.

## In scope

- **A timer-driven heartbeat inside the shared progress emitter.** `emit_progress_during(...)`
  (the helper specified once at `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 and
  extracted to `src/ollama_llm_bench/backend/inference_progress/` by ADR-0006) publishes an
  `_inference_progress` snapshot at least once per 1000 ms for the whole duration of the call,
  whether or not a chunk has arrived. All four callers — the per-task main inference, the per-task
  judge call, run-analysis generation, and provider test-inference — get this for free, because
  they all go through this one helper.
- **Teardown that is proven, not assumed.** Whatever concurrency primitive produces the cadence is
  stopped before `emit_progress_during` returns or raises, on every exit path: normal end of
  stream, a taxonomy exception from the client, and hard cancellation. No event may be published
  after the call has ended, and no thread may outlive it.
- **`backend/provider_anthropic/`'s streaming read timeout.** `_internal/client_impl.py:49`
  declares `_STREAM_READ_TIMEOUT_S = 0.5` and `:115` passes it as the SDK's streaming `read`
  timeout — the identical construct ADR-0019 replaced in the OpenAI-compatible client. This story
  first **measures** whether the Anthropic transport withholds response headers until generation
  begins (the behaviour that makes the 0.5 s bound a live defect on Ollama), records the
  measurement, and then applies the same budget-sized read timeout.
- **`backend/provider_openai_compatible/`'s read timeout, pinned by a test.** STORY-086 makes the
  change; this story adds the check that pins it, so the constant cannot silently return.

## Out of scope

- **Any edit under `docs/v3_specification/`.** That tree is read-only for automated sessions. Three
  clauses are now known to describe an unimplementable mechanism; ADR-0019 records that and
  recommends a correction, and the "Open spec conflict" section below repeats it for the owner.
  It is never resolved by editing the spec or by quietly changing behaviour in code.
- **The Progress widget's rendering of the row.** `ui/progress/`'s Current-task controller already
  renders sub-state A and sub-state B correctly from `_inference_progress` events — that is
  STORY-059's work, proven by
  `src/ollama_llm_bench/ui/progress/tests/test_current_task_controller.py:168`. The widget was
  never the problem; it was being fed nothing. No `ui/` module is touched.
- **`backend/provider_gemini/`.** It carries no `_STREAM_READ_TIMEOUT_S` construct (`grep`
  confirms the constant exists only in the OpenAI-compatible and Anthropic clients), so there is
  nothing to resolve there.
- **Changing `InferenceProgressEvent`'s shape.** The payload already carries `elapsed_ms`,
  `tokens_received`, `first_token_received` and `tokens_estimated` (ADR-0009). This story emits
  more of them, not different ones.
- **Repointing an existing `Proves:` line.** STORY-059 is `done`;
  `test_current_task_controller.py:168` keeps `Proves: STORY-059-AC-…`. Moving its proof onto this
  story's ids would leave a `done` story with an unproven criterion and redden `just trace-check`.

## Spec inputs

- `08_Cross_Cutting/08-I_edge_cases.md#EC-RUN-19` — the user-visible contract this story owes:
  while the provider is silent, the row stays in sub-state A and "the seconds counter
  (`Waiting for first token — N.N s`) keeps increasing on every heartbeat emission". Its "Avoid"
  list is binding too — no frozen seconds value, and `first_token_received` must never flip from
  `True` back to `False` (the flag is monotonic per call). **Read the parenthetical in this clause
  as describing an outcome, not a mechanism** — the mechanism it names is the one ADR-0019 shows
  cannot exist.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#69-live-inference-progress-emission` — the
  helper's authoritative specification: the ≥ 1 Hz cadence floor, the immediate emit the instant
  the first content token arrives, the counters-only payload (no response text ever crosses this
  boundary), the token-source preference order, and the rule that the accumulator stays local to
  the invocation. Everything in this clause except the sentence naming the read-timeout mechanism
  stays exactly as written.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#61-the-unified-contract` — the
  `chat_stream` row of the surface table, which is where the ">=1 Hz heartbeat chunks" obligation
  is placed on the client. Together with DD-51 it establishes that `chat_stream` is *the* chat
  execution surface and every user-visible call goes through `emit_progress_during(chat_stream(…))`,
  so fixing the helper fixes all four surfaces at once.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#62-transport-streaming-and-time-to-first-token` —
  the same heartbeat mechanism restated for the non-streaming fallback path, and the TTFT
  measurement rule that only the first **content-bearing** chunk trips `ttft_ms`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm` — the
  finite-deadline invariant (SPEC-015): every provider call path passes a finite deadline to the
  transport, and an infinite or absent transport timeout must not exist anywhere in a client.
  This is what AC-6 has to keep true while removing the 0.5 s constant.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation` — the
  hard-cancel contract the teardown has to survive: the abort hook closes the stream from the
  cancelling thread and the call raises `TaskCancelledError` within
  `provider.hard_cancel_max_ms` (default 2000 ms). A heartbeat that is still running at that
  point would publish an event for a call that no longer exists.
- `04_Progress_Widget/description.md#711-inference-progress-sub-row-context--benchmark_task` — the
  two sub-states and their exact strings, so the events this story emits carry what the existing
  renderer needs: sub-state A shows `Waiting for first token — N.N s` from `elapsed_ms / 1000`,
  sub-state B shows `Generating — N tokens · T.T s elapsed`.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#9-ui-update-coalescing` — the division of
  responsibility that makes a backend timer legitimate: the emission cadence (≥ 1 Hz) is a backend
  concern; the repaint cadence (≤ 1 per frame) is owned by the adapter/controller. Backend
  services never decide repaint timing and never import a Qt timer.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#11-concurrency-stack-stdlib--qt-only--no-asyncio-no-anyio` —
  the stack this story must build within: standard library `threading` / `concurrent.futures`
  plus Qt `QThreadPool` in the adapter layer only. `asyncio`, `anyio`, and `qasync` are absent by
  decision and blocked by a hook.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules` — no widget touched
  off the GUI thread; the shared mutable surface stays exactly two objects (the inference-activity
  gate and the single DB writer); everything else is single-owner.

## Design constraints

- **The concurrency design is an open question this story settles *before* implementation, not
  during.** See "Open design question" below. Write the chosen shape down and get it agreed
  first; do not start by editing `emit.py` and see what happens.
- **`asyncio`, `anyio`, and `qasync` are banned anywhere in `src/`** — a project decision (D-R-01)
  enforced by the `hookify:block-asyncio-imports` PreToolUse rule, which blocks the tool call
  outright. The heartbeat cannot be an async task, an event-loop callback, or a coroutine.
- **The emitter is Qt-free.** `backend/inference_progress/` sits in the Qt-free backend, so
  `QTimer` is not available to it either. The `import-linter` "Backend layer is Qt-free" contract
  fails the gate on a PySide6 import from any `backend/*` package.
- **Emission is chunk-driven today, and that is the whole defect.**
  `backend/inference_progress/_internal/emit.py:98` is `for chunk in chat_stream:` with both
  `_emit()` calls at `:103` and `:111` inside that loop. Zero chunks means zero emissions. The
  loop body's existing behaviour — the token-source preference, the accumulator, the
  first-token immediate emit, the `>= _EMIT_CADENCE_MS` check — is correct and stays; what is
  missing is a second source of wake-ups.
- **At most one LLM inference call is in flight app-wide**, enforced by the
  `InferenceActivityStore` gate and by `tests/architecture/test_ui_gate_access.py` and
  `test_stability_dispatcher_thread_only.py`. So there is at most one heartbeat alive at a time —
  the design does not need to scale, and anything that suggests it does is over-built.
- **The dispatcher thread and the single-inference gate are the highest-risk area in this
  codebase.** A leaked pipeline-dispatcher thread has already failed three tests and wedged
  `pytest` in `Py_Finalize` for eleven hours on this repository, un-root-caused. A heartbeat that
  outlives its call is the same class of bug. AC-5 exists specifically to make that failure
  visible in a fast test rather than in an eleven-hour hang.
- **The dispatcher blocks on `Future.result()` with no Qt event loop on its thread.** Nothing in
  the completion or heartbeat path may depend on a queued Qt signal being delivered to the
  dispatcher — the canonical anti-pattern in the concurrency standard.
- **The payload stays counters-only.** No portion of the model response text crosses the
  `_inference_progress` boundary, in a heartbeat snapshot or any other. The accumulator remains
  local to the helper invocation (§6.9 "Boundary discipline").
- **Time comes from the injected `Clock`.** The existing helper already reads
  `clock.monotonic_ms()`; a heartbeat that reads the wall clock directly, or sleeps against real
  time in a way the test suite cannot control, makes AC-1 untestable without a five-second sleep.
- **Do not weaken `provider.connect_timeout_ms`.** §7 fixes the connection-establishment timeout
  at 5000 ms independently of the per-call response deadline; AC-6 changes the `read` component
  only.
- **Establish the Anthropic transport behaviour before changing its constant.** Exercise
  `backend/provider_anthropic/` against the provider wire stub (`pytest-httpserver`, DD-56) with a
  server that withholds response headers, and record what the SDK does. If the measurement
  contradicts ADR-0019's expectation, stop and report rather than proceeding — this is new
  information about an accepted decision and is never resolved silently.

## Acceptance criteria

### STORY-120-AC-1

Given an in-flight `chat_stream` that has yielded no chunk of any kind since the call started,
when 5000 ms of `Clock` time have passed, then `emit_progress_during` has published at least one
`_inference_progress` event carrying `first_token_received == False` within each of the five
successive 1000 ms windows.

### STORY-120-AC-2

For every schedule of chunk arrivals and silent intervals within one call, each
`_inference_progress` event published for that call carries an `elapsed_ms` strictly greater than
that of the event published immediately before it for the same call.

### STORY-120-AC-3

For every schedule of chunk arrivals and silent intervals within one call, once an
`_inference_progress` event for that call has been published with `first_token_received == True`,
no later event for that call carries `first_token_received == False`.

### STORY-120-AC-4

After `emit_progress_during` has returned or raised, no further `_inference_progress` event is
published for that call, for each way the call can end:

| How the call ended                                                                         | What the helper does                                   |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| The stream ended normally and the trailing `ChatResponse` was returned                     | returns the response; emits nothing further            |
| The client raised a taxonomy exception (for example `HttpTimeoutError` on deadline expiry) | propagates the exception; emits nothing further        |
| The run's `CancellationToken` was hard-cancelled and `TaskCancelledError` was raised       | propagates `TaskCancelledError`; emits nothing further |

### STORY-120-AC-5

Within 100 ms of `emit_progress_during` returning or raising, the set of live threads reported by
`threading.enumerate()` is identical to the set observed immediately before the call, for each way
the call can end:

| How the call ended                               | Threads after the call        |
| ------------------------------------------------ | ----------------------------- |
| The stream ended normally                        | identical to the pre-call set |
| The client raised a taxonomy exception           | identical to the pre-call set |
| The run's `CancellationToken` was hard-cancelled | identical to the pre-call set |

### STORY-120-AC-6

Given a `ChatRequest` whose `timeout_ms` is `T`, when the client opens its streaming chat request,
then the transport `read` timeout it passes to the SDK is the finite value `T / 1000` seconds:

| Client                                                       | Read timeout passed to the SDK |
| ------------------------------------------------------------ | ------------------------------ |
| `backend/provider_openai_compatible/` (`make_openai_client`) | `T / 1000` seconds             |
| `backend/provider_anthropic/` (`make_anthropic_client`)      | `T / 1000` seconds             |

## Test plan

- STORY-120-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/inference_progress/tests/test_emit_progress_during.py`,
  `test_heartbeat_emits_at_least_once_per_second_while_the_provider_is_silent`. Uses a controllable
  `Clock` fake and a stub `ChatStream` that blocks without yielding, and a recording `EventBus`.
  Asserts per-window coverage, not a raw event count, so a burst of five events in one window
  fails the check.
- STORY-120-AC-2 — unit (property, `hypothesis`), same file,
  `test_elapsed_ms_is_strictly_increasing_across_consecutive_progress_events`. The strategy draws a
  list of `(silence_ms, chunk_or_none)` steps and replays it through the stub stream.
- STORY-120-AC-3 — unit (property, `hypothesis`), same file,
  `test_first_token_received_never_flips_back_to_false`. Same strategy as AC-2; asserts the flag's
  monotonicity per call. Covers EC-RUN-19's "Avoid" clause on the flag.
- STORY-120-AC-4 — unit (`@pytest.mark.parametrize`, one case per row, no loop in the body), same
  file, `test_no_progress_event_is_published_after_the_call_ends`. The cancellation row drives a
  real `CancellationToken` hard cancel; the exception row raises `HttpTimeoutError` from the stub
  stream.
- STORY-120-AC-5 — unit (`@pytest.mark.parametrize`, one case per row), same file,
  `test_no_thread_outlives_the_call`. Snapshots `threading.enumerate()` before and after and
  diffs the sets, so a leaked heartbeat thread names itself in the failure message.
- STORY-120-AC-6 — integration (`@pytest.mark.parametrize` over the two client factories),
  `tests/integration/test_stream_read_timeout_budget.py`,
  `test_streaming_read_timeout_is_the_calls_remaining_budget`. Drives each concrete client against
  the `pytest-httpserver` provider wire stub and asserts the `httpx.Timeout` the SDK received, so
  the check bites on the real request the client builds rather than on a constant's value.
- EC-RUN-19 — covered by STORY-120-AC-1 (the counter advances during silence) together with
  STORY-120-AC-3 (the flag never regresses). Per
  `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`, EC-RUN-19's mapped tiers are
  "unit; widget" across `ui/progress/` and `backend/benchmark_pipeline/`; the widget half is
  already proven by STORY-059 and is not re-proven here.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-120.
- [ ] EC-RUN-19 has a passing test on the backend side, in addition to STORY-059's widget-side test.
- [ ] The measured Anthropic header-withholding behaviour is recorded in the closing report, with
  the stub configuration that produced it — not asserted from the OpenAI-compatible result.
- [ ] `_STREAM_READ_TIMEOUT_S` no longer exists as a read timeout in either provider client, and
  every provider call path still passes a **finite** deadline to the transport (SPEC-015).
- [ ] `just check` is green, with the tail pasted and diffed against the baseline.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the three cited modules and for
  `src/ollama_llm_bench/backend/inference_progress/`.
- [ ] `just trace` then `just trace-check` pass with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged (see "Module-inventory note" below).
- [ ] The open spec conflict below is restated to the owner in the closing report, unresolved in
  code.

## Open design question — settle this before writing code

The specification's mechanism is gone, and its replacement is not obvious. The candidates, with
what each costs:

1. **One short-lived heartbeat thread per call.** `emit_progress_during` starts a
   `threading.Thread` that wakes on a `threading.Event.wait(1.0)` and emits a snapshot, and the
   `finally` sets the event and joins the thread. Simple and local. Cost: it creates a thread the
   concurrency standard's anti-pattern table warns about ("spawning a raw `threading.Thread` for a
   work unit"), even though this one is not a work unit; and the emitter now publishes from two
   threads, so the snapshot fields it reads need to be safe to read concurrently with the chunk
   loop writing them.
1. **One long-lived heartbeat thread owned by the composition root**, ticking whenever a call is
   registered with it. Avoids per-call thread churn and gives one place to join at shutdown. Cost:
   a second sanctioned standalone thread alongside the dispatcher (DD-38 currently names exactly
   one), which is an architecture change and needs its own agreement.
1. **Move the wake-up back into the transport**, by having the client's stream iterator yield a
   heartbeat chunk on a bounded read — the specification's own design, but implemented with an
   SDK-independent read loop rather than the SDK's `Stream` generator. Cost: it means not using
   `openai`'s streaming helper for the body read, which is a large, high-risk change to the
   busiest code path in the application.

Note that options 1 and 2 make the ≥ 1 Hz cadence a property of the **helper**, while the
specification places the "≥ 1 Hz heartbeat chunks" obligation on the **client**
(`02_LLM_CLIENT_PROTOCOL.md` §6.1's `chat_stream` row). Whichever is chosen, say so explicitly in
the closing report, because it changes which component owns the guarantee.

**Recommendation: option 1**, because at most one inference call exists app-wide, so per-call
thread churn is at most one thread per task, and because it keeps the change inside one module
with no lifecycle to wire into `compose.py`. AC-5 is what makes it safe. This is a recommendation,
not a ruling — the owner picks.

## Open spec conflict — owner ruling required

Three accepted clauses specify a heartbeat mechanism that the chosen SDK cannot provide:
`08_Cross_Cutting/08-I_edge_cases.md:176` (EC-RUN-19),
`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md:117` and `:140` (§6.2), and
`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9. Each states that the client's
sub-second read timeout yields a heartbeat chunk during provider silence.
`openai/_streaming.py:108-110` ends `Stream.__stream__` with `finally: response.close()`, so a
read timeout destroys the stream instead of pausing it — measured, after a `ReadTimeout` at
0.502 s the response is already closed and the next `next()` returns `StopIteration` in 0.000 s.

ADR-0019 records this and recommends the owner authorise a correction to the **mechanism** wording
in those three places while leaving the ≥ 1 Hz **outcome** intact. `docs/v3_specification/` is
read-only, so this story proposes no edit to it and must not resolve the conflict silently in
code. If the owner instead rules that the mechanism wording is binding, this story is not
implementable as scoped and option 3 in "Open design question" becomes the only path.

## Module-inventory note

The helper this story changes lives at `src/ollama_llm_bench/backend/inference_progress/`, which is
**not** a row in `14_Process_and_Traceability/01_MODULE_INVENTORY.md` — the module was created by
ADR-0006, which recorded the addition in the ADR rather than as a spec-file edit because the
inventory is vendored and read-only. The `modules:` front-matter therefore cites
`backend/benchmark_pipeline/`, the inventory row that owns the §6.9 helper's specification and its
original implementation, exactly as STORY-030 and STORY-035 did. This is a known inventory gap,
not a mis-citation; it is reported again here so it is not mistaken for one.

## Verification

Run in this order:

1. `uv run pytest src/ollama_llm_bench/backend/inference_progress -q -p no:randomly` — the
   emitter's own colocated suite, which is where five of the six criteria are proven and where a
   leaked thread shows up fastest.
1. `uv run pytest tests/integration/test_stream_read_timeout_budget.py -q` — AC-6 against the wire
   stub.
1. `uv run pytest src/ollama_llm_bench/backend/provider_anthropic src/ollama_llm_bench/backend/provider_openai_compatible -q`
   — both provider suites, which the read-timeout change can break.
1. `just check` — the full gate. This story touches the emitter that every inference call runs
   through, so the blast radius is the whole pipeline, not one module. **Budget roughly 30
   minutes**: this repository has a known teardown slowdown that keeps a full run near 100 % CPU
   throughout. A genuine hang shows near-zero CPU — use that to tell the two apart rather than the
   clock. Never run this concurrently with another full-suite run.
1. `just trace` then `just trace-check`.

## Negative controls

Prove each new assertion bites by falsifying the condition — never by deleting the assertion.

- **Heartbeat cadence.** Set the heartbeat interval to 60 s and re-run AC-1's test: it must go red,
  reporting the empty windows. Restore and confirm it passes again.
- **Teardown.** Remove the stop/join from the helper's `finally` and re-run AC-4 and AC-5: both
  must go red, and AC-5's failure must name the leaked thread. This is the single most important
  control in the story — a teardown test that passes with teardown deleted proves nothing.
- **Monotonic flag.** Make the emitter publish `first_token_received=False` once after the first
  token and re-run AC-3: the property test must shrink to a counterexample.
- **Read timeout.** Restore `read=0.5` in one client and re-run AC-6: only that client's
  parametrized case may fail, which also confirms the two cases are genuinely independent.
