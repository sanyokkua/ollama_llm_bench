"""The pure cosine-similarity computation (§6.3)."""

import math

_ZERO_NORM_SCORE = 0.0
_CLAMP_MIN = 0.0
_CLAMP_MAX = 1.0


def compute_cosine(vector_a: tuple[float, ...], vector_b: tuple[float, ...]) -> float:
    """Compute the clamped whole-vector cosine similarity of two vectors (§6.3).

    ``cosine(a, b) = dot(a, b) / (norm(a) * norm(b))``, clamped into
    ``[0.0, 1.0]`` — a raw value below ``0.0`` (near-opposite vectors) clamps
    to ``0.0``, a value slightly above ``1.0`` from floating-point rounding
    clamps to ``1.0``. When either vector has zero norm the cosine is
    undefined and the function returns ``0.0`` (§6.3, an empty/degenerate
    text embeds to a zero-norm vector).

    Args:
        vector_a: The first embedding vector.
        vector_b: The second embedding vector, the same length as
            ``vector_a``.

    Returns:
        The clamped cosine similarity in ``[0.0, 1.0]``.
    """
    norm_a = math.sqrt(sum(component * component for component in vector_a))
    norm_b = math.sqrt(sum(component * component for component in vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return _ZERO_NORM_SCORE
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    raw_cosine = dot_product / (norm_a * norm_b)
    return max(_CLAMP_MIN, min(_CLAMP_MAX, raw_cosine))
