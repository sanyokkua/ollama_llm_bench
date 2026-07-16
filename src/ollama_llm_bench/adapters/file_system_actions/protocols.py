"""``FileSystemActions`` Protocol (08-E §21c)."""

from typing import Protocol

__all__: list[str] = ["FileSystemActions"]


class FileSystemActions(Protocol):
    """File-manager integration."""

    def open_in_file_manager(self, path: str) -> None:
        """Reveal a file or folder in the OS file manager.

        fast-synchronous; must be called on the Qt main thread. When ``path``
        names a file, the file manager opens with that file selected where the
        platform supports selection (08-K §5); when it names a folder, the
        folder itself is opened.

        Args:
            path: The absolute filesystem path to reveal.

        Raises:
            OsAdapterError: ``path`` does not exist, or the file manager could
                not be launched.
        """
        ...
