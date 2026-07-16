"""``NativePickers`` Protocol (08-E §21a)."""

from typing import Protocol

from ollama_llm_bench.adapters.native_pickers.models import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)

__all__: list[str] = ["NativePickers"]


class NativePickers(Protocol):
    """Native save / open-file / open-folder dialogs."""

    def save_file(self, options: SavePickerOptions) -> str | None:
        """Show a native save dialog.

        fast-synchronous; must be called on the Qt main thread.

        Args:
            options: The dialog's title, suggested name, start directory, and filters.

        Returns:
            The chosen path, or ``None`` when the user cancels.

        Raises:
            OsAdapterError: The dialog subsystem failed to launch.
        """
        ...

    def open_file(self, options: FilePickerOptions) -> tuple[str, ...]:
        """Show a native open-file dialog.

        fast-synchronous; must be called on the Qt main thread.

        Args:
            options: The dialog's title, start directory, filters, and whether
                multiple files may be selected.

        Returns:
            The chosen paths, empty when the user cancels.

        Raises:
            OsAdapterError: The dialog subsystem failed to launch.
        """
        ...

    def open_folder(self, options: FolderPickerOptions) -> str | None:
        """Show a native open-folder dialog.

        fast-synchronous; must be called on the Qt main thread.

        Args:
            options: The dialog's title and start directory.

        Returns:
            The chosen folder, or ``None`` when the user cancels.

        Raises:
            OsAdapterError: The dialog subsystem failed to launch.
        """
        ...
