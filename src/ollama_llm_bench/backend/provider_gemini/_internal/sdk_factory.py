"""Constructs the underlying ``google-genai`` SDK client for one provider (§6.9)."""

from google import genai
from google.genai import types

from ollama_llm_bench.backend.domain import ProviderConfig

__all__: list[str] = ["build_sdk_client"]

_NO_RETRY_ATTEMPTS = 1


def build_sdk_client(
    config: ProviderConfig, resolved_api_key: str, *, connect_timeout_ms: int
) -> genai.Client:
    """Build the ``google-genai`` SDK client (§6.9).

    Never issues a network call — pure object assembly. SDK-level automatic
    retries are disabled (``HttpRetryOptions(attempts=1)`` — the SDK defaults
    to 5 attempts otherwise): the application's own retry policy owns retry
    decisions, and the SDK retrying underneath it would both distort measured
    latency and race the cooperative ``CancellationToken``, exactly as
    ``AnthropicClient``'s ``max_retries=0`` and the OpenAI-compatible
    client's equivalent setting already do.

    Args:
        config: The provider configuration; ``base_url`` overrides the
            provider default endpoint only when set — confirmed to work in
            plain API-key mode (``_base_url.get_base_url`` checks
            ``http_options.base_url`` unconditionally, before any
            Vertex-specific branch).
        resolved_api_key: The already-resolved secret value (required for
            Gemini — never a placeholder, unlike a keyless local host).
        connect_timeout_ms: The connection-establishment timeout applied to
            every call issued by the constructed client; the SDK exposes one
            ``HttpOptions.timeout`` (milliseconds) covering the whole
            request, not a distinct connect-vs-read split — every actual
            chat/probe call still overrides this per-call with its own
            finite deadline (the finite-deadline invariant, SPEC-015, is
            enforced at the call site, not here).

    Returns:
        A constructed ``genai.Client`` instance, not yet used for any call.
    """
    http_options = types.HttpOptions(
        timeout=connect_timeout_ms,
        retry_options=types.HttpRetryOptions(attempts=_NO_RETRY_ATTEMPTS),
    )
    if config.base_url:
        http_options.base_url = config.base_url
    return genai.Client(api_key=resolved_api_key, http_options=http_options)
