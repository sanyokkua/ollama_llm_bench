"""Proves STORY-026-AC-1 and STORY-026-AC-2 — the model-name parser (§4.7)."""

from hypothesis import given, strategies as st
import pytest

from ollama_llm_bench.backend.model_helpers import ModelNameParsed, parse_model_name


@pytest.mark.parametrize(
    ("model_string", "expected"),
    [
        (
            "qwen3:8b-q4_K_M",
            ModelNameParsed(model_family="qwen3", model_params_b=8, quantization="q4_K_M"),
        ),
        (
            "llama3.1:70b",
            ModelNameParsed(model_family="llama3.1", model_params_b=70, quantization=None),
        ),
        (
            "nomic-embed-text",
            ModelNameParsed(
                model_family="nomic-embed-text", model_params_b=None, quantization=None
            ),
        ),
        ("", ModelNameParsed(model_family=None, model_params_b=None, quantization=None)),
        (
            "mistral:7b-instruct-q8_0",
            ModelNameParsed(model_family="mistral", model_params_b=7, quantization="q8_0"),
        ),
        (
            "gpt-4o-mini",
            ModelNameParsed(model_family="gpt-4o-mini", model_params_b=None, quantization=None),
        ),
    ],
)
def test_parse_model_name_extracts_components(model_string: str, expected: ModelNameParsed) -> None:
    """Proves: STORY-026-AC-1

    parse_model_name extracts model_family, model_params_b, and quantization per
    the story's example table (plus additional real-world provider model strings),
    returning None for any component it cannot parse.
    """
    assert parse_model_name(model_string) == expected


@pytest.mark.slow
@pytest.mark.property
@given(st.text())
def test_parse_model_name_never_raises(model_string: str) -> None:
    """Proves: STORY-026-AC-2

    For every model string, parse_model_name returns a ModelNameParsed value and
    never raises — an unparseable or malformed string yields None components
    rather than an exception.
    """
    result = parse_model_name(model_string)

    assert isinstance(result, ModelNameParsed)
