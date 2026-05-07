---
name: Phase 2 Task 8 — CosineSimilarityEvaluator design (2026-04-16)
description: Design decisions for Layer 3 cosine evaluator — replicate _cosine_similarity, None scope guard, encode call order, between-threshold patching pattern
type: project
---

`_cosine_similarity` is replicated in `cosine_evaluator.py` — not imported from `keyword_evaluator.py`.

**Why:** Spec is explicit ("replicate, don't import"); seven-line math function; coupling two sibling evaluator modules is a higher cost than minor duplication.

`_SCOPE_THRESHOLDS: dict[ResponseScope, tuple[float, float]]` — key is `ResponseScope`, value is `(pass_threshold, fail_threshold)`. When `task.response_scope is None`, default to `ResponseScope.CONTAINS` thresholds using explicit `is not None` guard (not `or`).

`encode([golden_answer, response])` — golden first (index 0), response second (index 1). Order is load-bearing in tests even though cosine is symmetric.

Between-threshold tests patch `cosine_evaluator._cosine_similarity` at point-of-use with `mocker.patch("ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity", return_value=X)` while still setting `encode.return_value` to a valid two-vector list.

`_compute_similarity(golden, response) -> tuple[bool, float]` private helper isolates try/except so `evaluate()` stays flat (max 3 nesting levels).

**How to apply:** Follow same replicate-not-import pattern and scope guard pattern for any future evaluator that computes embeddings.
