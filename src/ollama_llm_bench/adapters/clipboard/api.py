"""Public factory for the Qt-backed ``Clipboard`` (08-E §21b)."""

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.clipboard._internal.qt_clipboard import QtClipboard
from ollama_llm_bench.adapters.clipboard.protocols import Clipboard

__all__: list[str] = ["Clipboard", "make_clipboard"]


@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist -- called once from compose.py during start-up",
)
@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_clipboard must be called on the Qt GUI thread -- Clipboard is synchronous and "
    "main-thread-only (08-E §21)",
)
def make_clipboard() -> Clipboard:
    """Construct the Qt-backed Clipboard.

    Returns:
        A Clipboard writing to the system clipboard via Qt.
    """
    return QtClipboard()
