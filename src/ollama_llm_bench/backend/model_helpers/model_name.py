"""ModelNameParser — pure model-name parsing (§4.7).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§4.7. ``parse_model_name`` splits a provider model string into ``model_family``,
``model_params_b``, and ``quantization``, populating the parsed fields of
``BenchmarkRunModelEntry``. It never raises: an unparseable component is returned as
``None``.
"""

import re

import msgspec

from ollama_llm_bench.backend.domain import PositiveInt

__all__: list[str] = ["ModelNameParsed", "parse_model_name"]

_PARAMS_PATTERN: re.Pattern[str] = re.compile(r"(?<![\w.])(\d+)[bB](?![\w])")
_QUANTIZATION_PATTERN: re.Pattern[str] = re.compile(r"\bq\d+(?:_[A-Za-z0-9]+)*\b")


class ModelNameParsed(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The three components extracted from a provider model string (§4.7).

    An unparseable component is ``None`` rather than raising.
    """

    model_family: str | None
    model_params_b: PositiveInt | None
    quantization: str | None


def _extract_params_b(tag: str) -> PositiveInt | None:
    """Extract a leading parameter-count-in-billions token from a tag, if present."""
    match = _PARAMS_PATTERN.search(tag)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        # Defensive: the pattern only captures digits, so this branch is unreachable
        # in practice, but no parsing branch may ever let an exception escape (AC-2).
        return None


def _extract_quantization(tag: str) -> str | None:
    """Extract a quantization-shaped token from a tag, if present."""
    match = _QUANTIZATION_PATTERN.search(tag)
    if match is None:
        return None
    return match.group(0)


def parse_model_name(model_string: str) -> ModelNameParsed:
    """Parse a provider model string into family, parameter count, and quantization.

    Splits on ``:`` first (Ollama-style ``family:tag``, e.g. ``qwen3:8b-q4_K_M``): the
    left side is ``model_family`` when non-empty, and the right side (if present) is
    searched for a parameter count and a quantization token. When there is no ``:``,
    the whole string is both the candidate family and the tag searched for a
    parameter count and quantization token (e.g. ``nomic-embed-text``).

    Args:
        model_string: The raw provider-reported model identifier. May be any string,
            including malformed or empty input — this function never raises.

    Returns:
        A ``ModelNameParsed`` value with ``None`` for any component that could not be
        parsed from ``model_string``.
    """
    if not model_string:
        return ModelNameParsed(model_family=None, model_params_b=None, quantization=None)

    family_part, sep, tag_part = model_string.partition(":")
    model_family = family_part if family_part else None
    search_space = tag_part if sep else model_string

    return ModelNameParsed(
        model_family=model_family,
        model_params_b=_extract_params_b(search_space),
        quantization=_extract_quantization(search_space),
    )
