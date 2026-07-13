---
id: STORY-027
title: Produce cached embeddings and the clamped Cosine Score over the embedding LLM client
status: done
spec_clauses:
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#62-producing-an-embedding
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#63-the-cosine-similarity-formula
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#64-the-comparison-and-the-single-threshold-dd-45
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#65-embedding-cache
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#7-configuration
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#8-error-handling
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#9-threading-and-concurrency
modules:
  - backend/embedding/
acceptance_criteria:
  - STORY-027-AC-1
  - STORY-027-AC-2
  - STORY-027-AC-3
  - STORY-027-AC-4
  - STORY-027-AC-5
depends_on:
  - STORY-001
  - STORY-004
  - STORY-017
owner: coder
estimate: M
---

# STORY-027 — Produce cached embeddings and the clamped Cosine Score over the embedding LLM client

## Goal

Give the evaluation pipeline a single shared embedding facade that turns text into a numeric
vector through the run's embedding `LLMClient`, computes the whole-text cosine similarity
between two texts as the clamped `[0.0, 1.0]` **Cosine Score**, looks up the single
`eval.cosine_threshold` from the run snapshot, memoises vectors in a bounded LRU cache so a
golden answer embedded once is reused across every test model in the run, and short-circuits
the whole cosine dimension run-wide after a configured number of consecutive embedding
failures. The service is the only producer of a numeric quality value in the application; it
decides no `PASS`/`FAIL` itself.

## In scope

- The `EmbeddingService` Protocol and its concrete implementation over the embedding-capable
  `LLMClient` port: producing an embedding vector for one normalised text (§6.2), the
  whole-text cosine similarity computation with the `[0.0, 1.0]` clamp and the zero-norm →
  `0.0` rule (§6.3), and the `eval.cosine_threshold` lookup from the frozen run snapshot
  (§6.4).
- The in-memory LRU cache keyed on `(provider_id, model_name, normalised_text)`, bounded by
  `eval.embedding_cache_max_entries` (default 4096), evicting the least-recently-used entry on
  overflow (§6.5), scoped to one service instance's lifetime.
- The consecutive-embedding-failure short-circuit (DD-70): after
  `eval.embedding_consecutive_failures_to_skip` consecutive embedding failures/timeouts
  (default 3) the service reports the cosine dimension as short-circuited run-wide and attempts
  no further embedding; a single success resets the consecutive counter (§7, §8).
- The `is_embedding_model` pure module function (embedding-model classifier) re-exported from
  `api.py`, and the `make_embedding_service` factory guarded by `icontract` on programmer
  invariants only, plus `backend/embedding/testing.py`.

## Out of scope

- The cosine **phase** (mapping the Cosine Score to `cosine_verdict` against the threshold and
  writing `ResultPatch` rows) and the keyword phase's per-term semantic check — owned by
  `backend/evaluation/` in STORY-028; this service returns the numeric score and the threshold,
  never a verdict.
- The run-start embedding fail-fast probe (`embed("probe")` under the `BENCHMARK_RUN` gate) and
  the capability probe under `PROVIDER_TEST` — orchestration owned by the pipeline (STORY-029)
  and the readiness/settings flows respectively; this service only exposes `embed`.
- The run-level "cosine produced zero scores" warning surfacing and the Progress-widget notice
  text — owned by the pipeline and UI phases; this service only exposes the short-circuit state.
- Rejecting an `ANTHROPIC` provider as the embedding provider — enforced by the run-creation use
  case (a pipeline concern), never by this service.
- Which `EmbeddingService` instance a resume gets (fresh vs reused) — a `compose.py` wiring
  decision; see the Design constraints note on cache lifetime.

## Spec inputs

- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#62-producing-an-embedding` — the
  normalise → cache-check → provider-call → cache-store sequence for one text.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#63-the-cosine-similarity-formula` — the
  dot/norms formula, the `[0.0, 1.0]` clamp, and the zero-norm → Cosine Score `0.0` rule.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#64-the-comparison-and-the-single-threshold-dd-45` —
  the whole-text (no sliding-window) comparison and the single `eval.cosine_threshold` lookup
  the service exposes.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#65-embedding-cache` — the
  `(provider_id, model_name, normalised_text)` key, the `eval.embedding_cache_max_entries` bound,
  and the LRU eviction.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#7-configuration` — the three snapshot keys
  and their defaults, the fixed (non-adaptive) `eval.embedding_timeout_seconds` budget, and the
  DD-70 consecutive-failure short-circuit.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#8-error-handling` — the per-request
  failure/timeout handling (degrade, do not raise) and the malformed/zero-norm-vector cases.
