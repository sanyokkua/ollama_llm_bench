# ADR-0013 — Issue a dedicated lightweight liveness call as the circuit breaker's post-cooldown probe

**Status:** accepted
**Date:** 2026-07-28
**Deciders:** architect (finalization backlog)

## Context and problem statement

`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §6.6 (as currently worded in the file) describes
the breaker's post-cooldown "probe" as nothing more than the next real benchmark task the
dispatcher happens to route to a `PROBING` provider: the breaker admits it, the task runs the full
retry-laddered inference path, and whichever of the pipeline's several outcome-reporting call sites
handles that task decides whether to call `record_success` or `record_failure`. In production this
has a liveness gap: several of the dispatcher's error paths — a cancellation-adjacent branch, a
breaker-state guard exit, a task that errors before an outcome is ever classified — return without
calling either method. When one of those paths is what ends the admitted probe task, the breaker is
left in `PROBING` with a probe slot marked "handed out" but never resolved (§6.5's "subsequent
`should_skip` queries return `True` until the probe's outcome arrives"). No later task can ever
become a new probe, because no later task is ever admitted — `should_skip` keeps returning `True`
forever. The provider is now permanently unusable for the rest of the run, silently, with no cooldown
ever restarting and no error surfaced.

This is worse in the common case than it looks: a group in this pipeline is one `(provider, model)`
pair. A run against a single provider and a single model is one group. Once that group's provider
trips, every remaining row for that group is skipped by `should_skip` in milliseconds — there is no
further group boundary at which anything re-evaluates the provider, and no natural place left in the
run for a probe candidate to appear. A multi-model run against the same provider is not much better:
each subsequent model's first row is a plausible probe candidate only if it happens to land on one of
the reporting paths that actually calls back into the breaker, which is exactly the set of paths this
bug shows is incomplete.

The product owner already decided the core fix, recorded as DD-71 in
`08_Cross_Cutting/08-F_spec_issues_log.md` (2026-06-06, Q7/SPEC-108): the probe becomes "the
single-attempt, single-short-budget warmup-style call (DD-64), not a full benchmark task on the
retry-laddered inference path," so a still-down provider's re-trip is decided in seconds rather than
the minutes a `(1+retry_count)×`-escalating real task would cost. DD-71 names its own affected spec
areas as `08_CIRCUIT_BREAKER.md` §intro, §6.x, and the state table — but the file was never actually
edited to match everywhere DD-71 names. §1 (Purpose) and §5 (Postconditions), and part of §6.2's state
table, already carry DD-71's language verbatim. §6.5 and §6.6's own probe-behaviour walkthrough
(quoted above) still carry the older, pre-DD-71 description of a real task as the probe. This split —
some sections correctly updated, most not — is itself something a later reader needs a rule for, not
just a one-off correction.

This ADR does not re-decide anything DD-71 already settled: the probe is, and stays, a dedicated
lightweight liveness call, not a real task. What DD-71 left open, and what a coder implementing the
fix cannot get from either DD-71's one paragraph or the still-mixed prose in `08_CIRCUIT_BREAKER.md`,
is: (1) which text governs when the two disagree, (2) exactly which breaker method the probe calls for
each concrete outcome, (3) whether "single-attempt" means what the existing warmup call actually does
in code, and (4) at what granularity in the dispatcher the probe fires. Those four questions are this
ADR's scope.

## Decision drivers

- **DD-71 is binding and is not re-litigated here.** Where `08_CIRCUIT_BREAKER.md`'s prose has not
  caught up to a dated, affected-areas-scoped product-owner decision in
  `08-F_spec_issues_log.md`, the DD entry governs and the stale prose is superseded-in-place — a
  general rule, because this will not be the only partial propagation in this spec tree.
- **The invariant the current bug violates must hold going forward:** no exit path other than
  cancellation may leave a provider parked in `PROBING` with no future event able to resolve it.
  Every branch that can end a probe attempt must report exactly one of `record_success` /
  `record_failure`, or explicitly re-raise cancellation and report nothing.
- **The probe's cost must actually be bounded in seconds**, per DD-71's own stated purpose — a
  probe shape that silently reintroduces the retry-laddered path's multi-minute worst case defeats
  the decision even while nominally satisfying "use `run_model_warmup`."
- **The probe must fire at a grain the dispatcher actually revisits.** A per-group hook does not
  exist for the single-group case that is the most common repro of this bug (one provider, one
  model): once that group trips, no later group boundary ever occurs to notice the cooldown has
  elapsed.

## Considered options

- **Option A — Keep the real-task-as-probe design; just fix every dispatcher path so it always
  reports an outcome.**
- **Option B — A dedicated, single-attempt lightweight probe call, invoked per row (chosen).**
- **Option C — A dedicated lightweight probe call that reuses the warmup call's full retry ladder
  as-implemented (`with_retry` + `default_transient_policy(retry_count=...)`).**
- **Option D — A dedicated lightweight probe call, but triggered only from the existing per-group
  warmup hook instead of on every row.**

## Decision outcome

Chosen option: **Option B**. `provider_probe.py` (module
`src/ollama_llm_bench/backend/benchmark_pipeline/_internal/provider_probe.py`) exposes:

```python
def run_provider_probe(
    *,
    provider_id: ProviderId,
    model_name: ModelName,
    provider_registry: ProviderRegistry,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
    runner: TaskRunner[ChatResponse],
    token: CancellationToken,
) -> None: ...
```

**1. Precedence.** For every clause in `08_CIRCUIT_BREAKER.md` that DD-71's "Affected spec areas"
names (§intro/§1, §6.x, the state table in §6.2) but that still carries pre-DD-71 prose — concretely
§6.4's warmup-timeout paragraph, §6.5, and §6.6's probe-behaviour walkthrough — DD-71's decision
governs and the stale prose is treated as superseded-in-place. This is a general rule for this spec
tree, not specific to the circuit breaker: whenever a dated `08-F_spec_issues_log.md` entry names a
spec area as affected, that entry is authoritative for that area even where the file's own prose was
never edited to match, until someone does correct the file. Do not resolve such a conflict by
re-reading the stale prose as if it were still current.

**2. The outcome map.** `run_provider_probe` reports to the breaker as follows:

| Outcome                                                                                                                     | Breaker call             | Why                                                                                                                                                                                                                                                           |
| --------------------------------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A chat response comes back (any completion, including a model-side error the LLM itself produced)                           | `record_success`         | The provider answered — DD-64's rule that any response is a liveness signal, restated for the breaker call site.                                                                                                                                              |
| `HttpTimeoutError`, `HttpConnectionError`                                                                                   | `record_failure`         | No response of any kind — the provider is genuinely unreachable or wedged; re-trip with a fresh cooldown.                                                                                                                                                     |
| Any other `AppError` originating in a provider *response* (401, 404, 400, 422, 429, 5xx, etc.)                              | `record_success`         | §6.4's own rule: "any response — including a `4xx` — proves the provider is alive." The request/model was the problem, not the provider's reachability; a still-broken provider re-accumulates ordinary task failures to the threshold on its own.            |
| `ConfigurationError` / `MissingEnvVarError` raised by `provider_registry.get_client()` before any network call is attempted | `record_failure`         | Nothing was ever sent — this is not evidence the provider is alive, and the pre-cooldown state (a config problem, not a transient network problem) is unchanged, so there is nothing to probe repeatedly for; treat it the same as a hard connection failure. |
| `TaskCancelledError`                                                                                                        | Re-raise; report nothing | A user pause/stop must never trip or close a breaker (§6.4's existing cancellation rule, extended to the probe).                                                                                                                                              |

This redefines §6.6 step 4's "neutral" outcome. Under the old real-task design, a `FAILED_INFERENCE`
or `ERRORED` result was neutral because the breaker stayed `PROBING` and *the next task the pipeline
happened to route* became the new probe candidate — "neutral" meant "wait for something else to
decide it." With a dedicated probe there is no next-task candidate to wait for: the probe call itself
is the only chance to decide. The table above resolves what was neutral into a decided outcome: any
answer at all — including a 4xx-shaped `AppError` a model-side error would previously have made
neutral — now closes the breaker via `record_success`, per row three's rationale. There is no
"neutral, try again next time" outcome left in this design outside cancellation, which is what
guarantees the closing invariant below.

**Resulting invariant:** no exit path from `run_provider_probe` other than `TaskCancelledError`
leaves the provider in `PROBING`. Every other branch reaches exactly one of `record_success` or
`record_failure` before returning. This is the property the current bug lacks, and the property the
four implementation stories (STORY-100..103) must each preserve.

**3. One-attempt shape.** DD-71 describes the probe as "the single-attempt, single-short-budget
warmup-style call (DD-64)" — but the warmup call as actually implemented today
(`warmup.py:116-118`, `run_model_warmup`) wraps its single inner attempt in the full transient-retry
ladder: `with_retry(_one_attempt, policy=default_transient_policy(retry_count=retry_count), token=token)`.
`with_retry`'s `total_budget` (60 s) bounds only the cumulative *backoff sleep time* between attempts
— it does not bound any individual attempt's own network call, which is separately sized by
`adaptive_timeout.next_budget(...)` and can itself run to the role's configured maximum. Reusing that
implementation verbatim as the probe would mean a probe against a genuinely wedged provider can still
make several sequential attempts, each escalating its own timeout, and burn minutes — exactly the
outcome DD-71 exists to prevent. DD-71's own text ("single-attempt") wins over the literal current
shape of the DD-64 warmup call it points to (per the precedence rule in item 1, applied here to a
disagreement between two DD entries rather than a DD entry and stale prose): `run_provider_probe`
makes **exactly one** network attempt — no `with_retry`, no backoff, no second attempt on failure.
`retry_count` is not used to drive a retry loop here; it is used only to select where on the
adaptive-timeout ladder the probe's single budget is drawn from
(`adaptive_timeout.next_budget(provider_id, model_name, AdaptiveTimeoutRole.INFERENCE, attempt_index=1 + retry_count)`),
so the one attempt gets the same generous, top-of-ladder budget a real task's *last* retry attempt
would have received, rather than being cut off at the ladder's smallest first-tier budget. This gives
a merely slow-but-alive provider a fair chance to answer within one call, while a genuinely wedged
provider still fails in one budget's worth of wall time, not several.

**4. Per-row, not per-group, invocation.** `run_provider_probe` is called from the dispatcher's
per-row loop — immediately before routing a row whose target's provider is `PROBING`, in place of
what would otherwise be `should_skip`'s admission of that row as a real-task probe — not from the
per-group model-switch warmup hook that `run_model_warmup` already occupies. A group in this pipeline
is one `(provider, model)` pair; a run targeting one provider and one model is a single group. Hanging
the probe off the per-group hook would mean that once that one group's provider trips, there is no
second group boundary left in the run for anything to ever re-invoke the hook — the exact half-fixed
state this ADR exists to avoid, just moved from "no real task is ever admitted again" to "no warmup
call is ever issued again." Firing per row means every remaining row against a `PROBING` provider is a
fresh opportunity to resolve the cooldown, regardless of how many distinct models the run targets.

### Consequences

- Positive — Closes the liveness gap: with the outcome map's totality (item 2) and the per-row
  invocation (item 4), the invariant in item 2 holds regardless of which dispatcher branch is hit,
  including the single-group, single-model repro case that is unfixable under the old per-group or
  real-task designs.
- Positive — Bounds probe cost to one budget's worth of wall time even against a wedged provider
  (item 3), delivering DD-71's "seconds, not minutes" property in the actual implementation, not just
  in the DD-71 text.
- Positive — `ui/progress/protocols.py:116`'s already-declared `manual_provider_probe()` — currently a
  UI-side hook with no backend behind it — gains a natural backend implementation: the same
  `run_provider_probe` the breaker's own post-cooldown transition uses can be invoked on demand for a
  user-triggered manual probe. This is noted here as a consequence available to a future story, not as
  work done by this ADR or its four cited stories.
- Negative — Introduces a fourth call shape into the breaker/adaptive-timeout/warmup family
  (`run_task_with_stability` for ordinary rows, `run_model_warmup` for model-switch warmup,
  `run_provider_probe` for breaker recovery, plus the Readiness Service's own unrelated
  `probe_health`), which is one more thing a future maintainer needs to keep straight; the module
  docstring and the four stories carry the responsibility of distinguishing them clearly.
- Negative — Because the probe reports `record_success` for a 4xx-shaped `AppError` (item 2, row 3),
  a provider that is up but permanently misconfigured for every model (e.g. a bad model name repeated
  across the whole run) will bounce out of `PROBING` back into ordinary service on every cooldown
  cycle, re-accumulate `failure_threshold` ordinary failures, and re-trip — a real but accepted cost of
  DD-71's own liveness-not-correctness framing, not something this ADR introduces.
- Neutral — `08_CIRCUIT_BREAKER.md` and `08-F_spec_issues_log.md` are vendored and unchanged; this ADR
  is the record of how DD-71 is implemented, not a spec edit. The stale §6.4/§6.5/§6.6 prose remains in
  the file until a future documentation pass corrects it in place; until then, item 1's precedence rule
  governs how it is read.

## Pros and cons of the options

### Option A — Keep the real-task probe; fix every dispatcher reporting path

- Good — No new probe call shape; smallest structural diff to the dispatcher.
- Bad — Contradicts DD-71 outright, which already rejected a real task as the probe specifically
  because of its `(1+retry_count)×`-escalating worst-case cost. Also structurally fragile: "every
  path reports an outcome" is exactly the invariant that was already supposed to hold and did not —
  nothing about this option makes the next dispatcher change less likely to reintroduce an unreported
  path.

### Option B — Dedicated single-attempt probe, invoked per row (chosen)

- Good — Matches DD-71 literally; bounded, predictable cost; the invariant in the outcome map (item
  2\) is enforced by one small function's own exhaustive `except` structure rather than by discipline
  spread across every dispatcher branch; fires at a grain (per row) that always exists, including the
  single-group case.
- Bad — A new module and a new call shape to build, document, and keep distinct from
  `run_model_warmup`.

### Option C — Dedicated probe reusing the warmup call's full retry ladder verbatim

- Good — Reuses existing, already-tested code (`with_retry`, `default_transient_policy`) with no new
  attempt-budgeting logic.
- Bad — Does not actually bound probe cost to seconds, because `with_retry`'s `total_budget` bounds
  only inter-attempt backoff, not any attempt's own network time; against a genuinely wedged provider
  this can still run to several times the role's per-attempt maximum, reproducing the multi-minute
  cost DD-71 exists to eliminate.

### Option D — Dedicated probe triggered from the per-group warmup hook only

- Good — Reuses an invocation point that already exists (`run_model_warmup`'s call site) with no new
  dispatcher wiring.
- Bad — Leaves the bug half-fixed for exactly the case most likely to trigger it: a run against one
  provider and one model is one group, so once that group's provider trips there is no later group
  boundary for anything to ever re-invoke the hook, and the cooldown's expiry is never noticed.

## Links

- Spec clauses: `docs/v3_specification/11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §1, §5,
  §6.2, §6.4, §6.5, §6.6, §6.9; `docs/v3_specification/08_Cross_Cutting/08-F_spec_issues_log.md`
  DD-71, DD-64.
- Stories: STORY-100, STORY-101, STORY-102, STORY-103.
