"""Constructs the underlying ``anthropic`` SDK client for one provider (§6.9)."""

import anthropic
import httpx

from ollama_llm_bench.backend.domain import ProviderConfig

__all__: list[str] = ["build_sdk_client"]


def build_sdk_client(
    config: ProviderConfig, resolved_api_key: str, *, connect_timeout_ms: int
) -> anthropic.Anthropic:
    """Build the ``anthropic`` SDK client (§6.9 — no Azure-equivalent branch).

    Never issues a network call — pure object assembly. SDK-level automatic
    retries are disabled (``max_retries=0``): the application's own retry
    policy owns retry decisions, and the SDK retrying underneath it would
    both distort measured latency and race the cooperative
    ``CancellationToken``.

    Args:
        config: The provider configuration; ``base_url`` overrides the
            provider default endpoint only when set.
        resolved_api_key: The already-resolved secret value (required for
            Anthropic — never a placeholder, unlike a keyless local host).
        connect_timeout_ms: The connection-establishment timeout applied to
            every call issued by the constructed client, independent of each
            call's own per-call response deadline.

    Returns:
        A constructed ``anthropic.Anthropic`` instance, not yet used for any
        call.
    """
    # `read=None`/`write=None`/`pool=None` here are the SDK-level defaults; every
    # actual chat/probe call overrides `timeout=` per-call with its own finite
    # read/pool budget — the finite-deadline invariant (SPEC-015) is enforced at
    # the CALL site, not here.
    timeout = httpx.Timeout(connect=connect_timeout_ms / 1000, read=None, write=None, pool=None)
    kwargs: dict[str, object] = {
        "api_key": resolved_api_key,
        "timeout": timeout,
        "max_retries": 0,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return anthropic.Anthropic(**kwargs)  # type: ignore[arg-type]  # dynamic kwargs; each key is SDK-typed