- `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#9-threading-and-concurrency` — the
  single-instance, single-accessor, lock-free, Qt-free, worker-thread-only contract.

## Design constraints

- `backend/embedding/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`CosineScore`, `CosineThreshold`, `ProviderId`, `ModelName`, `BenchmarkRunSettingEntry`),
  `backend/infra`, and the `LLMClient` Protocol (`01_MODULE_INVENTORY.md` §4.4). No PySide6.
- `embed` is blocking — a synchronous method invoked on a `TaskRunner` worker thread. Because
  execution is strictly serial (D-R-16) the service is a single-accessor structure: no cache
  lock, no in-flight-key handshake (§9).
- **Embedding return shape (gap resolution).** `EmbeddingService` exposes a raw-vector method
  `embed(text) -> tuple[float, ...]` (matching §3's output type, the DD-48 probe's
  `embed("probe")` shape, and the module inventory's stated public surface) *and* a
  `cosine(text_a, text_b) -> CosineScore` convenience that embeds both and applies §6.3; the
  keyword semantic-term check and the cosine phase both consume the raw-vector/`cosine` surface
  rather than each re-implementing the formula. The threshold lookup
  (`cosine_threshold() -> CosineThreshold`) is a separate method reading the snapshot; the
  service maps no score to a verdict.
- **The service does NOT consult the Adaptive Timeout Service** — every embedding call uses the
  fixed `eval.embedding_timeout_seconds` budget directly (DD-34, §7).
- **Cache lifetime (gap resolution).** The LRU cache lives for the lifetime of one
  `EmbeddingService` instance and is dropped when that instance is dropped; whether a resume
  receives a fresh instance is a `compose.py` decision, out of scope for this module. The
  consecutive-failure counter has the same instance lifetime.
- `icontract` on the `api.py` factory guards programmer invariants only — never a snapshot
  value, provider response, or user text.

## Acceptance criteria

### STORY-027-AC-1

For every pair of non-zero equal-length vectors, the computed Cosine Score equals the
mathematical cosine of the pair clamped into `[0.0, 1.0]`; the score is `1.0` for a vector
against itself, `0.0` for an orthogonal pair, `1.0` for a raw value above `1.0` from rounding,
and `0.0` whenever either input text embeds to a zero-norm vector.

### STORY-027-AC-2

Given a request to embed `(provider_id, model_name, text)`, when the same
`(provider_id, model_name, normalised_text)` key is requested a second time, then the cached
vector is returned and the underlying `LLMClient.embed` is called exactly once across the two
requests; text differing only by surrounding whitespace normalises to the same key.

### STORY-027-AC-3

Given an `eval.embedding_cache_max_entries` bound of `N`, when `N + 1` distinct keys are
embedded in access order, then the least-recently-used entry is evicted — a subsequent request
for the evicted key calls `LLMClient.embed` again while a request for a still-cached key does
not.

### STORY-027-AC-4

Given a run snapshot with `eval.embedding_consecutive_failures_to_skip = K`, when `K`
consecutive embedding calls fail or time out with no intervening success, then the service
reports the cosine dimension short-circuited run-wide and performs no further embedding call;
a single successful embedding before the `K`-th failure resets the consecutive-failure counter
so no short-circuit occurs.

### STORY-027-AC-5

Given a run snapshot carrying `eval.cosine_threshold`, `cosine_threshold()` returns that value
typed as `CosineThreshold`; and given a single embedding call that fails or times out, the
service surfaces the failure as a degraded outcome (no Cosine Score produced for that
comparison) and does not raise to its caller.

## Test plan

- STORY-027-AC-1 — property (Hypothesis over vector pairs) + unit for the fixed clamp/zero-norm
  cases, colocated `src/ollama_llm_bench/backend/embedding/tests/test_cosine.py`,
  `test_cosine_score_is_clamped_cosine` / `test_cosine_score_zero_norm_and_identity`.
- STORY-027-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/embedding/tests/test_cache.py`,
  `test_cache_hit_avoids_second_provider_call_and_normalises_whitespace`.
- STORY-027-AC-3 — unit, same file,
  `test_lru_evicts_least_recently_used_on_overflow`.
- STORY-027-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/embedding/tests/test_short_circuit.py`,
  `test_consecutive_failure_short_circuit_and_success_resets_counter`.
- STORY-027-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/embedding/tests/test_threshold_and_failure.py`,
  `test_threshold_lookup_and_failure_degrades_without_raising`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-027.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/embedding/`.
- [x] An architecture test confirms `backend/embedding/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-027.
- [x] The module inventory is unchanged.
