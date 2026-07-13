"""Tests for backend/evaluation/_internal/parameters.py."""

import pytest

from ollama_llm_bench.backend.evaluation._internal.parameters import (
    REQUIRED_EVALUATION_SETTING_KEYS,
    parse_evaluation_parameters,
)
from ollama_llm_bench.backend.evaluation.tests.conftest import make_snapshot

_EXPECTED_SANITY_MIN_CHARS = 3
_EXPECTED_JUDGE_MAX_COMPLETION_TOKENS = 2048
_EXPECTED_PASS_THRESHOLD = 0.65


def test_parse_evaluation_parameters_reads_every_required_key() -> None:
    """Proves: STORY-028-AC-1

    All six required eval.* keys are parsed into their typed fields.
    """
    snapshot = make_snapshot(
        {
            "eval.sanity_min_chars": "3",
            "eval.sanity_error_markers": "ERROR:,EXCEPTION:",
            "eval.keyword_semantic_pass_threshold": "0.65",
            "eval.judge_max_completion_tokens": "2048",
            "eval.judge_max_parse_retries": "1",
            "eval.force_judge_on_prior_failure": "true",
        }
    )

    parameters = parse_evaluation_parameters(snapshot)

    assert parameters.sanity_min_chars == _EXPECTED_SANITY_MIN_CHARS
    assert parameters.sanity_error_markers == ("ERROR:", "EXCEPTION:")
    assert parameters.keyword_semantic_pass_threshold == pytest.approx(_EXPECTED_PASS_THRESHOLD)
    assert parameters.judge_max_completion_tokens == _EXPECTED_JUDGE_MAX_COMPLETION_TOKENS
    assert parameters.judge_max_parse_retries == 1
    assert parameters.force_judge_on_prior_failure is True


def test_required_evaluation_setting_keys_has_six_entries() -> None:
    """Proves: STORY-028-AC-1

    The required-key set matches exactly the six eval.* keys this module reads.
    """
    expected_keys = {
        "eval.sanity_min_chars",
        "eval.sanity_error_markers",
        "eval.keyword_semantic_pass_threshold",
        "eval.judge_max_completion_tokens",
        "eval.judge_max_parse_retries",
        "eval.force_judge_on_prior_failure",
    }
    assert expected_keys == REQUIRED_EVALUATION_SETTING_KEYS


@pytest.mark.parametrize(
    ("csv_value", "expected_markers"),
    [
        ("ERROR:,EXCEPTION:", ("ERROR:", "EXCEPTION:")),
        ("ERROR:, ,EXCEPTION:,", ("ERROR:", "EXCEPTION:")),
        ("  ERROR:  , , , EXCEPTION: ", ("ERROR:", "EXCEPTION:")),
        ("ERROR:", ("ERROR:",)),
        (",", ()),
        ("   ,  , ", ()),
        ("A,  B  ,C", ("A", "B", "C")),
        ("  WARN  , ERROR: , FATAL ", ("WARN", "ERROR:", "FATAL")),
    ],
)
def test_parse_evaluation_parameters_sanitizes_sanity_error_markers(
    csv_value: str, expected_markers: tuple[str, ...]
) -> None:
    """Proves: STORY-028-AC-1

    The sanity_error_markers CSV parser strips whitespace-only and empty entries,
    and trims real entries.
    """
    snapshot = make_snapshot(
        {
            "eval.sanity_min_chars": "3",
            "eval.sanity_error_markers": csv_value,
            "eval.keyword_semantic_pass_threshold": "0.65",
            "eval.judge_max_completion_tokens": "2048",
            "eval.judge_max_parse_retries": "1",
            "eval.force_judge_on_prior_failure": "true",
        }
    )

    parameters = parse_evaluation_parameters(snapshot)

    assert parameters.sanity_error_markers == expected_markers


@pytest.mark.parametrize(
    ("boolean_value", "expected_result"),
    [
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("YES", True),
        ("Yes", True),
        ("false", False),
        ("FALSE", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("NO", False),
        ("No", False),
        ("", False),
        ("   ", False),
        ("garbage", False),
        ("maybe", False),
        ("2", False),
        ("truee", False),
    ],
)
def test_parse_evaluation_parameters_parses_force_judge_on_prior_failure_boolean(
    *,
    boolean_value: str,
    expected_result: bool,
) -> None:
    """Proves: STORY-028-AC-1

    The force_judge_on_prior_failure boolean parser accepts 'true', '1', 'yes'
    (case-insensitive) as True, and everything else as False.
    """
    snapshot = make_snapshot(
        {
            "eval.sanity_min_chars": "3",
            "eval.sanity_error_markers": "ERROR:",
            "eval.keyword_semantic_pass_threshold": "0.65",
            "eval.judge_max_completion_tokens": "2048",
            "eval.judge_max_parse_retries": "1",
            "eval.force_judge_on_prior_failure": boolean_value,
        }
    )

    parameters = parse_evaluation_parameters(snapshot)

    assert parameters.force_judge_on_prior_failure is expected_result
