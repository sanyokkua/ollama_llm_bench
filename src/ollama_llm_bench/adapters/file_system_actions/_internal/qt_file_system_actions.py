"""Concrete per-OS ``FileSystemActions`` (08-E §21c, 08-K §5)."""

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.infra import run_log_path
from ollama_llm_bench.backend.platform import PlatformKind, make_platform_detector

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


class _AppDataRootView:
    """Adapts a resolved ``PlatformProfile`` to ``backend.infra``'s narrow,
    structurally-typed ``PlatformDetector`` Protocol (``app_data_root`` only).

    ``backend.platform.PlatformDetector.detect()`` returns a full
    ``PlatformProfile``; ``backend.infra.run_log_path`` wants an object
    exposing ``app_data_root`` directly. This tiny private view bridges the
    two structurally -- it never crosses this module's own boundary.
    """

    def __init__(self, app_data_root: Path) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        return self._app_data_root


def _first_free_path(directory: Path, filename: str) -> Path:
    """Apply the numeric-suffix collision rule (05_EXPORT_FORMATS.md §2.2)."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _atomic_write(destination: Path, content: str) -> None:
    """Write ``content`` to a temp file beside ``destination``, then rename atomically.

    Leaves no partial file on failure (EC-RES-5).
    """
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=".export_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, destination)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise OsAdapterError(message=f"failed to write export file: {destination}") from exc


def _atomic_write_bytes(destination: Path, content: bytes) -> None:
    """Write raw ``content`` to a temp file beside ``destination``, then rename atomically.

    The binary counterpart of ``_atomic_write`` (STORY-064) -- identical
    temp-file-then-rename structure, only the open mode and payload type differ.
    Leaves no partial file on failure (EC-RES-5).
    """
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=".export_tmp_")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(tmp_name, destination)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise OsAdapterError(message=f"failed to write export file: {destination}") from exc


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

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return self._run_log_path(run_id=run_id, started_at=started_at).exists()

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return str(self._run_log_path(run_id=run_id, started_at=started_at))

    def _run_log_path(self, *, run_id: int, started_at: str) -> Path:
        unix_ts = int(datetime.fromisoformat(started_at).timestamp())
        profile = make_platform_detector().detect()
        app_data_root_view = _AppDataRootView(profile.app_data_root)
        return run_log_path(app_data_root_view, run_id=str(run_id), unix_ts=unix_ts)

    def write_export_file(self, *, filename: str, content: str) -> str:
        exports_dir = Path(self.exports_folder_path())
        final_path = _first_free_path(exports_dir, filename)
        _atomic_write(final_path, content)
        return str(final_path)

    def write_text_file(self, *, path: str, content: str) -> None:
        _atomic_write(Path(path), content)

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        exports_dir = Path(self.exports_folder_path())
        final_path = _first_free_path(exports_dir, filename)
        _atomic_write_bytes(final_path, content)
        return str(final_path)

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        _atomic_write_bytes(Path(path), content)

    def exports_folder_path(self) -> str:
        profile = make_platform_detector().detect()
        exports_dir = profile.app_data_root / "exports"
        try:
            exports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OsAdapterError(
                message=f"could not create the exports folder: {exports_dir}"
            ) from exc
        return str(exports_dir)
