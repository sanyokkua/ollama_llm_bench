"""Details table `Verdict` column rendering (`19_TABLE_SERIALIZATION.md` §6.2).

``ERROR`` and ``UNKNOWN`` are render-only display tokens, never ``Verdict`` enum
members (SPEC-088); exports are one-way reports and this column is not required to
round-trip.
"""

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus

_TERMINAL_FAILURE_STATUSES: frozenset[ResultStatus] = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)


def render_verdict(result: BenchmarkResult) -> str:
    """Render the Details ``Verdict`` column display token (§6.2).

    Returns:
        ``"PASS"``/``"FAIL"`` for a set ``Verdict``; the render-only token
        ``"ERROR"`` for a terminal-failure status with no verdict; ``"UNKNOWN"``
        for any other non-terminal/no-verdict row.
    """
    if result.verdict is not None:
        return result.verdict.value.upper()
    if result.status in _TERMINAL_FAILURE_STATUSES:
        return "ERROR"
    return "UNKNOWN"
