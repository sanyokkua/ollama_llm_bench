"""Construction-time DTOs owned by ``backend/provider_gemini/``.

``GeminiClientSettings`` groups ``make_gemini_client``'s timeout/bound keyword
arguments into one ``msgspec.Struct`` bundle so the factory's own parameter
count stays within the project's limit (`coding-style.md`'s dependency-bundle
pattern) — mirrors ``provider_openai_compatible/models.py`` and
``provider_anthropic/models.py``. Unlike ``AnthropicClientSettings``, this
struct carries ``embedding_model``/``embedding_timeout_ms``: Gemini exposes a
real embeddings endpoint (§6.7, §6.9), so this client's ``embed`` issues a
genuine call rather than always raising.
"""

import msgspec

__all__: list[str] = ["GeminiClientSettings"]

_DEFAULT_CONNECT_TIMEOUT_MS = 5000
_DEFAULT_PROBE_TIMEOUT_MS = 5000
_DEFAULT_EMBEDDING_TIMEOUT_MS = 20000
_DEFAULT_INFERENCE_TEST_TIMEOUT_MS = 30000
_DEFAULT_HARD_CANCEL_MAX_MS = 2000


class GeminiClientSettings(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The timeout/bound configuration for one ``GEMINI`` client (§7).

    Every field carries the spec-mandated default (`02_LLM_CLIENT_PROTOCOL.md`
    §7); a caller resolving the corresponding settings keys
    (``provider.probe_timeout_ms`` etc.) overrides the relevant fields.
    ``embedding_model`` is ``None`` for a client never used for ``embed`` —
    ``embed`` then raises immediately rather than issuing a network call with
    an unresolved model name.
    """

    connect_timeout_ms: int = _DEFAULT_CONNECT_TIMEOUT_MS
    probe_timeout_ms: int = _DEFAULT_PROBE_TIMEOUT_MS
    embedding_timeout_ms: int = _DEFAULT_EMBEDDING_TIMEOUT_MS
    inference_test_timeout_ms: int = _DEFAULT_INFERENCE_TEST_TIMEOUT_MS
    hard_cancel_max_ms: int = _DEFAULT_HARD_CANCEL_MAX_MS
    embedding_model: str | None = None
