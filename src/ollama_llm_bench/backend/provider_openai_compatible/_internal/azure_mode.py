"""Azure-transport selection (SPEC-114)."""

from ollama_llm_bench.backend.domain import ProviderConfig

__all__: list[str] = ["is_azure_mode"]


def is_azure_mode(config: ProviderConfig) -> bool:
    """Return whether ``config`` selects the Azure OpenAI transport (SPEC-114).

    True iff all three ``azure_endpoint_raw``, ``azure_deployment_raw``, and
    ``azure_api_version_raw`` are non-empty. The any-but-not-all structural
    validation error is already enforced by ``provider_registry``'s
    ``client_builder.validate_structure()`` before this builder is ever
    called (STORY-017) — this function only decides which of the two
    equally-valid configurations it is looking at.

    Args:
        config: The provider configuration to inspect.

    Returns:
        ``True`` when the Azure transport should be used, ``False`` for
        plain OpenAI-compatible mode.
    """
    return bool(
        config.azure_endpoint_raw and config.azure_deployment_raw and config.azure_api_version_raw
    )
