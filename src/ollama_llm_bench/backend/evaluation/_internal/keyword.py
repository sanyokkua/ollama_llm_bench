"""The keyword phase: exact / forbidden / semantic term matching (§6.3 of
04_EVALUATION_PIPELINE.md)."""

from ollama_llm_bench.backend.domain import (
    BenchmarkResultTerm,
    RequiredTerms,
    ResultTermKind,
    Verdict,
)
from ollama_llm_bench.backend.embedding import EmbeddingService
from ollama_llm_bench.backend.evaluation._internal.parameters import _EvaluationParameters
from ollama_llm_bench.backend.evaluation.models import KeywordPhaseResult


class _KeywordEvaluatorImpl:
    """The concrete keyword-phase evaluator; never constructed outside ``api.py``."""

    def __init__(
        self, *, embedding_service: EmbeddingService, parameters: _EvaluationParameters
    ) -> None:
        self._embedding_service = embedding_service
        self._parameters = parameters

    def evaluate(self, *, response: str, required_terms: RequiredTerms) -> KeywordPhaseResult:
        terms: list[BenchmarkResultTerm] = []
        response_cf = response.casefold()

        has_failure = self._collect_exact_missing(required_terms.exact, response_cf, terms)
        has_failure |= self._collect_forbidden_found(required_terms.forbidden, response_cf, terms)
        has_failure |= self._collect_semantic(required_terms.semantic, response, terms)

        verdict = Verdict.FAIL if has_failure else Verdict.PASS
        return KeywordPhaseResult(verdict=verdict, terms=tuple(terms))

    def _collect_exact_missing(
        self, exact_terms: tuple[str, ...], response_cf: str, terms: list[BenchmarkResultTerm]
    ) -> bool:
        has_failure = False
        for order, term in enumerate(exact_terms):
            if term.casefold() not in response_cf:
                terms.append(
                    BenchmarkResultTerm(
                        term_kind=ResultTermKind.EXACT_MISSING,
                        term_order=order,
                        term_text=term,
                        similarity_score=None,
                    )
                )
                has_failure = True
        return has_failure

    def _collect_forbidden_found(
        self, forbidden_terms: tuple[str, ...], response_cf: str, terms: list[BenchmarkResultTerm]
    ) -> bool:
        has_failure = False
        for order, term in enumerate(forbidden_terms):
            if term.casefold() in response_cf:
                terms.append(
                    BenchmarkResultTerm(
                        term_kind=ResultTermKind.FORBIDDEN_FOUND,
                        term_order=order,
                        term_text=term,
                        similarity_score=None,
                    )
                )
                has_failure = True
        return has_failure

    def _collect_semantic(
        self, semantic_terms: tuple[str, ...], response: str, terms: list[BenchmarkResultTerm]
    ) -> bool:
        has_failure = False
        threshold = self._parameters.keyword_semantic_pass_threshold
        for order, term in enumerate(semantic_terms):
            similarity = self._embedding_service.cosine(text_a=response, text_b=term)
            terms.append(
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.SEMANTIC,
                    term_order=order,
                    term_text=term,
                    similarity_score=similarity,
                )
            )
            if similarity < threshold:
                has_failure = True
        return has_failure
