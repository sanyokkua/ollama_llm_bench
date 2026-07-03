# Embedding Service

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `06_Settings_Dialog/`

This document specifies the embedding service: how the embedding model is selected, how the service produces vector embeddings, how it computes the cosine-similarity quality value (the **Cosine Score**), how that score is mapped to a binary pass/fail outcome through the single user-configured `eval.cosine_threshold` (DD-45), how embeddings are cached, and the provider-specific behaviour. The embedding service is the only producer of a numeric quality value in the application; the cosine phase of the evaluation pipeline and the keyword phase's semantic-term check both depend on it.

---

## Table of Contents

1. Purpose
2. Inputs
3. Outputs
4. Preconditions
5. Postconditions
6. Algorithm
7. Configuration
8. Error handling
9. Threading and concurrency
10. Examples
11. Test cases

---

## 1. Purpose

The embedding service converts text into fixed-length numeric vectors and computes the cosine similarity between two pieces of text. It serves two consumers in the evaluation pipeline:

- the **cosine phase**, which compares a model's `sanitized_response` to the task `golden_answer` and produces the Cosine Score stored in `BenchmarkResult.cosine_similarity`;
- the **keyword phase's semantic-term check**, which compares the response to each declared semantic term.

The Cosine Score is the single numeric quality metric the application exposes — result tables and charts present it as the "score", and the judge phase deliberately produces no competing number. The embedding service computes that score; the cosine phase (see `04_EVALUATION_PIPELINE.md`) maps it to a binary verdict.

The service is skipped entirely for tasks that opt out via `cosine_enabled: false` (DD-46) or have no `golden_answer`; see §6.6.

## 2. Inputs

| Input | Source | Notes |
|---|---|---|
| Text pair to compare | the cosine phase or the keyword phase | `(sanitized_response, golden_answer)` for cosine; `(sanitized_response, semantic_term)` for each semantic term. |
| `cosine_enabled` | `BenchmarkTask.cosine_enabled` | The task-level opt-out (DD-46): determines, together with the presence of a `golden_answer`, whether cosine runs at all (§6.6). |
| Embedding model | the embedding selection / the run's `EMBEDDING`-role `BenchmarkRunModelEntry` | The `(provider_id, model_name)` pair that hosts the embedding model. |
| Cosine threshold | the run's frozen `settings_snapshot` | `eval.cosine_threshold` — the single user-configured pass/fail cutoff (DD-45). |
| Provider client | injected port | Reaches the embedding endpoint of the configured provider. |

## 3. Outputs

| Output | Type | Meaning |
|---|---|---|
| Embedding vector | `tuple[float, ...]` | A fixed-length numeric vector for one text input. Not persisted; held only in the cache. |
| Cosine Score | `CosineScore` (`float`, `0.0`–`1.0`) | The cosine similarity for a comparison. Stored in `BenchmarkResult.cosine_similarity` by the cosine phase, and in `BenchmarkResultTerm.similarity_score` for each semantic term by the keyword phase. |
| Threshold lookup | `CosineThreshold` (`float`, `0.0`–`1.0`) | The single pass/fail threshold (`eval.cosine_threshold`). |

The embedding service returns the numeric Cosine Score; it does not itself decide `PASS` / `FAIL`. The cosine phase compares the score against the threshold and writes `cosine_verdict`. The service produces no verdict and no enum value.

## 4. Preconditions

- An embedding model is configured: an embedding selection exists, or the run snapshot carries an `EMBEDDING`-role model.
- The configured embedding provider is reachable, or a cached embedding exists for the text.
- The `eval.cosine_threshold` key is present in the run's frozen settings snapshot.
- The input text is the **sanitized** response — reasoning/thinking blocks already stripped — never the raw response.

When no embedding model can be resolved, the selection is absent and `GRADED` is disabled at run creation until the user configures one (see the embedding selection, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §5.2). A run that grades but disables the cosine phase and declares no semantic terms needs no embedding model.

## 5. Postconditions

- Every cosine comparison yields a `CosineScore` in the closed interval `[0.0, 1.0]`.
- For a cosine-graded task, `BenchmarkResult.cosine_similarity` carries the computed Cosine Score.
- For each semantic term, `BenchmarkResultTerm.similarity_score` carries the term's similarity.
- A task with `cosine_enabled = false`, or with no `golden_answer`, has no cosine computation performed; `cosine_similarity` stays `None`.
- Identical text inputs within a run produce identical embeddings (deterministic, cache-backed).

