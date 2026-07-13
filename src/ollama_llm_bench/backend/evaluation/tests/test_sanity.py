"""Tests for backend/evaluation/_internal/sanity.py."""

import pytest

from ollama_llm_bench.backend.domain import TaskOrigin
from ollama_llm_bench.backend.evaluation._internal.parameters import parse_evaluation_parameters
from ollama_llm_bench.backend.evaluation._internal.sanity import _SanityCheckerImpl
from ollama_llm_bench.backend.evaluation.tests.conftest import make_snapshot, make_task

_SHORT_QUESTION = "What is the capital of France?"
_LONG_QUESTION = "What is the capital city of France, and what is its approximate population today?"


@pytest.mark.parametrize(
    ("response", "question", "task_origin", "expected"),
    [
        ("", _SHORT_QUESTION, TaskOrigin.FILE, False),
        ("   \n\t  ", _SHORT_QUESTION, TaskOrigin.FILE, False),
        (_SHORT_QUESTION, _SHORT_QUESTION, TaskOrigin.FILE, False),
        # near-length echo: 35 vs 30 chars, ratio ~0.14 < 0.20 -> flagged as echo
        ("What is the capital of France? Yes.", _SHORT_QUESTION, TaskOrigin.FILE, False),
        ("a", _SHORT_QUESTION, TaskOrigin.FILE, False),
        (
            "ERROR: connection reset by peer while generating a response",
            _SHORT_QUESTION,
            TaskOrigin.FILE,
            False,
        ),
        ("42", _SHORT_QUESTION, TaskOrigin.FILE, True),
        ("a", _SHORT_QUESTION, TaskOrigin.SYNTHETIC, True),
        # spec's own worked counter-example (§6.2 line 132): a short valid prefix-shaped
        # answer to a much longer question, ratio ~0.58 >= 0.20 -> NOT flagged as echo
        ("What is the capital city of France", _LONG_QUESTION, TaskOrigin.FILE, True),
    ],
)
def test_sanity_rules_flag_the_expected_responses(
    response: str, question: str, task_origin: TaskOrigin, *, expected: bool
) -> None:
    """Proves: STORY-028-AC-1

    Each of the five sanity conditions produces the documented
    sanity_check_passed value.
    """
    checker = _SanityCheckerImpl(parameters=parse_evaluation_parameters(make_snapshot()))
    task = make_task(question=question, task_origin=task_origin)

    result = checker.check(response=response, task=task)

    assert result is expected
