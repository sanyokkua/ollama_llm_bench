"""File-manager "reveal" integration (08-E §21c, 08-K §5). Reveals a file
(selected, where the platform supports selection) or opens a folder in the
host's file manager.
"""

from ollama_llm_bench.adapters.file_system_actions.api import (
    FileSystemActions,
    make_file_system_actions,
)

__all__: list[str] = ["FileSystemActions", "make_file_system_actions"]
