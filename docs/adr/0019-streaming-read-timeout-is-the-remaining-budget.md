# ADR-0019 — Size the streaming read timeout to the call's remaining budget, and record that the specified heartbeat mechanism is unimplementable

**Status:** accepted
**Date:** 2026-08-19
**Deciders:** project owner, architect
**Supersedes:** —
**Superseded by:** —
**Relates to:** ADR-0006, ADR-0009, EC-RUN-19, SPEC-015, DD-51

## Context and problem statement

While building STORY-086's opt-in live tier against a real local Ollama, the implementer hit a
failure that could not be fixed the way the specification describes, and the finding was then
re-verified independently by the controller against the installed `openai` SDK source and this
repository's source.

**The specification names a mechanism, not just an outcome, and that mechanism cannot exist on
this stack.** Three clauses say the same thing:

- `08_Cross_Cutting/08-I_edge_cases.md:176` (EC-RUN-19) — the seconds counter "keeps increasing
  on every heartbeat emission (the client's **sub-second read timeout yields a heartbeat chunk**
  during provider silence)".
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md:117` — `chat_stream` yields "content +
  > =1 Hz heartbeat chunks"; `:140` (§6.2) — the non-streaming fallback "still yields >=1 Hz
  > heartbeat chunks while waiting (the body read uses the same **sub-second per-read socket
  > timeout**)".
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 — "the client's streaming read uses
  a sub-second per-read socket timeout, and on a read that elapses with no new content the
  iterator yields a heartbeat chunk".

On the `openai` SDK a read timeout does not pause the stream, it destroys it.
`openai/_streaming.py:108-110` ends `Stream.__stream__` with `finally: response.close()`, so an
`httpx.ReadTimeout` propagating out of that generator runs the `finally` and closes the HTTP
response. Measured against a stub that goes silent for 2 s and then resumes: one chunk arrives,
then `httpx.ReadTimeout` is raised at **0.502 s** with `response.is_closed` already `True`, and
the next `next()` returns `StopIteration` in **0.000 s**. The three chunks the server did send
afterwards were unreachable. Building the specified heartbeat on that timeout would therefore
convert a hard timeout into a silently truncated response scored as a success — strictly worse
than today's `FAILED_TIMEOUT`.

**The real failure does not even occur where the specification implies.** Ollama withholds HTTP
response headers until generation begins, and httpx's `read` timeout governs that header wait, so
the timeout is raised from the `create()` call, not from stream iteration. Measured on a cold
`granite4.1:3b`: with `read=0.5` the call fails at **0.505 s waiting for headers**; with
`read=120` the headers arrive at **1.083 s** and the largest gap between server-sent-event lines
after that is **0.033 s**. Driving the real production client with a 120 000 ms budget fails in
**0.67 s** with `HttpTimeoutError` (from `openai.APITimeoutError`) raised at
`backend/provider_openai_compatible/_internal/client_impl.py:137` — the `except` around
`create()` at `:114-130` — not in `chat_stream_impl.__next__`. A heartbeat added inside `__next__`
would have left the defect entirely unfixed while appearing to fix it.

So: what read timeout does the streaming call pass to the transport, given that the sub-second
value the specification prescribes buys nothing and actively breaks the call?

## Decision drivers

- **The finite-deadline invariant is non-negotiable.** `02_LLM_CLIENT_PROTOCOL.md` §6.3
  (SPEC-015) requires every client call path to pass a finite deadline to the transport; an
  infinite or absent transport timeout must not exist anywhere in a client. Whatever replaces
  `0.5` must still be finite.
- **The deadline must actually be enforceable.** The existing between-chunks elapsed check in
  `chat_stream_impl.__next__` cannot interrupt a thread blocked in a socket read; only a socket
  timeout can.
- **Nothing that works today may regress.** Any change has to be checked against what the
  progress emitter actually does, not against what the specification says it does.
- **A contradiction with an accepted specification clause is never resolved silently in code.**
  It gets recorded and escalated.

## Considered options

- Option A — Keep `_STREAM_READ_TIMEOUT_S = 0.5` and add heartbeat emission on `ReadTimeout`
  inside the stream iterator, as the specification describes.
- Option B — Set the streaming `read` timeout to the call's remaining adaptive budget
  (`ChatRequest.timeout_ms`), and treat a read timeout as the deadline expiring.
- Option C — Keep the sub-second read timeout only for the header wait and raise it after headers
  arrive, so the header phase stays responsive while the body phase gets the full budget.

## Decision outcome

Chosen option: **Option B.** The streaming `read` timeout is the call's remaining adaptive budget
(`ChatRequest.timeout_ms`) instead of the fixed 0.5 s. This is already being implemented under
STORY-086.

**Why this regresses nothing.** Progress emission is *already* strictly chunk-driven:
`backend/inference_progress/_internal/emit.py:98` is `for chunk in chat_stream:` with both
`_emit()` calls at `:103` and `:111` inside that loop. Zero chunks therefore means zero
emissions, today, with the 0.5 s read timeout in place. The "Waiting for first token — N.N s"
counter never ticked during provider silence, so widening the read timeout takes nothing away
from the user.

**Why this is strictly an improvement.** The per-call deadline becomes better enforced. The
between-chunks monotonic check in `chat_stream_impl.__next__` runs only when a chunk arrives and
so cannot interrupt a blocked read; a socket timeout set to the remaining budget can, and it
fires at the budget rather than at an arbitrary 0.5 s.

Option A is rejected because it is not implementable — the SDK closes the response before the
next `next()` can be issued, so the "resume after heartbeat" step the specification assumes does
not exist. Option C is rejected as unnecessary complexity for no user-visible gain: the header
wait is exactly the phase that legitimately takes many seconds on a cold local model, and there
is no consumer that benefits from failing it faster.

### Consequences

- **Positive** — The live tier can reach a cold local model instead of failing at 0.505 s. The
  transport deadline now equals the budget the Adaptive Timeout Service computed, and it is
  enforceable while the socket is blocked. Measured against real cold models: `gemma4:12b-mlx`
  went from `HttpTimeoutError` at 0.652 s to a completed reply at 7.101 s (ttft 7097 ms), and
  `granite4.1:3b` from 0.677 s to 11.830 s (ttft 11822 ms). `test_deadline.py`'s **assertions** are
  untouched: given the no-resumption result, the two tests in it pin behaviour that is correct for
  this SDK, and the earlier claim in `live-defects-found.md` that they pinned a specification
  violation is withdrawn. Only its docstring changed, because it named the now-deleted
  `_STREAM_READ_TIMEOUT_S` constant.
- **Negative — the worst-case wall-clock bound widens from `budget + 0.5 s` to `2 x budget`.** A
  provider that streams right up to the deadline and then goes silent passes
  `chat_stream_impl.__next__`'s between-chunks deadline check at `deadline - epsilon` and then blocks
  for a further full read timeout — 240 s at the 120 s production budget. The bound stays finite and
  deterministic, so SPEC-015 still holds, and both measured stall shapes landed at approximately
  1x budget (silent stub 1.648 s and dribbling stub 1.523 s, on a 1.5 s budget). Tightening it means
  re-arming the timeout inside `__next__` per chunk, which was out of scope here. Accepted
  deliberately; folded into STORY-120.
- **Negative — EC-RUN-19's user-visible promise is not delivered today and was never delivered.**
  There is no live, monotonically increasing "Waiting for first token — N.N s" counter during
  provider silence, because no timer-driven heartbeat exists anywhere in the application and the
  chunk-driven emitter cannot produce one. This decision does not create that gap and does not
  close it; it makes it visible. Closing it is STORY-120.
- **Negative — the gap was invisible to the test suite by construction.** EC-RUN-19's only mapped
  test is UI-side: `src/ollama_llm_bench/ui/progress/tests/test_current_task_controller.py:168`
  feeds `_inference_progress` events to the Current-task controller and asserts the rendering. It
  never exercises the client mechanism that is supposed to produce those events, so no amount of
  green suite could have caught this.
- **Neutral — the Anthropic adapter carries the identical construct, and its status is
  UNVERIFIED.** `backend/provider_anthropic/_internal/client_impl.py:49` declares the same
  `_STREAM_READ_TIMEOUT_S = 0.5` and `:115` passes it as the streaming `read` timeout. It is very
  likely the same latent defect. It is **not** asserted to be broken and **not** asserted to be
  fine: Anthropic is a cloud provider that could not be exercised during this work, so whether its
  transport withholds response headers until generation begins the way Ollama does has not been
  measured. STORY-120 establishes that behaviour before changing the constant.
- **Neutral — residual unknown across the other OpenAI-compatible backends.** Whether LM Studio,
  llama.cpp, OpenAI, and Azure also withhold headers until the first token is untested. The timing
  figures above are single-sample; the order of magnitude is the load-bearing part, not the digits.

## Recommendation to the owner — the specification text is now known to be wrong

`docs/v3_specification/` is read-only for automated sessions and **this ADR changes none of it.**
Three clauses — `08-I_edge_cases.md:176`, `02_LLM_CLIENT_PROTOCOL.md:117` and `:140`
(§6.2), and `04_EVALUATION_PIPELINE.md` §6.9 — describe a heartbeat mechanism that the chosen
SDK cannot provide. The outcome those clauses promise (a ≥ 1 Hz progress signal that keeps
advancing while the provider is silent) remains desirable and is worth building; the mechanism
they prescribe (a sub-second read timeout yielding a heartbeat chunk) is not available. The
recommendation is that the owner authorise a correction to the mechanism wording in those three
places, leaving the ≥ 1 Hz outcome intact. Until that happens, this ADR is the record of the
divergence, and STORY-120 delivers the outcome by a different mechanism.

## Pros and cons of the options

### Option A — Keep the 0.5 s read timeout, emit heartbeats on `ReadTimeout`

- Good — Matches the specification's wording verbatim; needs no spec escalation.
- Bad — Not implementable. `openai/_streaming.py:108-110` closes the response in the generator's
  `finally`, so the stream cannot be resumed after the timeout; measured, the next `next()`
  returns `StopIteration` in 0.000 s and already-sent chunks are stranded. Shipping it would turn
  a hard timeout into a silently truncated response scored as a success.

### Option B — Read timeout equals the call's remaining budget

- Good — Finite, so SPEC-015 still holds; enforces the real deadline even while blocked in a
  socket read; costs nothing, because emission was never read-timeout-driven in the first place.
- Bad — Removes the last trace of the specified heartbeat mechanism from the code, so the ≥ 1 Hz
  promise now has no implementation at all until a replacement is built.

### Option C — Sub-second timeout for the header wait, full budget after headers arrive

- Good — Keeps a fast failure signal for a genuinely unreachable endpoint.
- Bad — The header wait is exactly the phase that legitimately runs for seconds on a cold local
  model (measured 1.083 s on `granite4.1:3b`, and longer on a first load), so a sub-second bound
  there is the very defect being fixed. Two-phase timeout switching is not expressible through the
  single `httpx.Timeout` the SDK accepts per request without reaching into transport internals.

## Links

- Related ADRs: ADR-0006 (extracted the shared `emit_progress_during` helper into
  `backend/inference_progress/`), ADR-0009 (`tokens_estimated` on `InferenceProgressEvent`).
- Spec clauses: `docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-19;
  `docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.1, §6.2, §6.3
  (SPEC-015 finite-deadline invariant), §7 (`provider.connect_timeout_ms`);
  `docs/v3_specification/11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9;
  `docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §9, §11.
- Stories: STORY-086 (applies the read-timeout change), STORY-120 (delivers EC-RUN-19's outcome
  by a working mechanism and resolves the Anthropic construct).
