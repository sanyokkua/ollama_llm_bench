# ADR-0006 — Extract the shared inference-progress helper into `backend/inference_progress/`

**Status:** accepted
**Date:** 2026-07-14
**Deciders:** architect, coder
**Supersedes:** —

## Context and problem statement

`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 specifies exactly one
`emit_progress_during` helper, reused verbatim by four call sites: the per-task main inference
call, the per-task judge call, the Run Analysis Service's generation call, and provider
test-inference. STORY-030 implemented the helper as a private detail of
`backend/benchmark_pipeline/_internal/progress.py`, wiring only the first two of the four
callers and explicitly deferring the other two in its own docstring ("the other two ... belong
to modules outside this story's front-matter scope and are not wired here").

STORY-035 (Run Analysis Service) is the first of those two remaining callers to be built.
`backend/run_analysis/` cannot import `backend/benchmark_pipeline/_internal/progress.py`
directly — the `import-linter` "module internals are private" contract forbids any module from
reaching into another module's `_internal/` package (`01_PROJECT_STRUCTURE.md` §"Boundary
enforcement"). Should the helper move to a shared home before STORY-035 builds on it, or should
`backend/run_analysis/` carry its own private copy of the same algorithm?

## Decision drivers

- The spec's explicit single-shared-helper intent (§6.9: "reused verbatim by 4 callers").
- Avoiding two — eventually three, once provider test-inference is built — independently
  maintained copies of the same ~85-line heartbeat/cadence algorithm drifting apart over time.
- Minimizing churn to the already-`done`, already-tested `benchmark_pipeline` module: a pure
  move (rename plus relocate, no logic change) keeps its own regression risk near zero.
- Keeping the `import-linter` module-boundary contracts intact rather than carving out a
  targeted exception.

## Considered options

- Option A — Extract the helper into a new shared module, `backend/inference_progress/`.
- Option B — Duplicate a private copy of the algorithm inside `backend/run_analysis/_internal/`.
- Option C — Relax the "module internals are private" `import-linter` contract with a targeted
  exception allowing `backend/run_analysis/` to import
  `backend/benchmark_pipeline/_internal/progress`.

## Decision outcome

Chosen option: **Option A.** It is the only option that satisfies the spec's explicit reuse
intent without weakening a structural contract (Option C) or accepting drift risk across a
growing number of independently maintained copies (Option B). A dedicated shared-infrastructure
module also matches this codebase's own precedent for cross-cutting helpers that no single
feature module owns (e.g. `backend/adaptive_timeout/`, `backend/circuit_breaker/`).

### Consequences

- Positive — One implementation, one test suite, reused unchanged by the third caller (provider
  test-inference) when that story is built. No `import-linter` exception is needed.
- Negative — This story's diff touches `backend/benchmark_pipeline/_internal/units.py`'s import
  line even though `benchmark_pipeline` is not in STORY-035's own `modules:` front-matter — this
  is called out explicitly in STORY-035's completion notes rather than left unexplained.
- Neutral — `backend/inference_progress/` is a new shared-infrastructure module, not a feature
  module; `01_MODULE_INVENTORY.md` is vendored and read-only, so its addition is recorded here
  and in the consuming stories' notes rather than as a spec-file edit.

## Pros and cons of the options

### Option A — Extract to `backend/inference_progress/`

- Good — One implementation and one test suite; satisfies the spec's explicit reuse intent; no
  import-linter exception.
- Bad — Touches a `done` story's file tree (`benchmark_pipeline`) to repoint one import.

### Option B — Private copy inside `backend/run_analysis/_internal/`

- Good — Zero changes to `benchmark_pipeline`.
- Bad — Two copies of the same ~85-line algorithm from day one, a third likely once provider
  test-inference is built; contradicts the spec's explicit "reused verbatim" intent; drift risk
  each time either copy is touched.

### Option C — Targeted import-linter exception

- Good — No new module, no code move.
- Bad — Weakens a structural contract for one call site; every future consumer of
  `emit_progress_during` would need the same carve-out, compounding the exception.

## Links

- Spec clauses: `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#6.9`
- Stories: STORY-030 (original private implementation), STORY-035 (first consumer of the
  extraction; applies this decision)
