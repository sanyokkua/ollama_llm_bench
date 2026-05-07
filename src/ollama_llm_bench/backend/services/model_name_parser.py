"""Service for parsing Ollama-style model name strings into structured components."""

import logging
import re

from ollama_llm_bench.backend.core.models import ParsedModelName

# Strips a trailing version suffix from the family segment: "llama3.1" → "llama3"
_FAMILY_VERSION_RE = re.compile(r"\.\d+$")

# Matches size tokens like "8b", "13.8b", "70B"
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)[bB]")

# Matches GGUF quant labels (q4_K_M, q8_0, q2_K, …) and common float formats
_QUANT_RE = re.compile(r"\b(q\d+(?:_[A-Za-z0-9]+)+|qat|fp16|bf16|f32)\b")

logger = logging.getLogger(__name__)


class ModelNameParser:
    """Regex-based parser for Ollama model name strings.

    Supports the Ollama naming convention::

        {family}[.version]:{size}[b|B][-variant][-quantization]

    Names without a ``':'`` separator (cloud/opaque models such as ``gpt-4o``
    or ``claude-sonnet-4-6``) are returned as an all-None ``ParsedModelName``.
    Fields that cannot be extracted from the tag are individually set to ``None``.
    """

    def parse(self, model_name: str) -> ParsedModelName:
        """Parse a model name into family, size, and quantization components.

        Args:
            model_name: Full model name, e.g. ``'llama3.1:8b-instruct-q4_K_M'``.

        Returns:
            ParsedModelName with extracted fields; unparseable fields are None.
        """
        if ":" not in model_name:
            return ParsedModelName()

        family_raw, tag = model_name.split(":", 1)
        return ParsedModelName(
            model_family=self._parse_family(family_raw),
            model_size_b=self._parse_size(tag),
            quantization_label=self._parse_quantization(tag),
        )

    def _parse_family(self, family_raw: str) -> str | None:
        cleaned = _FAMILY_VERSION_RE.sub("", family_raw)
        return cleaned or None

    def _parse_size(self, tag: str) -> float | None:
        m = _SIZE_RE.search(tag)
        if m is None:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            logger.warning("Unexpected non-numeric size token '%s'", m.group(1))
            return None

    def _parse_quantization(self, tag: str) -> str | None:
        m = _QUANT_RE.search(tag)
        return m.group(1) if m else None
