"""Pure buffers + validation -> ``TaskEditorViewModel`` selection functions
(STORY-068-AC-1, AC-2; STORY-069-AC-1, AC-2, AC-5). No Qt imports -- directly
unit-testable (``implementation_structure.md`` §9)."""

from collections.abc import Sequence
from pathlib import Path

from ollama_llm_bench.backend.task_files import ValidationSeverity
from ollama_llm_bench.ui.task_editor._internal.buffer import (
    TaskBuffer,
    is_saveable,
    task_at,
    task_count,
    task_ids,
)
from ollama_llm_bench.ui.task_editor._internal.field_rows import select_field_rows
from ollama_llm_bench.ui.task_editor.models import (
    FieldRowViewModel,
    FileRowViewModel,
    TaskEditorViewModel,
    TaskRowViewModel,
    ToolbarViewModel,
    ValidationState,
)

__all__: list[str] = ["select_task_editor_view_model"]

_SEVERITY_TO_STATE: dict[ValidationSeverity, ValidationState] = {
    ValidationSeverity.CLEAN: ValidationState.CLEAN,
    ValidationSeverity.INFO: ValidationState.INFO,
    ValidationSeverity.WARNING: ValidationState.WARNING,
    ValidationSeverity.ERROR: ValidationState.ERROR,
}


def select_task_editor_view_model(
    *,
    buffers: Sequence[TaskBuffer],
    active_buffer_index: int | None,
    active_task_index: int | None,
    preview_shown: bool,
    preview_text: str,
) -> TaskEditorViewModel:
    """Derive the workspace's full render state from its open buffers (§4).

    Args:
        buffers: Every currently open buffer, in Files-pane display order.
        active_buffer_index: The active file's index into ``buffers``, or ``None``
            in the Empty state.
        active_task_index: The active file's selected task index, or ``None``.
        preview_shown: The YAML-preview toggle state (§3.6).
        preview_text: The already-materialized preview text (I/O happens in the
            controller, via ``_internal/buffer.py``'s scratch seam -- this
            function stays pure and touches no disk).

    Returns:
        The frozen view-model the panes render from.
    """
    file_rows = tuple(
        _select_file_row(buffer, is_active=index == active_buffer_index)
        for index, buffer in enumerate(buffers)
    )
    task_rows: tuple[TaskRowViewModel, ...] = ()
    field_rows: tuple[FieldRowViewModel, ...] = ()
    if active_buffer_index is not None and 0 <= active_buffer_index < len(buffers):
        active_buffer = buffers[active_buffer_index]
        task_rows = _select_task_rows(active_buffer, active_task_index)
        field_rows = _select_field_rows_for_active_task(active_buffer, active_task_index)
    return TaskEditorViewModel(
        files=file_rows,
        active_file_index=active_buffer_index,
        tasks=task_rows,
        active_task_index=active_task_index,
        field_rows=field_rows,
        toolbar_state=_select_toolbar_state(buffers, active_buffer_index),
        preview_shown=preview_shown,
        preview_text=preview_text,
        is_empty=len(buffers) == 0,
    )


def _select_field_rows_for_active_task(
    buffer: TaskBuffer, active_task_index: int | None
) -> tuple[FieldRowViewModel, ...]:
    if active_task_index is None or not (0 <= active_task_index < task_count(buffer)):
        return ()
    task = task_at(buffer, active_task_index)
    task_validation = None
    if buffer.validation is not None:
        task_validation = next(
            (
                result
                for result in buffer.validation.task_results
                if result.task_index == active_task_index
            ),
            None,
        )
    return select_field_rows(task=task, task_validation=task_validation)


def _select_file_row(buffer: TaskBuffer, *, is_active: bool) -> FileRowViewModel:
    severity = (
        buffer.validation.severity if buffer.validation is not None else ValidationSeverity.CLEAN
    )
    return FileRowViewModel(
        path=buffer.source_path,
        display_name=Path(buffer.source_path).name,
        is_dirty=buffer.is_dirty,
        is_active=is_active,
        validation_state=_SEVERITY_TO_STATE[severity],
        is_external_changed=buffer.is_external_changed,
        is_in_use_by_run=buffer.is_in_use_by_run,
    )


def _select_task_rows(
    buffer: TaskBuffer, active_task_index: int | None
) -> tuple[TaskRowViewModel, ...]:
    task_results = buffer.validation.task_results if buffer.validation is not None else ()
    severity_by_index = {result.task_index: result.severity for result in task_results}
    return tuple(
        TaskRowViewModel(
            task_id=task_id,
            is_selected=index == active_task_index,
            validation_state=_SEVERITY_TO_STATE[
                severity_by_index.get(index, ValidationSeverity.CLEAN)
            ],
        )
        for index, task_id in enumerate(task_ids(buffer))
    )


def _select_toolbar_state(
    buffers: Sequence[TaskBuffer], active_buffer_index: int | None
) -> ToolbarViewModel:
    dirty_count = sum(1 for buffer in buffers if buffer.is_dirty)
    dirty_saveable_count = sum(1 for buffer in buffers if buffer.is_dirty and is_saveable(buffer))
    active_buffer = (
        buffers[active_buffer_index]
        if active_buffer_index is not None and 0 <= active_buffer_index < len(buffers)
        else None
    )
    active_saveable = (
        active_buffer is not None and active_buffer.is_dirty and is_saveable(active_buffer)
    )
    # Reload is enabled whenever a file is active (description.md §3.2) -- a dirty
    # file routes through the reload-confirmation dialog (EC-TE-09) rather than
    # being disabled outright, now that STORY-069 wires that dialog.
    reload_enabled = active_buffer is not None
    aggregate_task_count = sum(len(task_ids(buffer)) for buffer in buffers)
    aggregate_warning_count = sum(
        1
        for buffer in buffers
        if buffer.validation is not None
        and buffer.validation.severity is ValidationSeverity.WARNING
    )
    aggregate_error_count = sum(
        1
        for buffer in buffers
        if buffer.validation is not None and buffer.validation.severity is ValidationSeverity.ERROR
    )
    if aggregate_error_count:
        aggregate_state = ValidationState.ERROR
    elif aggregate_warning_count:
        aggregate_state = ValidationState.WARNING
    else:
        aggregate_state = ValidationState.CLEAN
    return ToolbarViewModel(
        save_enabled=active_saveable,
        save_all_enabled=dirty_saveable_count > 0,
        save_all_count=dirty_count,
        reload_enabled=reload_enabled,
        aggregate_state=aggregate_state,
        aggregate_task_count=aggregate_task_count,
        aggregate_warning_count=aggregate_warning_count,
        aggregate_error_count=aggregate_error_count,
    )