## 6. Algorithm

### 6.1 Embedding-model selection

The embedding model is the `(provider, model)` pair declared by the embedding selection (in Settings) and frozen into the run snapshot as the `EMBEDDING`-role `BenchmarkRunModelEntry`. A run has at most one embedding model. The service routes every embedding request to that provider through the injected provider client. The embedding model is fixed for the life of the run — it is read from the run snapshot, never re-resolved from live settings mid-run.

### 6.2 Producing an embedding

To embed a piece of text the service:

1. Normalises the text — trims surrounding whitespace; the text is otherwise sent verbatim.
2. Checks the embedding cache (§6.5) for the `(provider_id, model_name, normalised_text)` key. On a hit, the cached vector is returned and no network call is made.
3. On a miss, calls the provider's embedding endpoint for the normalised text and receives a numeric vector.
4. Stores the vector in the cache under the key and returns it.

All embeddings produced within one run use the same embedding model, so two vectors compared against each other always share a vector space and dimension.

### 6.3 The cosine-similarity formula

Given two embedding vectors `a` and `b` of equal length `n`, the cosine similarity is:

```
cosine(a, b) = dot(a, b) / (norm(a) * norm(b))

where  dot(a, b) = sum( a[i] * b[i]  for i in 0..n-1 )
       norm(v)   = sqrt( sum( v[i] * v[i]  for i in 0..n-1 ) )
```

The raw cosine value lies in `[-1.0, 1.0]`. The service clamps the result into `[0.0, 1.0]` — a value below `0.0` (near-opposite vectors, rare for embedding models) is clamped to `0.0`, a value slightly above `1.0` from floating-point rounding is clamped to `1.0`. The clamped value is the **Cosine Score**, typed `CosineScore`.

If either vector has zero norm (an empty or degenerate text), the cosine is undefined; the service returns a Cosine Score of `0.0` for that comparison.

### 6.4 The comparison and the single threshold (DD-45)

The comparison is **always the whole response against the whole golden answer** (D-R-04, MISS-03, DD-45): embed the entire `sanitized_response` (reasoning blocks already stripped) once and the entire `golden_answer` once, and take the single cosine between those two vectors. There is **no** sliding-window, sub-span, or fragment matching, and **no per-task scope or interpretation layer** — the Cosine Score already expresses how close the answer is. (This keeps cost bounded at two cache-friendly embeddings per task and removes the score-inflation a max-over-windows scheme would introduce.)

