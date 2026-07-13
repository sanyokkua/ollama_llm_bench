"""The deterministic sanity pre-check (§6.2 of 04_EVALUATION_PIPELINE.md)."""

from ollama_llm_bench.backend.domain import BenchmarkTask, TaskOrigin
from ollama_llm_bench.backend.evaluation._internal.parameters import _EvaluationParameters

_ECHO_MIN_LENGTH_CHARS = 16
_ECHO_LENGTH_DIFF_RATIO_THRESHOLD = 0.20


class _SanityCheckerImpl:
    """The concrete sanity pre-check; never constructed outside ``api.py``."""

    def __init__(self, *, parameters: _EvaluationParameters) -> None:
        self._parameters = parameters

    def check(self, *, response: str, task: BenchmarkTask) -> bool:
        stripped = response.strip()
        if not stripped:
            return False
        if _is_echo(stripped, task.question.strip()):
            return False
        if (
            task.task_origin is not TaskOrigin.SYNTHETIC
            and len(stripped) < self._parameters.sanity_min_chars
        ):
            return False
        return not _has_leading_error_marker(stripped, self._parameters.sanity_error_markers)


def _is_echo(response: str, question: str) -> bool:
    if response.casefold() == question.casefold():
        return True
    if len(response) < _ECHO_MIN_LENGTH_CHARS or len(question) < _ECHO_MIN_LENGTH_CHARS:
        return False
    response_cf, question_cf = response.casefold(), question.casefold()
    if response_cf not in question_cf and question_cf not in response_cf:
        return False
    return response_cf in question_cf or question_cf in response_cf


def _has_leading_error_marker(response: str, markers: tuple[str, ...]) -> bool:
    for line in response.splitlines():
        upper_line = line.strip().upper()
        if any(upper_line.startswith(marker.upper()) for marker in markers):
            return True
    return False
