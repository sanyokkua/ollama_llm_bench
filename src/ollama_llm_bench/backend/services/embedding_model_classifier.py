"""EmbeddingModelClassifier — pattern-based detector for embedding-only models."""

import logging

logger = logging.getLogger(__name__)

_DEFAULT_PATTERNS: tuple[str, ...] = (
    "bge",
    "nomic",
    "gte",
    "jina",
    "stella",
    "mxbai",
    "arctic-embed",
    "embed",
    "embedding",
    "clip",
    "imagebind",
    "minilm",
    "sentence-transformer",
    "all-minilm",
    "qwen2-embedding",
    "voyage",
    "cohere-embed",
    "e5-",
    "-e5",
)


class EmbeddingModelClassifier:
    """Detects whether a model name refers to an embedding-only model.

    Uses substring matching against a set of known embedding model name
    patterns. Callers may supply additional patterns at construction time
    to extend the built-in list.

    Args:
        extra_patterns: Additional lowercase substrings to match beyond the
            built-in defaults.
    """

    def __init__(self, *, extra_patterns: tuple[str, ...] = ()) -> None:
        cleaned = tuple(p.strip().lower() for p in extra_patterns if p.strip())
        self._patterns: tuple[str, ...] = _DEFAULT_PATTERNS + cleaned

    def is_embedding_model(self, model_name: str) -> bool:
        """Return True if model_name matches any known embedding pattern.

        Args:
            model_name: Raw model name string as returned by the provider.

        Returns:
            True when the name contains a known embedding-model substring.
        """
        lower = model_name.lower()
        return any(p in lower for p in self._patterns)
