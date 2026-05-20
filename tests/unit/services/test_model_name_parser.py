"""Unit tests for ModelNameParser service.

Covers real-world Ollama model name corpus: family parsing, size extraction,
quantization label extraction, unsupported quant labels, no-colon cloud model
names, full round-trip assertions, and edge cases.
"""

import pytest

from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser


@pytest.fixture
def parser() -> ModelNameParser:
    """Stateless ModelNameParser instance — no mocks needed."""
    return ModelNameParser()


# ---------------------------------------------------------------------------
# Family parsing — strips trailing `.N` version suffix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name", "expected_family"),
    [
        ("qwen3.6:27b", "qwen3"),
        ("qwen3.5:9b", "qwen3"),
        ("granite4.1:3b", "granite4"),
        ("mistral-medium-3.5:128b", "mistral-medium-3"),
        ("laguna-xs.2:q4_K_M", "laguna-xs"),
        ("gemma4:31b", "gemma4"),
        ("ministral-3:8b", "ministral-3"),
        ("nemotron3:33b", "nemotron3"),
        ("nomic-embed-text:v1.5", "nomic-embed-text"),
        ("gpt-oss:20b", "gpt-oss"),
        ("qwen3-embedding:8b", "qwen3-embedding"),
        ("functiongemma:270m", "functiongemma"),
        ("embeddinggemma:300m", "embeddinggemma"),
    ],
    ids=[
        "qwen3.6_strips_to_qwen3",
        "qwen3.5_strips_to_qwen3",
        "granite4.1_strips_to_granite4",
        "mistral_medium_3.5_strips_to_mistral_medium_3",
        "laguna_xs.2_strips_to_laguna_xs",
        "gemma4_no_version_suffix",
        "ministral_3_no_version_suffix",
        "nemotron3_no_version_suffix",
        "nomic_embed_text_v1.5_tag_ignored",
        "gpt_oss_hyphenated_no_suffix",
        "qwen3_embedding_hyphenated",
        "functiongemma_no_suffix",
        "embeddinggemma_no_suffix",
    ],
)
def test_parse_family_strips_trailing_version(
    parser: ModelNameParser,
    model_name: str,
    expected_family: str,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.model_family == expected_family


# ---------------------------------------------------------------------------
# Size parsing — extracts billions as float, `m` suffix → None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name", "expected_size"),
    [
        ("qwen3.5:0.8b", 0.8),
        ("qwen3.5:2b", 2.0),
        ("granite4.1:3b", 3.0),
        ("qwen3-embedding:4b", 4.0),
        ("mistral-medium-3:8b", 8.0),
        ("qwen3.5:9b", 9.0),
        ("granite4.1:30b", 30.0),
        ("nemotron3:33b", 33.0),
        ("qwen3.6:35b", 35.0),
        ("qwen3.5:122b", 122.0),
        ("mistral-medium-3.5:128b", 128.0),
        ("qwen3.5:latest", None),
        ("nomic-embed-text:v1.5", None),
        ("functiongemma:270m", None),
        ("nomic-embed-text:137m-v1.5-fp16", None),
        ("laguna-xs.2:mxfp8", None),
    ],
    ids=[
        "fractional_0.8b",
        "2b_integer",
        "3b_integer",
        "4b_integer",
        "8b_integer",
        "9b_integer",
        "30b_integer",
        "33b_integer",
        "35b_integer",
        "122b_three_digits",
        "128b_three_digits",
        "latest_tag_no_size",
        "v1.5_tag_no_b_suffix",
        "270m_suffix_not_b",
        "137m_suffix_not_b_with_fp16",
        "mxfp8_no_size_token",
    ],
)
def test_parse_size_extracts_billions(
    parser: ModelNameParser,
    model_name: str,
    expected_size: float | None,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.model_size_b == expected_size


# ---------------------------------------------------------------------------
# Size extracted from MoE-style variant prefix (e.g. "e2b" → 2.0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name", "expected_size"),
    [
        ("gemma4:e2b", 2.0),
        ("gemma4:e4b", 4.0),
        ("gemma4:e2b-it-q4_K_M", 2.0),
    ],
    ids=[
        "e2b_moe_extracts_2b",
        "e4b_moe_extracts_4b",
        "e2b_with_variant_suffix_extracts_2b",
    ],
)
def test_parse_size_from_moe_variant_prefix(
    parser: ModelNameParser,
    model_name: str,
    expected_size: float,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.model_size_b == expected_size


# ---------------------------------------------------------------------------
# Quantization label — extracts known GGUF / float format labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name", "expected_quant"),
    [
        ("granite4.1:3b-q2_K", "q2_K"),
        ("granite4.1:3b-q3_K_S", "q3_K_S"),
        ("granite4.1:3b-q3_K_M", "q3_K_M"),
        ("granite4.1:3b-q3_K_L", "q3_K_L"),
        ("granite4.1:3b-q4_0", "q4_0"),
        ("granite4.1:3b-q4_1", "q4_1"),
        ("granite4.1:3b-q4_K_S", "q4_K_S"),
        ("granite4.1:3b-q4_K_M", "q4_K_M"),
        ("granite4.1:3b-q5_0", "q5_0"),
        ("granite4.1:3b-q5_1", "q5_1"),
        ("granite4.1:3b-q5_K_S", "q5_K_S"),
        ("granite4.1:3b-q5_K_M", "q5_K_M"),
        ("granite4.1:3b-q6_K", "q6_K"),
        ("granite4.1:3b-q8_0", "q8_0"),
        ("qwen3.6:27b-bf16", "bf16"),
        ("mistral-medium-3.5:128b-bf16", "bf16"),
        ("granite4.1:30b-bf16", "bf16"),
        ("ministral-3:3b-instruct-2512-fp16", "fp16"),
        ("nomic-embed-text:137m-v1.5-fp16", "fp16"),
        ("embeddinggemma:300m-qat-q8_0", "qat"),
        ("qwen3.6:27b-mlx-bf16", "bf16"),
    ],
    ids=[
        "q2_K",
        "q3_K_S",
        "q3_K_M",
        "q3_K_L",
        "q4_0",
        "q4_1",
        "q4_K_S",
        "q4_K_M",
        "q5_0",
        "q5_1",
        "q5_K_S",
        "q5_K_M",
        "q6_K",
        "q8_0",
        "bf16_qwen3",
        "bf16_mistral_medium",
        "bf16_granite",
        "fp16_ministral_with_instruct",
        "fp16_nomic_embed",
        "qat_wins_leftmost_over_q8_0",
        "bf16_after_mlx_runtime_tag",
    ],
)
def test_parse_quantization_label_extracts_known_format(
    parser: ModelNameParser,
    model_name: str,
    expected_quant: str,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.quantization_label == expected_quant


# ---------------------------------------------------------------------------
# Unsupported quant labels — known parser limits; must return None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name",),
    [
        ("nemotron3:33b-q8",),
        ("qwen3.6:27b-mxfp8",),
        ("qwen3.6:27b-nvfp4",),
        ("qwen3.5:27b-int4",),
        ("qwen3.5:27b-int8",),
        ("laguna-xs.2:mxfp8",),
        ("laguna-xs.2:nvfp4",),
    ],
    ids=[
        "q8_without_suffix_not_matched",
        "mxfp8_not_in_pattern",
        "nvfp4_not_in_pattern",
        "int4_not_in_pattern",
        "int8_not_in_pattern",
        "mxfp8_as_only_tag",
        "nvfp4_as_only_tag",
    ],
)
def test_parse_unsupported_quant_label_returns_none(
    parser: ModelNameParser,
    model_name: str,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert — documented parser limitation
    assert result.quantization_label is None


# ---------------------------------------------------------------------------
# No-colon names (cloud / opaque model identifiers) → all None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name",),
    [
        ("gpt-4o",),
        ("claude-sonnet-4-6",),
        ("gemini-2.0-flash",),
        ("text-embedding-ada-002",),
    ],
    ids=[
        "gpt_4o",
        "claude_sonnet_4_6",
        "gemini_2_flash",
        "text_embedding_ada",
    ],
)
def test_parse_no_colon_name_returns_all_none(
    parser: ModelNameParser,
    model_name: str,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.model_family is None
    assert result.model_size_b is None
    assert result.quantization_label is None


# ---------------------------------------------------------------------------
# Full round-trip — all three fields verified together
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_name", "expected_family", "expected_size", "expected_quant"),
    [
        ("qwen3.5:27b-q4_K_M", "qwen3", 27.0, "q4_K_M"),
        ("qwen3.5:35b-a3b-q8_0", "qwen3", 35.0, "q8_0"),
        ("granite4.1:8b-q4_K_M", "granite4", 8.0, "q4_K_M"),
        ("mistral-medium-3.5:128b-q4_K_M", "mistral-medium-3", 128.0, "q4_K_M"),
        ("gemma4:31b-it-q4_K_M", "gemma4", 31.0, "q4_K_M"),
        ("gemma4:e4b-it-bf16", "gemma4", 4.0, "bf16"),
        ("ministral-3:8b-instruct-2512-q4_K_M", "ministral-3", 8.0, "q4_K_M"),
        ("qwen3-embedding:8b-fp16", "qwen3-embedding", 8.0, "fp16"),
        ("qwen3.5:0.8b-q8_0", "qwen3", 0.8, "q8_0"),
        ("nomic-embed-text:137m-v1.5-fp16", "nomic-embed-text", None, "fp16"),
        ("functiongemma:270m-it-q8_0", "functiongemma", None, "q8_0"),
    ],
    ids=[
        "qwen3.5_27b_q4_K_M",
        "qwen3.5_35b_a3b_moe_q8_0",
        "granite4.1_8b_q4_K_M",
        "mistral_medium_3.5_128b_q4_K_M",
        "gemma4_31b_it_q4_K_M",
        "gemma4_e4b_moe_bf16",
        "ministral_3_8b_instruct_q4_K_M",
        "qwen3_embedding_8b_fp16",
        "qwen3.5_0.8b_q8_0_fractional",
        "nomic_embed_text_137m_fp16_size_none",
        "functiongemma_270m_q8_0_size_none",
    ],
)
def test_parse_full_round_trip(
    parser: ModelNameParser,
    model_name: str,
    expected_family: str | None,
    expected_size: float | None,
    expected_quant: str | None,
) -> None:
    # Act
    result = parser.parse(model_name)

    # Assert
    assert result.model_family == expected_family
    assert result.model_size_b == expected_size
    assert result.quantization_label == expected_quant


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_parse_empty_string_returns_all_none(parser: ModelNameParser) -> None:
    # Act
    result = parser.parse("")

    # Assert
    assert result.model_family is None
    assert result.model_size_b is None
    assert result.quantization_label is None


def test_parse_latest_tag_has_family_and_no_size_or_quant(parser: ModelNameParser) -> None:
    # Act
    result = parser.parse("model:latest")

    # Assert
    assert result.model_family == "model"
    assert result.model_size_b is None
    assert result.quantization_label is None


def test_parse_opaque_variant_tag_has_family_and_no_size_or_quant(parser: ModelNameParser) -> None:
    # Arrange — "cloud" is a variant tag with no numeric or quant content
    # Act
    result = parser.parse("qwen3.5:cloud")

    # Assert
    assert result.model_family == "qwen3"
    assert result.model_size_b is None
    assert result.quantization_label is None


def test_parse_long_hyphenated_family_with_latest_returns_family_no_size_quant(
    parser: ModelNameParser,
) -> None:
    # Act
    result = parser.parse("nomic-embed-text-v2-moe:latest")

    # Assert
    assert result.model_family == "nomic-embed-text-v2-moe"
    assert result.model_size_b is None
    assert result.quantization_label is None
