"""Concrete Qt-backed ``Clipboard`` (08-E §21b)."""

from PySide6.QtGui import QGuiApplication

from ollama_llm_bench.backend.errors import OsAdapterError


class QtClipboard:
    """Qt ``QClipboard``-backed ``Clipboard`` (08-E §21b).

    Synchronous, main-thread-only. Raises ``OsAdapterError`` only when the
    system clipboard is unavailable or the underlying Qt call fails -- never
    leaks the raw Qt/platform exception.
    """

    def copy_text(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            raise OsAdapterError(message="the system clipboard is unavailable")
        try:
            clipboard.setText(text)
        except Exception as exc:
            # adapter wrapping a native Qt call with no typed exception hierarchy
            # (error-handling-standard.md)
            raise OsAdapterError(message="failed to place text on the system clipboard") from exc
