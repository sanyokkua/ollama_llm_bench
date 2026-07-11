"""Constructs the underlying ``openai`` SDK client for one provider (§6.9, SPEC-114)."""

import httpx
import openai

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.provider_openai_compatible._internal.azure_mode import is_azure_mode

__all__: list[str] = ["build_sdk_client"]

_PLACEHOLDER_API_KEY = "not-needed"


def build_sdk_client(
    config: ProviderConfig, resolved_api_key: str, *, connect_timeout_ms: int
) -> openai.OpenAI:
    """Build the ``openai`` SDK client, selecting the Azure transport per SPEC-114.

    Never issues a network call — pure object assembly. SDK-level automatic
    retries are disabled (``max_retries=0``): the application's own retry
    policy owns retry decisions, and the SDK retrying underneath it would
    both distort measured latency and race the cooperative
    ``CancellationToken``.

    Args:
        config: The provider configuration selecting plain OpenAI-compatible
            or Azure transport.
        resolved_api_key: The already-resolved secret value; may be ``""``
            for a keyless local host.
        connect_timeout_ms: The connection-establishment timeout applied to
            every call issued by the constructed client, independent of each
            call's own per-call response deadline.

    Returns:
        A constructed ``openai.OpenAI`` (or ``openai.AzureOpenAI``, which is
        a subtype-compatible client) instance, not yet used for any call.
    """
    api_key = resolved_api_key or _PLACEHOLDER_API_KEY
    # `read=None`/`write=None`/`pool=None` here are the SDK-level defaults; every
    # actual chat/embed/probe call overrides `timeout=` per-call with its own
    # finite read/pool budget — the finite-deadline invariant (SPEC-015) is
    # enforced at the CALL site, not here.
    timeout = httpx.Timeout(connect=connect_timeout_ms / 1000, read=None, write=None, pool=None)
    if is_azure_mode(config):
        azure_endpoint = config.azure_endpoint_raw
        azure_deployment = config.azure_deployment_raw
        azure_api_version = config.azure_api_version_raw
        if azure_endpoint is None or azure_deployment is None or azure_api_version is None:
            message = "is_azure_mode() true implies all three azure_* fields are non-empty"  # pragma: no cover
            raise AssertionError(message)  # pragma: no cover
        return openai.AzureOpenAI(
            azure_endpoint=azure_endpoint,
            azure_deployment=azure_deployment,
            api_version=azure_api_version,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )
    return openai.OpenAI(base_url=config.base_url, api_key=api_key, timeout=timeout, max_retries=0)
