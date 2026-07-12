"""EmbeddingModelClassifier — pure embedding-model name classification (§4.9).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§4.9. ``is_embedding_model`` decides, from a model name, whether the model is an
embedding-only model that must not be offered as an inference or judge target. It
never raises.
"""

__all__: list[str] = ["is_embedding_model"]

# Substring markers of a known embedding-only model family, drawn from real provider
# model names referenced across `docs/v3_specification/` (e.g.
# `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`, `02_New_Benchmark_Widget/description.md`,
# `10_Domain_and_Data/06_IMPORT_FORMATS.md`).
_EMBEDDING_MARKERS: tuple[str, ...] = (
    "embed",
    "bge-",
    "bge_",
    "gte-",
    "gte_",
    "e5-",
    "e5_",
    "minilm",
    "text-embedding",
)


def is_embedding_model(model_name: str) -> bool:
    """Decide whether a model name denotes an embedding-only model.

    Matches known embedding-model name markers (``embed``/``embedding``,
    ``bge-``, ``gte-``, ``e5-``, ``all-minilm``, ``text-embedding-*``, etc.)
    case-insensitively as substrings of ``model_name``.

    Args:
        model_name: The raw provider-reported model identifier. May be any string,
            including malformed or empty input — this function never raises.

    Returns:
        ``True`` when ``model_name`` matches a known embedding-model name pattern,
        ``False`` otherwise (including for a chat-capable model name or an
        unrecognized name).
    """
    if not model_name:
        return False
    lowered = model_name.lower()
    return any(marker in lowered for marker in _EMBEDDING_MARKERS)
