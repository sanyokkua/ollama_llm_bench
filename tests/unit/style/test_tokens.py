"""Unit tests for ui/style/tokens.py — token dicts and get_tokens() factory."""

import pytest

from ollama_llm_bench.ui.style.tokens import DARK_TOKENS, LIGHT_TOKENS, get_tokens


class TestGetTokensDark:
    def test_returns_dark_bg_primary(self) -> None:
        tokens = get_tokens("dark")
        assert tokens["bg_primary"] == "#111827"

    def test_includes_shared_tokens(self) -> None:
        tokens = get_tokens("dark")
        assert "spacing_xs" in tokens

    def test_dark_tokens_override_shared_on_collision(self) -> None:
        tokens = get_tokens("dark")
        for key in DARK_TOKENS:
            assert tokens[key] == DARK_TOKENS[key]


class TestGetTokensLight:
    def test_returns_light_bg_primary(self) -> None:
        tokens = get_tokens("light")
        assert tokens["bg_primary"] == "#FDFDFD"

    def test_includes_shared_tokens(self) -> None:
        tokens = get_tokens("light")
        assert "spacing_xs" in tokens

    def test_light_tokens_override_shared_on_collision(self) -> None:
        tokens = get_tokens("light")
        for key in LIGHT_TOKENS:
            assert tokens[key] == LIGHT_TOKENS[key]


class TestGetTokensFallback:
    def test_unknown_theme_falls_back_to_dark(self, caplog: pytest.LogCaptureFixture) -> None:
        tokens = get_tokens("banana")
        assert tokens["bg_primary"] == DARK_TOKENS["bg_primary"]
        assert "unknown_theme_requested" in caplog.text

    def test_unknown_theme_includes_shared_tokens(self) -> None:
        tokens = get_tokens("unknown_xyz")
        assert "spacing_xs" in tokens
