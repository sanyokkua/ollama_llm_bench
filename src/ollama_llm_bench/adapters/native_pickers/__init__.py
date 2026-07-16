"""Native save / open-file / open-folder dialogs (08-E §21a). Cancellation is
``None``/empty, never an exception; only a dialog-subsystem failure raises
OsAdapterError.
"""

from ollama_llm_bench.adapters.native_pickers.api import (
    FilePickerOptions,
    FolderPickerOptions,
    NativePickers,
    SavePickerOptions,
    make_native_pickers,
)

__all__: list[str] = [
    "FilePickerOptions",
    "FolderPickerOptions",
    "NativePickers",
    "SavePickerOptions",
    "make_native_pickers",
]
