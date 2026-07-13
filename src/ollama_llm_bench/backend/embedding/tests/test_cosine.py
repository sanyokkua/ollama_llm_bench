"""Proves STORY-027-AC-1 — the clamped cosine formula, the zero-norm rule, and the
identical/orthogonal/rounding fixed cases (§6.3)."""

import math

from hypothesis import given, strategies as st
import pytest

from ollama_llm_bench.backend.embedding._internal.math import compute_cosine

_VECTOR_LENGTH = 4
_MIN_ABS_COMPONENT = 1e-6
_NONZERO_COMPONENT = st.floats(
    min_value=-1000.0,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False,
).filter(lambda x: abs(x) > _MIN_ABS_COMPONENT)


@st.composite
def _nonzero_equal_length_vector_pair(
    draw: st.DrawFn,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    vector_a = tuple(draw(_NONZERO_COMPONENT) for _ in range(_VECTOR_LENGTH))
    vector_b = tuple(draw(_NONZERO_COMPONENT) for _ in range(_VECTOR_LENGTH))
    return vector_a, vector_b


@pytest.mark.slow
@given(_nonzero_equal_length_vector_pair())
def test_cosine_score_is_clamped_cosine(
    vectors: tuple[tuple[float, ...], tuple[float, ...]],
) -> None:
    """Proves: STORY-027-AC-1

    For any pair of non-zero equal-length vectors, compute_cosine equals the
    mathematical cosine of the pair clamped into [0.0, 1.0].
    """
    vector_a, vector_b = vectors
    norm_a = math.sqrt(sum(component * component for component in vector_a))
    norm_b = math.sqrt(sum(component * component for component in vector_b))
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    expected_raw = dot_product / (norm_a * norm_b)
    expected_clamped = max(0.0, min(1.0, expected_raw))

    score = compute_cosine(vector_a, vector_b)

    assert score == pytest.approx(expected_clamped, abs=1e-9)
    assert 0.0 <= score <= 1.0


def test_cosine_score_identity_is_one() -> None:
    """Proves: STORY-027-AC-1

    cosine(a, a) for any non-zero vector a returns 1.0.
    """
    vector_a = (1.0, 2.0, 3.0)

    score = compute_cosine(vector_a, vector_a)

    assert score == pytest.approx(1.0)


def test_cosine_score_orthogonal_is_zero() -> None:
    """Proves: STORY-027-AC-1

    cosine(a, b) for orthogonal vectors returns 0.0.
    """
    vector_a = (1.0, 0.0)
    vector_b = (0.0, 1.0)

    score = compute_cosine(vector_a, vector_b)

    assert score == pytest.approx(0.0)


def test_cosine_score_rounding_above_one_clamps_to_one() -> None:
    """Proves: STORY-027-AC-1

    A raw cosine slightly above 1.0 from floating-point rounding is clamped
    to 1.0.
    """
    epsilon = 1e-16
    vector_a = (1.0 + epsilon, 2.0, 3.0)
    vector_b = (1.0, 2.0, 3.0)

    score = compute_cosine(vector_a, vector_b)

    assert score <= 1.0


def test_cosine_score_zero_norm_first_vector_is_zero() -> None:
    """Proves: STORY-027-AC-1

    A zero-norm first vector (an empty/degenerate text) yields a Cosine Score
    of 0.0 for any comparison.
    """
    vector_a = (0.0, 0.0, 0.0)
    vector_b = (1.0, 2.0, 3.0)

    score = compute_cosine(vector_a, vector_b)

    assert score == 0.0


def test_cosine_score_zero_norm_second_vector_is_zero() -> None:
    """Proves: STORY-027-AC-1

    A zero-norm second vector yields a Cosine Score of 0.0 for any
    comparison.
    """
    vector_a = (1.0, 2.0, 3.0)
    vector_b = (0.0, 0.0, 0.0)

    score = compute_cosine(vector_a, vector_b)

    assert score == 0.0


def test_cosine_score_both_zero_norm_is_zero() -> None:
    """Proves: STORY-027-AC-1

    Two zero-norm vectors (both texts empty/degenerate) yield a Cosine Score
    of 0.0.
    """
    vector_a = (0.0, 0.0)
    vector_b = (0.0, 0.0)

    score = compute_cosine(vector_a, vector_b)

    assert score == 0.0
