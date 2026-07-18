"""Frozen ViewModel structs for ``ui/new_benchmark/`` (STORY-054).

Source of truth: ``docs/v3_specification/02_New_Benchmark_Widget/description.md``
§3, §4.6, §12. Recomputed by ``_internal/view_model_select.py`` on every subscribed
event/user action and applied to the view; never persisted, never crosses a service
boundary.
"""

import msgspec

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection

__all__: list[str] = [
    "NewBenchmarkViewModel",
    "SelectedModelPairViewModel",
    "TaskFileRowViewModel",
]


class TaskFileRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row in the Task Files list (STORY-054-AC-4, AC-6).

    Attributes:
        source_path: The absolute path of the loaded file.
        file_name: The display file name (``source_path``'s basename).
        task_count: The surviving parsed-task count for this file (EC-TASK-3:
            malformed individual tasks are already excluded by the loader).
    """

    source_path: str
    file_name: str
    task_count: int


class SelectedModelPairViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row in the Selected Models Summary (STORY-054-AC-3).

    Attributes:
        provider_id: The internal UUID4 selection key.
        provider_name: The user-facing provider name to display (never the id).
        model_name: The selected model name.
    """

    provider_id: str
    provider_name: str
    model_name: str


class NewBenchmarkViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The New Benchmark widget's full displayed state, in one frozen snapshot.

    Attributes:
        mode: The currently selected run mode.
        visible_sections: The section set the Mode Visibility Policy returns for
            ``mode`` (STORY-054-AC-2); the view shows/hides purely from this set.
        task_file_rows: The Task Files section's current rows, in add order.
        selected_models: Every ``(provider, model)`` pair currently selected,
            across all browsed providers (STORY-054-AC-3).
        browsed_provider_id: The Test Models section's currently browsed
            provider, or ``None`` before any provider has been chosen.
        available_model_names: The browsed provider's model names, already
            filtered by ``hide_embedding_models`` when that flag is set.
        selected_model_names_for_browsed_provider: The subset of
            ``available_model_names`` currently selected, for toggle-list
            checked-state rendering.
        hide_embedding_models: The current ``embedding.hide_from_test_models``
            checkbox state.
    """

    mode: RunMode
    visible_sections: tuple[ConfigSection, ...]
    task_file_rows: tuple[TaskFileRowViewModel, ...]
    selected_models: tuple[SelectedModelPairViewModel, ...]
    browsed_provider_id: str | None
    available_model_names: tuple[str, ...]
    selected_model_names_for_browsed_provider: tuple[str, ...]
    hide_embedding_models: bool
