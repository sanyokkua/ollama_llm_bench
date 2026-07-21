"""File-system integration (08-E §21c, 08-K §5): file-manager "reveal" actions,
log-file path checks, and atomic binary/text file writes to the exports folder
or arbitrary destination. Reveals a file (selected, where the platform supports
selection) or opens a folder in the host's file manager. Writes export files
and direct-picker files (PNG, SVG, CSV, Markdown) atomically via temp-file-then-rename
with collision-suffix handling.
"""

from ollama_llm_bench.adapters.file_system_actions.api import (
    FileSystemActions,
    make_file_system_actions,
)

__all__: list[str] = ["FileSystemActions", "make_file_system_actions"]
