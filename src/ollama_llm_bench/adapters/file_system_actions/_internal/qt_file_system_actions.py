"""Concrete per-OS ``FileSystemActions`` (08-E §21c, 08-K §5)."""

from pathlib import Path
import subprocess
import sys

from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.platform import PlatformKind

_MACOS_MARKERS = ("darwin",)
_WINDOWS_MARKERS = ("win32", "cygwin")
_LINUX_MARKERS = ("linux",)


def _classify(platform_identifier: str) -> PlatformKind:
    """Classify a ``sys.platform``-shaped identifier into a ``PlatformKind``.

    Mirrors ``backend.platform``'s own classifier -- kept local so this
    module's per-OS dispatch stays independently constructor-injectable for
    tests, matching why ``backend/platform/_internal/detector.py`` hand-rolls
    its own classification too.
    """
    lowered = platform_identifier.lower()
    if any(marker in lowered for marker in _MACOS_MARKERS):
        return PlatformKind.MACOS
    if any(marker in lowered for marker in _WINDOWS_MARKERS):
        return PlatformKind.WINDOWS
    if any(marker in lowered for marker in _LINUX_MARKERS):
        return PlatformKind.LINUX
    return PlatformKind.UNKNOWN


def _reveal_command(kind: PlatformKind, path: str) -> list[str]:
    """Build the per-OS reveal command (08-K §5). UNKNOWN falls back to Linux."""
    if kind is PlatformKind.MACOS:
        return ["open", "-R", path]
    if kind is PlatformKind.WINDOWS:
        return ["explorer", f"/select,{path}"]
    # LINUX and the UNKNOWN fallback both use the desktop-portal opener. Linux has no
    # universal reveal-and-select mechanism, so a file target is opened via its
    # containing folder instead (08-K §5: "where the platform supports selection" --
    # macOS/Windows do, Linux does not); a folder target is opened directly.
    target = path if Path(path).is_dir() else str(Path(path).parent)
    return ["xdg-open", target]


class QtFileSystemActions:
    """Per-OS ``FileSystemActions`` (08-E §21c, 08-K §5).

    Synchronous, main-thread-only. The reveal command is dispatched from an
    injected platform identifier so every OS branch is exercisable from a
    single test run without actually running on that OS. Raises
    ``OsAdapterError`` when ``path`` does not exist or the file-manager
    process could not be launched -- never leaks the raw ``OSError``.
    """

    def __init__(self, *, platform_identifier: str | None = None) -> None:
        """Construct the adapter bound to an injected platform identifier.

        Args:
            platform_identifier: A ``sys.platform``-shaped string classified
                into a ``PlatformKind`` to select the reveal command. If not
                provided, defaults to the host platform via ``sys.platform``.
        """
        if platform_identifier is None:
            platform_identifier = sys.platform
        self._kind = _classify(platform_identifier)

    def open_in_file_manager(self, path: str) -> None:
        if not Path(path).exists():
            raise OsAdapterError(message=f"path does not exist: {path}")
        command = _reveal_command(self._kind, path)
        try:
            # check=False: explorer.exe (Windows) is known to return non-zero even
            # on a successful reveal, so only a launch failure (executable missing)
            # is treated as an integration failure, never the return code.
            subprocess.run(command, check=False)  # noqa: S603  # fixed argv;
            # only a validated existing path is interpolated, never a shell string
        except OSError as exc:
            raise OsAdapterError(message="the OS file manager could not be launched") from exc
