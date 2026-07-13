"""The four-layer evaluation module: sanity, keyword, cosine, and judge.

Grades one benchmark result into a binary PASS/FAIL verdict. See
``docs/v3_specification/11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`` and
``docs/v3_specification/08_Cross_Cutting/08-P_judge_protocol.md``.
"""

from ollama_llm_bench.backend.evaluation.protocols import (
    CosineEvaluator,
    JudgeEvaluator,
    KeywordEvaluator,
    SanityChecker,
)

__all__: list[str] = [
    "CosineEvaluator",
    "JudgeEvaluator",
    "KeywordEvaluator",
    "SanityChecker",
]
