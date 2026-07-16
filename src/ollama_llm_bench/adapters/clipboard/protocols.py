"""``Clipboard`` Protocol (08-E §21b) -- the system clipboard write surface."""

from typing import Protocol

__all__: list[str] = ["Clipboard"]


class Clipboard(Protocol):
    """System clipboard write surface."""

    def copy_text(self, text: str) -> None:
        """Place text on the system clipboard.

        fast-synchronous; must be called on the Qt main thread.

        Args:
            text: The exact text to place on the clipboard, unredacted (08-E §22 --
                clipboard content is user-owned data, never redacted).

        Raises:
            OsAdapterError: The system clipboard is unavailable.
        """
        ...
