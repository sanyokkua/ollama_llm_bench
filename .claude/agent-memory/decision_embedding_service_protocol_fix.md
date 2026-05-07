---
name: EmbeddingService Protocol conformance fix
description: Decision to add encode() method to EmbeddingService to satisfy EmbeddingProviderApi Protocol and remove cast() workaround in ProviderRegistry
type: project
---

Added `encode()` to `EmbeddingService` (delegates to `encode_batch`) so the class structurally
satisfies `EmbeddingProviderApi`. Removed `cast(EmbeddingProviderApi, ...)` workaround from
`ProviderRegistry.get_embedding_provider()`. Three tests added to `test_embedding_service.py`.

**Why:** The `cast()` suppressed Mypy but Phase 3's `CosineSimilarityEvaluator` calls
`embedding_provider.encode(texts)` at runtime — without the method, that raises `AttributeError`.
Renaming `encode_batch` → `encode` was rejected to avoid churn on existing tests and because the
`encode_single` / `encode_batch` naming pair has internal symmetry worth preserving.

**How to apply:** The `cast` import in `provider_registry.py` must NOT be removed — it is still
used by the three provider factory functions `_build_openai_compatible`, `_build_anthropic`,
`_build_gemini`. Only the `cast` call in `get_embedding_provider` is removed.
