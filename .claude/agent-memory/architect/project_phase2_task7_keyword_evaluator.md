---
name: Phase 2 Task 7 — KeywordEvaluator design decision
description: Architectural decisions, confirmed facts, and test patterns for KeywordEvaluator (Layer 2) planned on 2026-04-16
type: project
---

Chose **Option B** (private helper methods per check category) for KeywordEvaluator.

**Why:** Mirrors `RuleBasedEvaluator` pattern exactly — `_fail()` / `_unknown()` constructors, module-level constants, module-level pure math function. Keeps `evaluate()` under 50 lines via delegation. Rejected inline monolith (Option A) and over-engineered strategy object (Option C).

**How to apply:** All evaluator layers (Layer 1–3) follow the same helper-method decomposition pattern. Module-level constants for thresholds, module-level pure functions for math, private methods for each check category.

---

Key facts confirmed as of 2026-04-16 (Tasks 1–6 complete):

- `RequiredTerms` fields are `tuple[str, ...]`, NOT `list[str]` — confirmed from `models.py` lines 124–131.
- `BenchmarkResult` is `frozen=True` — `KeywordEvaluator.evaluate()` returns `EvaluationResult` only; writes nothing to `BenchmarkResult`.
- `EmbeddingProviderApi.encode(texts: list[str]) -> list[list[float]]` — takes list, returns list of float vectors. Call pattern: `encode([response_text, *semantic_terms])` returns `[response_vec, term_vec_0, ...]`.
- `EvaluatorApi` is `@runtime_checkable` Protocol — `isinstance(evaluator, EvaluatorApi)` works at test time.
- `evaluators/__init__.py` already exists (created in Task 6) — no need to create it again.
- Response text extraction pattern: `result.sanitized_response or result.raw_response or ""` — consistent across all evaluator layers.
- Module-level constants exported for test import: `_SEMANTIC_PASS_THRESHOLD = 0.70`, `_SEMANTIC_FAIL_THRESHOLD = 0.40`, `_cosine_similarity` function.
- Embedding encoding error: catch `Exception`, log `logger.warning(...)`, return `_unknown(...)` — pipeline never throws.
- `_cosine_similarity` uses `math.sqrt` and `zip` — no numpy, pure stdlib. Guard: `return 0.0 if norm_a == 0 or norm_b == 0`.
- Test strategy for "between thresholds" semantic: use `mocker.patch("...keyword_evaluator._cosine_similarity", return_value=0.55)` to avoid fragile vector arithmetic in tests.
- Tests verify `mock_embedding.encode.call_count == 0` for all short-circuit paths (no embedding calls on empty required_terms or on forbidden/exact failures).
- No new third-party dependencies introduced — `math` is stdlib.
- This task creates exactly 2 files; no modifications to existing files.
