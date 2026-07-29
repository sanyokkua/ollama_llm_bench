"""Public factories for the per-OS ``FileSystemActions`` (08-E §21c) and the Task
Editor's on-disk ``FileChangeWatcher`` (``09_Task_Editor/state_machine.md`` §8)."""

from typing import Final

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.file_system_actions._internal.polling_file_change_watcher import (
    PollingFileChangeWatcher,
)
from ollama_llm_bench.adapters.file_system_actions._internal.qt_file_system_actions import (
    QtFileSystemActions,
)
from ollama_llm_bench.adapters.file_system_actions.protocols import (
    FileChangeWatcher,
    FileSystemActions,
    FileWatchSubscription,
)

__all__: list[str] = [
    "FileChangeWatcher",
    "FileSystemActions",
    "FileWatchSubscription",
    "make_file_change_watcher",
    "make_file_system_actions",
]

_DEFAULT_POLL_INTERVAL_MS: Final[int] = 1000


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
    return QtFileSystemActions()


@icontract.require(
    lambda poll_interval_ms: poll_interval_ms > 0,
    "poll_interval_ms must be positive -- it is a QTimer interval chosen in code, "
    "never a user-entered value",
)
@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_file_change_watcher must be called on the Qt GUI thread -- the watcher owns a "
    "QTimer and calls back on the thread that owns it (09_Task_Editor/state_machine.md §8)",
)
@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist -- called once from compose.py during start-up",
)
def make_file_change_watcher(
    *, poll_interval_ms: int = _DEFAULT_POLL_INTERVAL_MS
) -> FileChangeWatcher:
    """Construct the polling watcher backing the Task Editor's on-disk change watch.

    Args:
        poll_interval_ms: How often every watched path is checked, in
            milliseconds. Trades notification latency against idle cost; the
            default suits the interactive editor, tests drive it faster.

    Returns:
        A FileChangeWatcher reporting a watched path only when its on-disk
        content actually differs from what was last read.
    """
    return PollingFileChangeWatcher(poll_interval_ms=poll_interval_ms)
