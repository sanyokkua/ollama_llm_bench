"""No new DTO for this module (§3, §6.3).

The embedding service introduces no ``msgspec.Struct`` of its own. Its two numeric
outputs — the Cosine Score and the pass/fail threshold — are the domain's existing
``CosineScore``/``CosineThreshold`` type aliases (both
``Annotated[float, msgspec.Meta(ge=0.0, le=1.0)]``, defined in ``backend/domain``), and
the raw embedding vector is a plain ``tuple[float, ...]`` (§3) — not persisted, held only
in the service's in-memory cache for the lifetime of one instance (§6.5, §9). This file
exists to satisfy the module public-surface convention and to document that omission
explicitly rather than leaving it silent.
"""

__all__: list[str] = []
