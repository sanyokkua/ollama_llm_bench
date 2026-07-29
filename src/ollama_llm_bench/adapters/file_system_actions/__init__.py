"""File-system integration (08-E §21c, 08-K §5): file-manager "reveal" actions,
URL opening, log-file path checks, and atomic binary/text file writes to the exports
folder or arbitrary destination. Reveals a file (selected, where the platform supports
selection) or opens a folder in the host's file manager; opens URLs in the user's
default browser. Writes export files and direct-picker files (PNG, SVG, CSV, Markdown)
atomically via temp-file-then-rename with collision-suffix handling.

Also supplies the Task Editor's on-disk change watch (STORY-112,
``09_Task_Editor/state_machine.md`` §8): ``make_file_change_watcher`` returns a
``FileChangeWatcher`` that polls every open task file and reports a path only when its
*content* actually changed -- a save that rewrites a file with byte-identical content
raises no alarm.
"""

from ollama_llm_bench.adapters.file_system_actions.api import (
    FileChangeWatcher,
    FileSystemActions,
    FileWatchSubscription,
    make_file_change_watcher,
    make_file_system_actions,
)

__all__: list[str] = [
    "FileChangeWatcher",
    "FileSystemActions",
    "FileWatchSubscription",
    "make_file_change_watcher",
    "make_file_system_actions",
]
