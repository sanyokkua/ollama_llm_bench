"""Public factory for the reusable enabled-providers dropdown (08-E §9, 08-J §5.6)."""

from collections.abc import Callable

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.shared.provider_dropdown._internal.view import ProviderDropdownWidget
from ollama_llm_bench.ui.shared.provider_dropdown.protocols import ProviderListSource

__all__: list[str] = ["ProviderListSource", "make_provider_dropdown"]


@icontract.require(
    lambda provider_source: provider_source is not None,
    "provider_source is a required collaborator wired by the consumer",
)
@icontract.require(
    lambda event_bus: event_bus is not None,
    "event_bus is a required collaborator wired by the consumer",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_provider_dropdown(
    *,
    provider_source: ProviderListSource,
    event_bus: EventBus,
    filter: Callable[[ProviderConfig], bool] | None = None,  # noqa: A002  # matches the spec's documented `filter` parameter name (01_MODULE_INVENTORY.md §6)
) -> QWidget:
    """Build a QComboBox listing `provider_source`'s enabled providers by name.

    Args:
        provider_source: Read-only access to the enabled-provider catalog.
        event_bus: The bus this widget rebuilds itself from on `_provider_registry_reloaded`.
        filter: When given, only providers for which `filter(provider)` returns `True` appear.

    Returns:
        The mountable widget; emits `provider_changed(provider_id: str)` on user selection.
    """
    return ProviderDropdownWidget(
        provider_source=provider_source, event_bus=event_bus, provider_filter=filter
    )
