"""Pure state -> ``NewBenchmarkViewModel`` derivation (STORY-054). No Qt import."""

from collections.abc import Mapping

import msgspec

from ollama_llm_bench.backend.domain import ProviderConfig, RunMode
from ollama_llm_bench.ui.new_benchmark._internal.section_visibility import visible_section_set
from ollama_llm_bench.ui.new_benchmark._internal.selection_store import SelectionStore
from ollama_llm_bench.ui.new_benchmark.models import (
    NewBenchmarkViewModel,
    SelectedModelPairViewModel,
    TaskFileRowViewModel,
)
from ollama_llm_bench.ui.new_benchmark.protocols import ModeVisibilityPolicy

__all__: list[str] = ["NewBenchmarkViewState", "select_view_model"]


class NewBenchmarkViewState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``select_view_model``'s non-``mode`` inputs (coding-style.md's 4-parameter
    hard maximum -- ``select_view_model`` would otherwise take 7 keyword arguments).

    Attributes:
        policy: The Mode Visibility Policy collaborator.
        task_file_rows: The Task Files section's current rows.
        selection: The Test Models section's selection store.
        provider_configs: Every known provider, keyed by ``provider_id``, for
            resolving a selected pair's display name.
        browsed_provider_id: The Test Models section's currently browsed provider.
        hide_embedding_models: The current hide-embedding checkbox state.
    """

    policy: ModeVisibilityPolicy
    task_file_rows: tuple[TaskFileRowViewModel, ...]
    selection: SelectionStore
    provider_configs: Mapping[str, ProviderConfig]
    browsed_provider_id: str | None
    hide_embedding_models: bool


def select_view_model(*, mode: RunMode, state: NewBenchmarkViewState) -> NewBenchmarkViewModel:
    """Derive the full widget ``ViewModel`` from current controller-held state.

    Args:
        mode: The currently selected run mode.
        state: Every other piece of controller-held state this derivation needs.

    Returns:
        The frozen ``NewBenchmarkViewModel`` snapshot the view renders.
    """
    selected_models = tuple(
        SelectedModelPairViewModel(
            provider_id=provider_id,
            provider_name=state.provider_configs[provider_id].name
            if provider_id in state.provider_configs
            else provider_id,
            model_name=model_name,
        )
        for provider_id, model_name in state.selection.pairs
    )
    return NewBenchmarkViewModel(
        mode=mode,
        visible_sections=tuple(visible_section_set(mode=mode, policy=state.policy)),
        task_file_rows=state.task_file_rows,
        selected_models=selected_models,
        browsed_provider_id=state.browsed_provider_id,
        available_model_names=(),
        selected_model_names_for_browsed_provider=(),
        hide_embedding_models=state.hide_embedding_models,
    )
