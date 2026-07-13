"""Tests for backend/evaluation/_internal/keyword.py."""

import pytest

from ollama_llm_bench.backend.domain import RequiredTerms, ResultTermKind
from ollama_llm_bench.backend.embedding.testing import FakeEmbeddingService
from ollama_llm_bench.backend.evaluation._internal.keyword import _KeywordEvaluatorImpl
from ollama_llm_bench.backend.evaluation._internal.parameters import parse_evaluation_parameters
from ollama_llm_bench.backend.evaluation.tests.conftest import make_snapshot


def _make_evaluator(*, threshold: str = "0.70") -> _KeywordEvaluatorImpl:
    parameters = parse_evaluation_parameters(
        make_snapshot({"eval.keyword_semantic_pass_threshold": threshold})
    )
    return _KeywordEvaluatorImpl(embedding_service=FakeEmbeddingService(), parameters=parameters)


def test_no_required_terms_yields_pass_with_no_terms() -> None:
    """Proves: STORY-028-AC-2

    A task declaring no required_terms yields keyword_verdict=PASS and no terms.
    """
    evaluator = _make_evaluator()

    result = evaluator.evaluate(response="anything", required_terms=RequiredTerms())

    assert result.verdict.value == "pass"
    assert result.terms == ()


def test_missing_exact_term_fails_and_records_exact_missing() -> None:
    """Proves: STORY-028-AC-2

    A declared exact term absent from the response fails the phase and
    records one EXACT_MISSING term.
    """
    evaluator = _make_evaluator()
    terms = RequiredTerms(exact=("Paris",))

    result = evaluator.evaluate(response="The capital is Lyon.", required_terms=terms)

    assert result.verdict.value == "fail"
    assert len(result.terms) == 1
    assert result.terms[0].term_kind == ResultTermKind.EXACT_MISSING
    assert result.terms[0].term_text == "Paris"


def test_present_forbidden_term_fails_and_records_forbidden_found() -> None:
    """Proves: STORY-028-AC-2

    A declared forbidden term present in the response fails the phase and
    records one FORBIDDEN_FOUND term.
    """
    evaluator = _make_evaluator()
    terms = RequiredTerms(forbidden=("Lyon",))

    result = evaluator.evaluate(response="The capital is Lyon, not Paris.", required_terms=terms)

    assert result.verdict.value == "fail"
    assert result.terms[0].term_kind == ResultTermKind.FORBIDDEN_FOUND
    assert result.terms[0].term_text == "Lyon"


def test_semantic_term_at_or_above_threshold_passes() -> None:
    """Proves: STORY-028-AC-2

    A semantic term whose similarity to an identical response is
    (modulo floating-point rounding in ``compute_cosine``) 1.0, which always
    clears any threshold <= 1.0, contributing to a PASS.
    """
    evaluator = _make_evaluator(threshold="0.70")
    terms = RequiredTerms(semantic=("The capital of France is Paris.",))

    result = evaluator.evaluate(response="The capital of France is Paris.", required_terms=terms)

    assert result.verdict.value == "pass"
    assert result.terms[0].term_kind == ResultTermKind.SEMANTIC
    similarity_score = result.terms[0].similarity_score
    assert similarity_score is not None
    assert similarity_score == pytest.approx(1.0)


def test_semantic_term_below_threshold_fails() -> None:
    """Proves: STORY-028-AC-2

    A semantic term whose similarity falls below the configured threshold
    fails the phase.
    """
    evaluator = _make_evaluator(threshold="1.0")
    terms = RequiredTerms(semantic=("a completely unrelated term",))

    result = evaluator.evaluate(response="The capital is Paris.", required_terms=terms)

    assert result.verdict.value == "fail"
    assert result.terms[0].term_kind == ResultTermKind.SEMANTIC


def test_exact_term_match_is_case_insensitive_substring() -> None:
    """Proves: STORY-028-AC-2

    An exact term matches case-insensitively as a substring.
    """
    evaluator = _make_evaluator()
    terms = RequiredTerms(exact=("PARIS",))

    result = evaluator.evaluate(response="the capital is paris, france", required_terms=terms)

    assert result.verdict.value == "pass"
    assert result.terms == ()
