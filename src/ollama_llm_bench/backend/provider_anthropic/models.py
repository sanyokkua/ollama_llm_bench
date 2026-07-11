"""Construction-time DTOs owned by ``backend/provider_anthropic/``.

``AnthropicClientSettings`` groups ``make_anthropic_client``'s timeout/bound
keyword arguments into one ``msgspec.Struct`` bundle so the factory's own
parameter count stays within the project's limit (`coding-style.md`'s
dependency-bundle pattern) — mirrors ``provider_openai_compatible/models.py``.
There is no ``embedding_model``/``embedding_timeout_ms`` field: Anthropic
exposes no embeddings endpoint at all, so this client's ``embed`` always
raises immediately regardless of settings.
"""

import msgspec

__all__: list[str] = ["AnthropicClientSettings"]

_DEFAULT_CONNECT_TIMEOUT_MS = 5000
_DEFAULT_PROBE_TIMEOUT_MS = 5000
_DEFAULT_INFERENCE_TEST_TIMEOUT_MS = 30000
_DEFAULT_HARD_CANCEL_MAX_MS = 2000


class AnthropicClientSettings(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The timeout/bound configuration for one ``ANTHROPIC`` client (§7).

    Every field carries the spec-mandated default (`02_LLM_CLIENT_PROTOCOL.md`
    §7); a caller resolving the corresponding settings keys
    (``provider.probe_timeout_ms`` etc.) overrides the relevant fields.
    """

    connect_timeout_ms: int = _DEFAULT_CONNECT_TIMEOUT_MS
    probe_timeout_ms: int = _DEFAULT_PROBE_TIMEOUT_MS
    inference_test_timeout_ms: int = _DEFAULT_INFERENCE_TEST_TIMEOUT_MS
    hard_cancel_max_ms: int = _DEFAULT_HARD_CANCEL_MAX_MS
