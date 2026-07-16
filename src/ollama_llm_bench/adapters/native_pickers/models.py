"""``NativePickers`` contract-local options structs (08-E §21a)."""

import msgspec

__all__: list[str] = [
    "FilePickerOptions",
    "FolderPickerOptions",
    "SavePickerOptions",
]


class SavePickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Options for a native save-file dialog (08-E §21a)."""

    title: str
    suggested_name: str
    start_dir: str | None = None
    filters: tuple[str, ...] = ()


class FilePickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Options for a native open-file dialog (08-E §21a)."""

    title: str
    start_dir: str | None = None
    filters: tuple[str, ...] = ()
    allow_multiple: bool = False


class FolderPickerOptions(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Options for a native open-folder dialog (08-E §21a)."""

    title: str
    start_dir: str | None = None
