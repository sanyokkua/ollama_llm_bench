"""Public factories for the four evaluation-phase Protocols, and the pure
verdict-combination function."""

import icontract

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry, ModelNameStr, Verdict
from ollama_llm_bench.backend.embedding import EmbeddingService
from ollama_llm_bench.backend.evaluation._internal.combination import combine_verdict_impl
from ollama_llm_bench.backend.evaluation._internal.cosine import _CosineEvaluatorImpl
from ollama_llm_bench.backend.evaluation._internal.judge.evaluator import _JudgeEvaluatorImpl
from ollama_llm_bench.backend.evaluation._internal.keyword import _KeywordEvaluatorImpl
from ollama_llm_bench.backend.evaluation._internal.parameters import (
    REQUIRED_EVALUATION_SETTING_KEYS,
    parse_evaluation_parameters,
)
from ollama_llm_bench.backend.evaluation._internal.sanity import _SanityCheckerImpl
from ollama_llm_bench.backend.evaluation.models import CombinedVerdict
from ollama_llm_bench.backend.evaluation.protocols import (
    CosineEvaluator,
    JudgeEvaluator,
    KeywordEvaluator,
    SanityChecker,
)
from ollama_llm_bench.backend.provider_registry import LLMClient

__all__: list[str] = [
    "combine_verdict",
    "make_cosine_evaluator",
    "make_judge_evaluator",
    "make_keyword_evaluator",
    "make_sanity_checker",
]


def _has_required_keys(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    keys = {entry.setting_key for entry in snapshot}
    return REQUIRED_EVALUATION_SETTING_KEYS.issubset(keys)


@icontract.require(
    _has_required_keys,
    "snapshot must carry every eval.* key this module reads — RunSnapshotBuilder "
    "guarantees this; a missing key means the run-creation use case has a bug, "
    "not that the run itself is misconfigured",
)
def make_sanity_checker(*, snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> SanityChecker:
    """Construct the deterministic sanity pre-check (§6.2) for one run."""
    parameters = parse_evaluation_parameters(snapshot)
    return _SanityCheckerImpl(parameters=parameters)


@icontract.require(
    _has_required_keys,
    "snapshot must carry every eval.* key this module reads — see make_sanity_checker",
)
@icontract.require(
    lambda embedding_service: embedding_service is not None,
    "embedding_service must be constructed by the caller",
)
def make_keyword_evaluator(
    *, embedding_service: EmbeddingService, snapshot: tuple[BenchmarkRunSettingEntry, ...]
) -> KeywordEvaluator:
    """Construct the keyword phase (§6.3) for one run."""
    parameters = parse_evaluation_parameters(snapshot)
    return _KeywordEvaluatorImpl(embedding_service=embedding_service, parameters=parameters)


@icontract.require(
    lambda embedding_service: embedding_service is not None,
    "embedding_service must be constructed by the caller",
)
def make_cosine_evaluator(*, embedding_service: EmbeddingService) -> CosineEvaluator:
    """Construct the cosine phase (§6.4) for one run."""
    return _CosineEvaluatorImpl(embedding_service=embedding_service)


@icontract.require(
    _has_required_keys,
    "snapshot must carry every eval.* key this module reads — see make_sanity_checker",
)
@icontract.require(
    lambda llm_client: llm_client is not None, "llm_client must be constructed by the caller"
)
def make_judge_evaluator(
    *,
    llm_client: LLMClient,
    model_name: ModelNameStr,
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> JudgeEvaluator:
    """Construct the judge phase (08-P_judge_protocol.md) for one run."""
    parameters = parse_evaluation_parameters(snapshot)
    return _JudgeEvaluatorImpl(llm_client=llm_client, model_name=model_name, parameters=parameters)


@icontract.require(
    lambda judge_enabled, judge_verdict: judge_enabled or judge_verdict is None,
    "judge_verdict must be None when the judge phase is disabled",
)
@icontract.require(
    lambda sanity_check_passed, keyword_verdict, cosine_verdict, judge_verdict: (
        not sanity_check_passed
        or keyword_verdict is not None
        or cosine_verdict is not None
        or judge_verdict is not None
    ),
    "at least one enabled phase must have produced a verdict when sanity passed — "
    "the run-creation use case already rejects an all-disabled grading "
    "configuration (§7 of 04_EVALUATION_PIPELINE.md)",
)
@icontract.ensure(
    lambda result: result.verdict in (Verdict.PASS, Verdict.FAIL),
    "the combined verdict is always binary — never UNKNOWN",
)
def combine_verdict(  # noqa: PLR0913  # mirrors combine_verdict_impl's six-parameter
    # signature — each parameter disambiguates a distinct combination-cascade input
    *,
    sanity_check_passed: bool,
    keyword_verdict: Verdict | None,
    cosine_verdict: Verdict | None,
    judge_enabled: bool,
    judge_verdict: Verdict | None,
    force_judge_on_prior_failure: bool,
) -> CombinedVerdict:
    """Fold the enabled phases' outcomes into one binary verdict (§6.6, §11)."""
    return combine_verdict_impl(
        sanity_check_passed=sanity_check_passed,
        keyword_verdict=keyword_verdict,
        cosine_verdict=cosine_verdict,
        judge_enabled=judge_enabled,
        judge_verdict=judge_verdict,
        force_judge_on_prior_failure=force_judge_on_prior_failure,
    )
