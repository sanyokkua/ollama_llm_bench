"""Tests for backend/evaluation/_internal/sanity.py."""

import pytest

from ollama_llm_bench.backend.domain import TaskOrigin
from ollama_llm_bench.backend.evaluation._internal.parameters import parse_evaluation_parameters
from ollama_llm_bench.backend.evaluation._internal.sanity import _SanityCheckerImpl
from ollama_llm_bench.backend.evaluation.tests.conftest import make_snapshot, make_task


@pytest.mark.parametrize(
    ("response", "task_origin", "expected"),
    [
        ("", TaskOrigin.FILE, False),
        ("   \n\t  ", TaskOrigin.FILE, False),
        ("What is the capital of France?", TaskOrigin.FILE, False),
        ("What is the capital of France? Please answer.", TaskOrigin.FILE, False),
        ("a", TaskOrigin.FILE, False),
        ("ERROR: connection reset by peer while generating a response", TaskOrigin.FILE, False),
        ("42", TaskOrigin.FILE, True),
        ("a", TaskOrigin.SYNTHETIC, True),
    ],
)
def test_sanity_rules_flag_the_expected_responses(
    response: str, task_origin: TaskOrigin, *, expected: bool
) -> None:
    """Proves: STORY-028-AC-1

    Each of the five sanity conditions produces the documented
    sanity_check_passed value.
    """
    checker = _SanityCheckerImpl(parameters=parse_evaluation_parameters(make_snapshot()))
    task = make_task(question="What is the capital of France?", task_origin=task_origin)

    result = checker.check(response=response, task=task)

    assert result is expected
