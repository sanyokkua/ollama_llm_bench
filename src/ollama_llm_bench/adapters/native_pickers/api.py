"""Public factory for the Qt-backed ``NativePickers`` (08-E §21a)."""

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.native_pickers._internal.qt_native_pickers import QtNativePickers
from ollama_llm_bench.adapters.native_pickers.models import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)
from ollama_llm_bench.adapters.native_pickers.protocols import NativePickers

__all__: list[str] = [
    "FilePickerOptions",
    "FolderPickerOptions",
    "NativePickers",
    "SavePickerOptions",
    "make_native_pickers",
]


@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_native_pickers must be called on the Qt GUI thread -- NativePickers is "
    "synchronous and main-thread-only (08-E §21)",
)
@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist -- called once from compose.py during start-up",
)
def make_native_pickers() -> NativePickers:
    """Construct the Qt-backed NativePickers.

    Returns:
        A NativePickers showing native save/open-file/open-folder dialogs.
    """
    return QtNativePickers()
