"""Proves: STORY-067-AC-2

Table-driven: for each validation input, the cascade produces the specified
severity and Save enablement (`06_Settings_Dialog/description.md` §15).
Covers EC-SET-3.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.ui.settings_dialog._internal.validation import save_enabled, validate_all
from ollama_llm_bench.ui.settings_dialog.models import Severity


def _base_general_values() -> dict[str, str]:
    return {
        "benchmark.min_timeout_seconds": "300",
        "benchmark.max_timeout_seconds": "900",
        "eval.judge_timeout_min_seconds": "20",
        "eval.judge_timeout_max_seconds": "120",
        "eval.cosine_threshold": "0.85",
    }


def test_two_providers_sharing_a_name_is_a_hard_error(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    providers = (
        provider_config_factory(name="OpenAI"),
        provider_config_factory(name="OpenAI"),
    )

    findings = validate_all(providers=providers, general_values=_base_general_values())

    assert any(f.severity is Severity.HARD_ERROR and "name" in f.message.lower() for f in findings)
    assert save_enabled(findings, is_dirty=True) is False


def test_max_timeout_less_than_min_timeout_is_a_hard_error(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    values = _base_general_values()
    values["benchmark.max_timeout_seconds"] = "100"
    values["benchmark.min_timeout_seconds"] = "300"

    findings = validate_all(providers=(provider_config_factory(name="A"),), general_values=values)

    assert any(f.severity is Severity.HARD_ERROR for f in findings)
    assert save_enabled(findings, is_dirty=True) is False


def test_cleared_numeric_field_is_a_hard_error(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    values = _base_general_values()
    values["benchmark.min_timeout_seconds"] = ""

    findings = validate_all(providers=(provider_config_factory(name="A"),), general_values=values)

    assert any(f.severity is Severity.HARD_ERROR for f in findings)
    assert save_enabled(findings, is_dirty=True) is False


def test_unset_env_var_is_a_soft_warning_and_allows_save(
    provider_config_factory: Callable[..., ProviderConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISSING_TEST_VAR", raising=False)
    provider = provider_config_factory(name="A", api_key_raw="MISSING_TEST_VAR")

    findings = validate_all(providers=(provider,), general_values=_base_general_values())

    assert any(f.severity is Severity.SOFT_WARNING for f in findings)
    assert save_enabled(findings, is_dirty=True) is True


def test_no_findings_and_dirty_enables_save(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    findings = validate_all(
        providers=(provider_config_factory(name="A"),), general_values=_base_general_values()
    )

    assert findings == ()
    assert save_enabled(findings, is_dirty=True) is True


def test_no_findings_and_clean_disables_save(
    provider_config_factory: Callable[..., ProviderConfig],
) -> None:
    findings = validate_all(
        providers=(provider_config_factory(name="A"),), general_values=_base_general_values()
    )

    assert save_enabled(findings, is_dirty=False) is False
