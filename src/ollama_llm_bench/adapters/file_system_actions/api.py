"""Public factory for the per-OS ``FileSystemActions`` (08-E §21c)."""

import sys

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.file_system_actions._internal.qt_file_system_actions import (
    QtFileSystemActions,
)
from ollama_llm_bench.adapters.file_system_actions.protocols import FileSystemActions

__all__: list[str] = ["FileSystemActions", "make_file_system_actions"]


@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_file_system_actions must be called on the Qt GUI thread -- FileSystemActions "
    "is synchronous and main-thread-only (08-E §21)",
)
@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist -- called once from compose.py during start-up",
)
def make_file_system_actions() -> FileSystemActions:
    """Construct the FileSystemActions bound to the real host platform.

    Returns:
        A FileSystemActions revealing paths in this host's real file manager.
    """
    return QtFileSystemActions(platform_identifier=sys.platform)
