"""Frozen ViewModel structs for ``ui/new_benchmark/`` (STORY-054, STORY-055).

Source of truth: ``docs/v3_specification/02_New_Benchmark_Widget/description.md``
§3, §4.4, §4.6, §4.7, §6, §12. Recomputed by ``_internal/view_model_select.py`` on
every subscribed event/user action and applied to the view; never persisted, never
crosses a service boundary.
"""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import RunMode, SettingKey
from ollama_llm_bench.backend.mode_visibility import ConfigSection

__all__: list[str] = [
    "AdvancedOptionsViewModel",
    "EmbeddingStatusViewModel",
    "NewBenchmarkViewModel",
    "RunValidationSeverity",
    "SelectedModelPairViewModel",
    "TaskFileRowViewModel",
    "ValidationEntry",
]


class RunValidationSeverity(StrEnum):
    """The two Run Validator severities (`description.md` §6): hard errors block
    Start; soft warnings are surfaced but never block it."""

    HARD_ERROR = "hard_error"
    SOFT_WARNING = "soft_warning"


class ValidationEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Run Validator finding (`description.md` §6 table).

    Attributes:
        severity: Whether this entry blocks Start (``HARD_ERROR``) or is merely
            surfaced for review (``SOFT_WARNING``).
        message: The verbatim, user-facing explanation from the §6 table.
    """

    severity: RunValidationSeverity
    message: str


class AdvancedOptionsViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row per Advanced Options control (STORY-055-AC-3; `description.md` §4.7).

    Attributes:
        override_enabled: The activation-checkbox state; ``False`` means the run
            uses the global defaults and no per-run override is carried.
        values: Every ``PER_RUN_OVERRIDABLE`` key's current control value (registry
            storage form), except ``feature.judge_run_analysis_enabled``.
        dirty_keys: Exactly the keys the user changed from their seeded value --
            only these are carried on ``RunStartRequest.setting_overrides`` (DD-47).
        grading_visible: Whether the Evaluation controls sub-group is shown --
            ``True`` only in ``GRADED``.
    """

    override_enabled: bool
    values: dict[SettingKey, str]
    dirty_keys: frozenset[SettingKey]
    grading_visible: bool


class EmbeddingStatusViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Judge section's embedding status row (`description.md` §4.5), ``GRADED`` only.

    Attributes:
        ready: Whether the embedding selection is resolved and reachable.
        provider_display: The resolved embedding provider's display name, or
            ``None`` when unresolved.
        embedding_model: The resolved embedding model name, or ``None`` when
            unresolved.
    """

    ready: bool
    provider_display: str | None
    embedding_model: str | None


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
        judge_analysis_enabled: The "Generate run analysis for this run" toggle
            state (STORY-055-AC-1).
        judge_provider_id: The Judge section's currently selected provider, or
            ``None`` before any provider has been chosen.
        embedding_status: The Judge section's embedding status row content;
            ``None`` outside ``GRADED``.
        advanced_options: The Advanced Options section's current state.
        validation_entries: Every current Run Validator finding.
        start_enabled: Whether the Start Benchmark button is enabled.
        start_tooltip: The Start Benchmark button's tooltip (empty when enabled
            with no findings at all).
        synthetic_estimate_line: The live estimated-task-count line
            (`synthetic.md` §4); ``None`` outside ``SYNTHETIC``.
    """

    mode: RunMode
    visible_sections: tuple[ConfigSection, ...]
    task_file_rows: tuple[TaskFileRowViewModel, ...]
    selected_models: tuple[SelectedModelPairViewModel, ...]
    browsed_provider_id: str | None
    available_model_names: tuple[str, ...]
    selected_model_names_for_browsed_provider: tuple[str, ...]
    hide_embedding_models: bool
    judge_analysis_enabled: bool
    judge_provider_id: str | None
    embedding_status: EmbeddingStatusViewModel | None
    advanced_options: AdvancedOptionsViewModel
    validation_entries: tuple[ValidationEntry, ...]
    start_enabled: bool
    start_tooltip: str
    synthetic_estimate_line: str | None
