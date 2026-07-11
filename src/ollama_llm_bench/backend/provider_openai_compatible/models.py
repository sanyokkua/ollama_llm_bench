"""Construction-time DTOs owned by ``backend/provider_openai_compatible/``.

``OpenAICompatibleClientSettings`` groups ``make_openai_client``'s timeout/bound
keyword arguments into one ``msgspec.Struct`` bundle so the factory's own
parameter count stays within the project's limit (`coding-style.md`'s
dependency-bundle pattern). The collaborator bundle (``Clock``/``EventBus``/
``InferenceActivityStore``) is declared separately, in ``_internal/collaborators.py``,
as a plain class rather than a ``msgspec.Struct`` — a ``Protocol``-typed field
cannot round-trip through ``msgspec.convert``'s runtime instance checks unless
the Protocol is ``@runtime_checkable``, which these deliberately are not
(`protocol-first-interfaces` skill).
"""

import msgspec

__all__: list[str] = ["OpenAICompatibleClientSettings"]

_DEFAULT_CONNECT_TIMEOUT_MS = 5000
_DEFAULT_PROBE_TIMEOUT_MS = 5000
_DEFAULT_EMBEDDING_TIMEOUT_MS = 20000
_DEFAULT_INFERENCE_TEST_TIMEOUT_MS = 30000
_DEFAULT_HARD_CANCEL_MAX_MS = 2000


class OpenAICompatibleClientSettings(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The timeout/bound configuration for one ``OPENAI_COMPATIBLE`` client (§7).

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
