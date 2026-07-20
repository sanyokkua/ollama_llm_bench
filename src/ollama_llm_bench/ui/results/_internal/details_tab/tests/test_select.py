"""Unit tests for the Details tab's pure select.py — no Qt import."""

import pytest

from ollama_llm_bench.backend.domain import ResolutionLayer, ResultStatus, RunMode, Verdict
from ollama_llm_bench.ui.results._internal.details_tab.select import (
    DetailsColumnKey,
    badge_role_for_layer,
    badge_role_for_status,
    badge_role_for_verdict,
    chip_domains,
    offered_columns,
)
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result

_GRADED_ONLY_COUNT = 8
_TOTAL_COLUMNS = 24
_TWO_DISTINCT_MODEL_KEYS = 2


def test_graded_mode_offers_all_twenty_four_columns() -> None:
    """Proves: STORY-063

    §4 says GRADED offers all 24 columns of the §3 master list.
    """
    # Arrange / Act
    columns = offered_columns(RunMode.GRADED)
    # Assert
    assert len(columns) == _TOTAL_COLUMNS


def test_synthetic_mode_hides_the_eight_grading_columns() -> None:
    """Proves: STORY-063

    §4: SYNTHETIC and TASKS drop Sanity check, Keyword, Cosine Score, Cosine
    verdict, Judge, Layer, Verdict, Reason.
    """
    # Arrange / Act
    columns = offered_columns(RunMode.SYNTHETIC)
    # Assert
    assert len(columns) == _TOTAL_COLUMNS - _GRADED_ONLY_COUNT
    assert DetailsColumnKey.VERDICT not in columns
    assert DetailsColumnKey.PROVIDER_MODEL in columns


def test_chip_domains_lists_two_providers_of_the_same_model_separately() -> None:
    """Proves: STORY-063-AC-1

    Covers EC-RES-2. Two results share model_name "llama3" under two distinct
    provider_ids; the Models chip domain must list them as two separate entries.
    """
    # Arrange
    result_a = make_result(provider_id="prov-a", provider_name="Ollama Local", model_name="llama3")
    result_b = make_result(provider_id="prov-b", provider_name="Ollama Remote", model_name="llama3")
    # Act
    domains = chip_domains(results=(result_a, result_b), tasks_by_id={})
    # Assert
    assert len(domains.models) == _TWO_DISTINCT_MODEL_KEYS


@pytest.mark.parametrize(
    ("verdict", "expected_role"),
    [
        (Verdict.PASS, "success"),
        (Verdict.FAIL, "error"),
        (None, "muted"),
    ],
)
def test_badge_role_for_verdict(verdict: Verdict | None, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_verdict(verdict) == expected_role


@pytest.mark.parametrize(
    ("status", "expected_role"),
    [
        (ResultStatus.COMPLETED, "success"),
        (ResultStatus.FAILED_INFERENCE, "error"),
        (ResultStatus.FAILED_PROVIDER, "error"),
        (ResultStatus.FAILED_TIMEOUT, "error"),
        (ResultStatus.FAILED_JUDGE_TIMEOUT, "error"),
        (ResultStatus.ERRORED, "error"),
        (ResultStatus.PENDING, "info"),
        (ResultStatus.RUNNING_INFERENCE, "info"),
        (ResultStatus.AWAITING_KEYWORD_CHECK, "info"),
        (ResultStatus.AWAITING_COSINE_CHECK, "info"),
        (ResultStatus.AWAITING_JUDGE_CHECK, "info"),
    ],
)
def test_badge_role_for_status(status: ResultStatus, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_status(status) == expected_role


@pytest.mark.parametrize(
    ("layer", "expected_role"),
    [
        (ResolutionLayer.KEYWORD, "info"),
        (ResolutionLayer.COSINE, "info"),
        (ResolutionLayer.JUDGE, "info"),
        (ResolutionLayer.SKIP, "muted"),
        (None, "muted"),
    ],
)
def test_badge_role_for_layer(layer: ResolutionLayer | None, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_layer(layer) == expected_role
