"""Unit tests for ModelNameParser service."""

from dataclasses import FrozenInstanceError

import pytest

from ollama_llm_bench.backend.core.models import ParsedModelName
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser


@pytest.fixture
def parser() -> ModelNameParser:
    return ModelNameParser()


class TestModelNameParserOllamaNames:
    @pytest.mark.parametrize(
        "model_name,expected_family,expected_size,expected_quant",
        [
            ("llama3.1:8b-instruct-q4_K_M", "llama3", 8.0, "q4_K_M"),
            ("qwen3:8b", "qwen3", 8.0, None),
            ("llama3:latest", "llama3", None, None),
            ("llama3.1:13.8b-instruct-q4_K_M", "llama3", 13.8, "q4_K_M"),
            ("llama2:70B-chat-q5_K_M", "llama2", 70.0, "q5_K_M"),
            ("gemma3:12b-it-qat", "gemma3", 12.0, "qat"),
            ("llama3:7b-fp16", "llama3", 7.0, "fp16"),
            ("mistral:7b-instruct-bf16", "mistral", 7.0, "bf16"),
            ("phi3:14b-q8_0", "phi3", 14.0, "q8_0"),
            ("llama3:70b-q2_K", "llama3", 70.0, "q2_K"),
            ("nomic-embed-text:latest", "nomic-embed-text", None, None),
        ],
        ids=[
            "full_ollama_name_with_quant",
            "size_only",
            "latest_tag",
            "float_size_with_quant",
            "uppercase_b_with_quant",
            "qat_quantization",
            "fp16_format",
            "bf16_format",
            "q8_0_quant",
            "q2_K_two_part_quant",
            "embed_model_with_dashes",
        ],
    )
    def test_parse_ollama_model_names(
        self,
        parser: ModelNameParser,
        model_name: str,
        expected_family: str | None,
        expected_size: float | None,
        expected_quant: str | None,
    ) -> None:
        result = parser.parse(model_name)

        assert result.model_family == expected_family
        assert result.model_size_b == expected_size
        assert result.quantization_label == expected_quant


class TestModelNameParserCloudModels:
    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "gemini-2.0-flash",
            "gemini-2.5-pro",
        ],
        ids=[
            "gpt_4o",
            "gpt_4o_mini",
            "claude_sonnet",
            "claude_haiku_with_date",
            "gemini_flash",
            "gemini_pro",
        ],
    )
    def test_parse_cloud_model_returns_all_none(self, parser: ModelNameParser, model_name: str) -> None:
        result = parser.parse(model_name)

        assert result.model_family is None
        assert result.model_size_b is None
        assert result.quantization_label is None


class TestModelNameParserEdgeCases:
    def test_parse_empty_string_returns_all_none(self, parser: ModelNameParser) -> None:
        result = parser.parse("")

        assert result.model_family is None
        assert result.model_size_b is None
        assert result.quantization_label is None

    def test_parse_colon_only_returns_all_none(self, parser: ModelNameParser) -> None:
        result = parser.parse(":")

        assert result.model_family is None
        assert result.model_size_b is None
        assert result.quantization_label is None

    def test_parse_returns_parsed_model_name_instance(self, parser: ModelNameParser) -> None:
        result = parser.parse("llama3:8b")

        assert isinstance(result, ParsedModelName)

    def test_parse_result_is_frozen(self, parser: ModelNameParser) -> None:
        result = parser.parse("llama3:8b")

        with pytest.raises(FrozenInstanceError):
            result.model_family = "other"  # type: ignore[misc]

    def test_parse_family_version_stripped(self, parser: ModelNameParser) -> None:
        result = parser.parse("llama3.2:3b-instruct-fp16")

        assert result.model_family == "llama3"
        assert result.model_size_b == 3.0
        assert result.quantization_label == "fp16"

    def test_parse_family_no_version_unchanged(self, parser: ModelNameParser) -> None:
        result = parser.parse("mistral:7b")

        assert result.model_family == "mistral"
