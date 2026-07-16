"""Concrete Qt-backed ``NativePickers`` (08-E §21a)."""

from PySide6.QtWidgets import QFileDialog

from ollama_llm_bench.adapters.native_pickers.protocols import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)
from ollama_llm_bench.backend.errors import OsAdapterError

_FILTER_SEPARATOR = ";;"


def _join_filters(filters: tuple[str, ...]) -> str:
    """Join display filters into Qt's ``;;``-separated filter string."""
    return _FILTER_SEPARATOR.join(filters)


class QtNativePickers:
    """Qt ``QFileDialog``-backed ``NativePickers`` (08-E §21a).

    Synchronous, main-thread-only. Qt selects a native or toolkit-fallback
    dialog per OS internally (08-K §6); cancellation is Qt's own empty-string/
    empty-list sentinel, never an exception. Raises ``OsAdapterError`` only on
    a genuine dialog-subsystem failure -- never leaks the raw Qt exception.
    """

    def save_file(self, options: SavePickerOptions) -> str | None:
        try:
            path, _selected_filter = QFileDialog.getSaveFileName(
                None, options.title, options.start_dir or "", _join_filters(options.filters)
            )
        except Exception as exc:
            raise OsAdapterError(message="the native save dialog failed to launch") from exc
        return path or None

    def open_file(self, options: FilePickerOptions) -> tuple[str, ...]:
        try:
            if options.allow_multiple:
                paths, _selected_filter = QFileDialog.getOpenFileNames(
                    None, options.title, options.start_dir or "", _join_filters(options.filters)
                )
            else:
                path, _selected_filter = QFileDialog.getOpenFileName(
                    None, options.title, options.start_dir or "", _join_filters(options.filters)
                )
                paths = [path] if path else []
        except Exception as exc:
            raise OsAdapterError(message="the native open dialog failed to launch") from exc
        return tuple(p for p in paths if p)

    def open_folder(self, options: FolderPickerOptions) -> str | None:
        try:
            folder = QFileDialog.getExistingDirectory(None, options.title, options.start_dir or "")
        except Exception as exc:
            raise OsAdapterError(message="the native folder dialog failed to launch") from exc
        return folder or None
