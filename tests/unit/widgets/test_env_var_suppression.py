"""Unit tests for _should_prompt_for_envvar — local-trivial-key suppression."""

import pytest

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import _should_prompt_for_envvar


def _make_cfg(*, api_key_raw: str, base_url: str | None = None) -> ProviderConfig:
    return ProviderConfig(
        provider_id="test_provider",
        label="Test",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="",
        api_key_raw=api_key_raw,
        enabled=True,
        base_url=base_url,
    )


class TestEmptyAndEnvRefKeys:
    def test_empty_key_does_not_prompt(self) -> None:
        assert _should_prompt_for_envvar(_make_cfg(api_key_raw="")) is False

    def test_env_var_reference_does_not_prompt(self) -> None:
        assert _should_prompt_for_envvar(_make_cfg(api_key_raw="${MY_API_KEY}")) is False

    def test_env_var_reference_uppercase_does_not_prompt(self) -> None:
        assert _should_prompt_for_envvar(_make_cfg(api_key_raw="${OPENAI_KEY}")) is False


class TestLocalTrivialKeys:
    @pytest.mark.parametrize(
        "key",
        ["ollama", "lm-studio", "lmstudio", "none", "no-key", "sk-no-key-required", ""],
        ids=["ollama", "lm-studio", "lmstudio", "none", "no-key", "sk-no-key-required", "empty"],
    )
    def test_trivial_key_with_localhost_does_not_prompt(self, key: str) -> None:
        cfg = _make_cfg(api_key_raw=key, base_url="http://localhost:11434")
        assert _should_prompt_for_envvar(cfg) is False

    def test_trivial_key_with_127_0_0_1_does_not_prompt(self) -> None:
        cfg = _make_cfg(api_key_raw="ollama", base_url="http://127.0.0.1:11434")
        assert _should_prompt_for_envvar(cfg) is False

    def test_trivial_key_with_lm_studio_port_does_not_prompt(self) -> None:
        cfg = _make_cfg(api_key_raw="lm-studio", base_url="http://localhost:1234/v1")
        assert _should_prompt_for_envvar(cfg) is False

    def test_trivial_key_with_remote_url_does_prompt(self) -> None:
        cfg = _make_cfg(api_key_raw="ollama", base_url="https://api.example.com")
        assert _should_prompt_for_envvar(cfg) is True

    def test_trivial_key_with_no_url_does_prompt(self) -> None:
        cfg = _make_cfg(api_key_raw="none", base_url=None)
        assert _should_prompt_for_envvar(cfg) is True


class TestRealApiKeys:
    def test_real_openai_key_prompts(self) -> None:
        cfg = _make_cfg(api_key_raw="sk-abc123xyz", base_url="https://api.openai.com/v1")
        assert _should_prompt_for_envvar(cfg) is True

    def test_real_anthropic_key_prompts(self) -> None:
        cfg = _make_cfg(api_key_raw="sk-ant-api03-realkey", base_url="https://api.anthropic.com")
        assert _should_prompt_for_envvar(cfg) is True

    def test_real_key_with_localhost_still_prompts(self) -> None:
        # A real key value, even on localhost, should be offered for conversion.
        cfg = _make_cfg(api_key_raw="sk-real-key-abc123", base_url="http://localhost:8080")
        assert _should_prompt_for_envvar(cfg) is True
