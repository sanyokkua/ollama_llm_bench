"""Public factory for the reusable models-of-a-provider dropdown (08-E §10)."""

from collections.abc import Callable

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.backend.domain import ModelName
from ollama_llm_bench.ui.shared.model_dropdown._internal.view import ModelDropdownWidget
from ollama_llm_bench.ui.shared.model_dropdown.protocols import ModelFetcher

__all__: list[str] = ["ModelFetcher", "make_model_dropdown"]


@icontract.require(
    lambda model_fetcher: model_fetcher is not None,
    "model_fetcher is a required collaborator wired by the consumer",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_model_dropdown(
    *,
    model_fetcher: ModelFetcher,
    filter: Callable[[ModelName], bool] | None = None,  # noqa: A002  # matches the spec's documented `filter` parameter name (01_MODULE_INVENTORY.md §6)
) -> QWidget:
    """Build a QComboBox that lists a provider's models, driven by `set_provider(provider_id)`.

    Args:
        model_fetcher: Off-GUI-thread model-list access for whichever provider is selected.
        filter: When given, only models for which `filter(model)` returns `True` appear.

    Returns:
        The mountable widget; exposes `set_provider(provider_id)` and emits
        `model_changed(model_name: str)` on user selection.
    """
    return ModelDropdownWidget(model_fetcher=model_fetcher, model_filter=filter)