The pass/fail decision uses **one user-configured threshold**: `eval.cosine_threshold` (default `0.85`, per-run-overridable, read from the run's frozen settings snapshot). There is exactly one threshold — a single pass/fail boundary, not a band, and not a per-task selection. The service exposes the threshold lookup so the cosine phase can apply it:

- Cosine Score **at or above** `eval.cosine_threshold` → the cosine phase records `cosine_verdict = PASS`;
- Cosine Score **below** `eval.cosine_threshold` → the cosine phase records `cosine_verdict = FAIL`.

The numeric Cosine Score is always stored on the result regardless of which side of the threshold it falls on; the threshold only affects the binary `cosine_verdict`, never the stored number.

For the **semantic-term check** in the keyword phase, the comparison is always the whole-text cosine between the response and the term; each term's Cosine Score is stored in `BenchmarkResultTerm.similarity_score`. The keyword phase's own threshold (`eval.keyword_semantic_pass_threshold`, owned by `04_EVALUATION_PIPELINE.md`) is applied **per term** — every semantic term must individually meet or exceed it (D-R-04, MISS-05), not as a mean across terms; `eval.cosine_threshold` does not apply to semantic terms.

### 6.5 Embedding cache

The service maintains an in-memory cache keyed on `(provider_id, model_name, normalised_text)`. The cache exists for the lifetime of one run and is dropped when the run ends. It removes redundant network calls in two common cases:

- the same golden answer is compared once per model under test — every test model in the run is graded against the same task, so the golden answer is embedded once and reused;
- the same response text recurs (rare, but cheap to deduplicate).

The cache is bounded by `eval.embedding_cache_max_entries` (default `4096`); on overflow the least-recently-used entry is evicted. Cache entries are never persisted — they are a runtime optimisation only, and an embedding model never changes mid-run, so a cache hit is always valid for the run that produced it.

### 6.6 The task-level cosine opt-out: `cosine_enabled` (DD-46)

Cosine runs for a task **iff** the task's `cosine_enabled` flag is `true` (the default)
**and** the task has a `golden_answer` — exactly analogous to the keyword phase, which
runs only when the task declares keywords. There is no hardcoded task-type rule: whether
whole-text similarity is a meaningful signal is the task author's decision, taken on the
task itself. For tasks where it is not — for example code tasks, where two correct
solutions can be textually unrelated — the author sets `cosine_enabled: false`, the
embedding service performs **no cosine computation**, the cosine phase records
`cosine_similarity = None` and `cosine_verdict = None`, and the verdict is decided by the
keyword and judge phases instead.

The semantic-term check in the keyword phase is **not** subject to this opt-out —
semantic terms are embedded for any task that declares them, including
`cosine_enabled: false` tasks, because a semantic term is a short concept phrase, not a
whole-answer comparison.

### 6.7 Provider-specific notes

The embedding endpoint differs by `ProviderType`:

| `ProviderType` | Embedding behaviour |
|---|---|
| `OPENAI_COMPATIBLE` | Uses the provider's embeddings endpoint. The model name is the embedding model string. Azure-hosted endpoints additionally use the `azure_*` fields of the run's provider snapshot. |
| `ANTHROPIC` | The Anthropic API exposes no first-party embedding endpoint; an Anthropic provider must not be selected as the embedding provider. The run-creation use case rejects an `EMBEDDING`-role model whose provider type is `ANTHROPIC`. |
| `GEMINI` | Uses the Gemini embeddings endpoint. The model name is the Gemini embedding model string. |

### 6.6a Embedding-capability validation (D-R-11, MISS-11)

The provider-type check above is necessary but **not sufficient**: an `OPENAI_COMPATIBLE` endpoint may be a *chat-only* server with no embeddings route — most notably a `llama.cpp` server **not** started in embedding mode (`--embedding`), which answers `/v1/chat/completions` but returns `404`/`400` on `/v1/embeddings`. Selecting such an endpoint as the embedding provider would otherwise pass run creation and then degrade **every** cosine check to not-run at run time.

To catch this at configuration time rather than mid-run, the application performs a **capability probe** — and this is the **single** user-initiated embedding test path (DD-48; the automatic readiness check never calls `embed()`): it runs when the user clicks the Settings **Test Embedding** action and when the user **changes the embedding selection** (both explicit user actions), holding the single-inference gate as `PROVIDER_TEST`. It issues **one tiny test embedding call** — `embed("probe")` — against the configured `(provider, model)`. The outcome is recorded as the embedding selection's verified capability:

- **Success** (a vector is returned) → the embedding model is `embedding-capable` and may be used for cosine grading.
- **Failure** (`404`/`400`/`ProviderError` from the embeddings route) → the selection is flagged **"endpoint cannot embed"** and is **not** accepted as ready; `GRADED` with cosine enabled is blocked for that selection until a working embedding endpoint is chosen, with a clear message naming the failing `(provider, model)` **and remediation guidance** keyed to the backend expectation table (`13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` §7): update Ollama to a release serving `/v1/embeddings`; start the llama.cpp server with `--embedding`; or choose a different embedding provider.

This is a user-initiated, one-shot call under the `PROVIDER_TEST` gate activity and, for a paid cloud embedding provider, is billable — exactly as the Provider Edit *Test inference* action is, and permitted for exactly the same reason: the user asked for it. It replaces the previous "validate by provider type only" heuristic, which could not detect a chat-only OpenAI-compatible endpoint. The complementary run-start **fail-fast probe** (DD-48, `04_EVALUATION_PIPELINE.md` §4) repeats the same one-shot check when a run that needs embeddings starts, under the already-held `BENCHMARK_RUN` gate.

Different providers return vectors of different dimension; the service never compares vectors produced by different embedding models. Because the embedding model is fixed per run, every comparison within a run is dimension-consistent by construction.

## 7. Configuration

All keys are read from the run's frozen `settings_snapshot`.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `eval.cosine_threshold` | float `0.0`–`1.0` | `0.85` | The single pass/fail threshold for the whole-text Cosine Score (DD-45). |
| `eval.embedding_cache_max_entries` | int `>= 1` | `4096` | Maximum embedding-cache entries before LRU eviction. |
| `eval.embedding_timeout_seconds` | int `1`–`3600` | `30` | **Fixed** per-call deadline applied to every embedding call. NOT adaptive — see §8 below and DD-34. |

The embedding model selection is stored as the two `app_settings` keys `embedding.selected_provider_name` and `embedding.selected_model_name`, and is frozen per run as the run's `EMBEDDING`-role model snapshot entry. Thresholds are editable in the Settings dialog (see `06_Settings_Dialog/`).

**The Embedding Service does NOT consult the Adaptive Timeout Service.** Every embedding call uses the fixed `eval.embedding_timeout_seconds` budget directly. There is no per-`(provider, model)` escalation ladder for embedding and no last-known-good promotion. **Consecutive-failure short-circuit (DD-70):** to bound the worst case, after `eval.embedding_consecutive_failures_to_skip` consecutive embedding failures/timeouts (default **3**) the run **stops attempting cosine for its remaining tasks** — the cosine phase degrades to not-run run-wide (not the whole run; keyword and judge still grade), and the Progress widget and Run-Analysis narrative show a one-time notice *"Embedding model unresponsive — cosine grading skipped for the remainder of this run."* This caps the dead time at roughly `K × eval.embedding_timeout_seconds` rather than `N × 30 s` for an N-task run. The run is **not failed** for this; it completes on its other phases. The embedding model is not *excluded* in the adaptive-timeout sense — there is simply no further embedding attempt once the cosine phase is short-circuited. **Run-level signal (D-R-04, MISS-10):** when the cosine phase was enabled for the run but produced **zero** Cosine Scores across all completed results (every embedding failed), the run records a prominent run-level warning (surfaced in the run summary and the run-analysis narrative) so the user is not misled into thinking the run was quality-graded when the entire cosine dimension silently did not run. The rationale is that embedding calls are short vector calls (not generative inference), so a single fixed budget is sufficient; adaptive escalation would only add state without changing the failure mode. See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` §1.2 and DD-34 (`08_Cross_Cutting/08-F_spec_issues_log.md`).

## 8. Error handling

| Condition | Handling |
|---|---|
| No embedding model configured, run grades with cosine enabled or with semantic terms | Run creation is blocked; `GRADED` is disabled until an embedding model is configured. The service is never reached without a model. |
| Embedding provider unreachable for a request | The request fails; the cosine phase records `cosine_similarity = None` and `cosine_verdict = None`; the verdict-combination step treats cosine as not-run. The run is not failed solely for this. |
| Embedding call exceeds `eval.embedding_timeout_seconds` | The request is abandoned at the fixed deadline; the cosine phase records `cosine_similarity = None` and `cosine_verdict = None` for the affected task; the verdict-combination step treats cosine as not-run and falls back per D-012 (binary FAIL when cosine is the deciding phase and cannot produce a value). The next task's embedding call uses the same fixed budget afresh, **until** `eval.embedding_consecutive_failures_to_skip` consecutive failures short-circuit the cosine phase run-wide (DD-70), after which no further embedding is attempted for the run. The Adaptive Timeout Service is not consulted on this path (see §7 and DD-34). |
| Embedding endpoint returns a malformed or empty vector | Treated as an embedding failure for that text; the affected comparison yields no Cosine Score; handled as the unreachable case above. |
| Either text is empty or its vector has zero norm | The cosine is undefined; the service returns a Cosine Score of `0.0`. |
| Raw cosine outside `[0.0, 1.0]` from floating-point rounding or near-opposite vectors | Clamped into `[0.0, 1.0]`. |
| An `ANTHROPIC` provider is selected as the embedding provider | Rejected at run creation; the embedding service is never asked to use an Anthropic provider. |

An embedding failure never throws to the pipeline as a fatal error; it degrades the cosine phase to not-run for the affected result, exactly as the cosine-phase disabled case is handled in `04_EVALUATION_PIPELINE.md`.

## 9. Threading and concurrency

There is **one shared `EmbeddingService` instance** — a singleton constructed once at the composition root and injected into every consumer. It is owned by the composition root and shared by the cosine evaluator, the keyword-semantic evaluator, and the readiness probe; no other instance is created.

The embedding service runs on the benchmark worker thread, off the Qt UI thread. Because execution is **strictly serial** (D-R-16) — one task, one stage, one inference call at a time across the whole application — the service is called by **at most one worker at a time**, so its in-memory LRU cache (§6.5) is effectively a **single-accessor** structure: no two threads ever embed concurrently and no two threads ever touch the cache concurrently. **No concurrent-cache locking is required** — there is no per-key in-flight lock, no read/write lock, and no need to coordinate a "request for an in-flight key waits for the first call" handshake, because there is never a second concurrent caller. A repeated text within the serial sequence is simply a later cache hit. Cosine arithmetic (§6.3) is pure and local, requiring no synchronisation. The service holds no Qt objects and emits no signals; it is a plain port consumed by the pipeline.

(There is no per-provider embedding concurrency limit: the single-inference invariant and serial execution already guarantee one embedding call at a time. Any prior wording implying concurrent embedding requests is superseded by D-R-16.)

## 10. Examples

### 10.1 Happy path — `CONTAINS` cosine comparison

A `factual_qa` task. The golden answer is a single sentence; the model wrapped that sentence inside a longer paragraph.

- The golden answer is embedded once as a whole (and cached, reused for every test model in the run).
- The whole response is embedded once; the Cosine Score is the single cosine between the whole-response vector and the whole-golden-answer vector (D-R-04, MISS-03). Because the golden sentence sits inside extra wrapper prose, the whole-text cosine is somewhat diluted but still high.
- The clamped Cosine Score is `0.88`, stored in `cosine_similarity`.
- The cosine phase applies `eval.cosine_threshold` (`0.85`); `0.88 >= 0.85` → `cosine_verdict = PASS`. (The threshold — vs `EXACT`'s `0.92` — is what accommodates the wrapper prose; the computation itself is the same whole-text cosine.)

### 10.2 Edge case — empty response

A `summarization` task; the model returned an empty string.

- The response embeds to a zero-norm vector.
- The cosine is undefined; the service returns a Cosine Score of `0.0`.
- `cosine_similarity = 0.0`; the cosine phase compares `0.0` against the scope threshold → `cosine_verdict = FAIL`.

### 10.3 Edge case — cosine skipped for a code task

A code task with `cosine_enabled: false`. The service performs no cosine computation for it; `cosine_similarity` and `cosine_verdict` both stay `None`. If the same task declared semantic terms, those terms would still be embedded and scored by the keyword phase's semantic check — the skip applies only to the whole-answer cosine comparison.

## 11. Test cases

1. `cosine(a, a)` for any non-zero vector `a` returns `1.0`.
2. `cosine(a, b)` for orthogonal vectors returns `0.0`.
3. A raw cosine slightly above `1.0` from rounding is clamped to `1.0`.
4. An empty text yields a zero-norm vector; any comparison with it returns a Cosine Score of `0.0`.
5. The same `(provider, model, text)` is embedded once; a second request for the same key is a cache hit with no network call.
6. The golden answer of a task is embedded once and reused across every test model in the run.
7. The Cosine Score is always the whole-text cosine of `sanitized_response` vs `golden_answer`; the verdict applies the single `eval.cosine_threshold` (DD-45).
8. No sliding-window, sub-span, or fragment matching exists: for a fixed pair of texts the computed Cosine Score is one value regardless of any task attribute.
9. A run snapshot with `eval.cosine_threshold = 0.85` marks a score of `0.85` PASS and `0.8499` FAIL (boundary is at-or-above).
10. A task with `cosine_enabled = false` (or no `golden_answer`) triggers no cosine computation; `cosine_similarity` stays `None` (DD-46).
11. A task with `cosine_enabled = true` and a `golden_answer` is graded by cosine normally, against `eval.cosine_threshold`.
12. A semantic term on a `cosine_enabled: false` task is still embedded and scored (the opt-out does not apply to semantic terms).
13. An unreachable embedding provider degrades the cosine phase to not-run; the result is not marked failed for this reason.
14. An `ANTHROPIC` provider cannot be selected as the embedding provider; run creation rejects it.
15. The embedding cache evicts the least-recently-used entry when `eval.embedding_cache_max_entries` is exceeded.
