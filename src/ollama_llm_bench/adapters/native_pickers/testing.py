"""An in-memory ``NativePickers`` test double."""

from ollama_llm_bench.adapters.native_pickers.models import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)

__all__: list[str] = ["FakeNativePickers"]


class FakeNativePickers:
    """A ``NativePickers`` fake returning externally settable canned choices."""

    def __init__(self) -> None:
        self._save_result: str | None = None
        self._open_file_result: tuple[str, ...] = ()
        self._open_folder_result: str | None = None

    def save_file(self, options: SavePickerOptions) -> str | None:  # noqa: ARG002  # canned fake: options unused by design
        return self._save_result

    def open_file(self, options: FilePickerOptions) -> tuple[str, ...]:  # noqa: ARG002  # canned fake: options unused by design
        return self._open_file_result

    def open_folder(self, options: FolderPickerOptions) -> str | None:  # noqa: ARG002  # canned fake: options unused by design
        return self._open_folder_result

    def set_save_result(self, path: str | None) -> None:
        self._save_result = path

    def set_open_file_result(self, paths: tuple[str, ...]) -> None:
        self._open_file_result = paths

    def set_open_folder_result(self, path: str | None) -> None:
        self._open_folder_result = path
