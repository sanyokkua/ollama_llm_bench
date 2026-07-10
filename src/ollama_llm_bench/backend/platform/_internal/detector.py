"""The concrete, constructor-injectable ``PlatformDetector`` implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``
§§2-3, 5, 7, 13; ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §1.

Hand-rolls the per-OS classification and ``<app-data>`` path table rather than using
``platformdirs`` — ``platformdirs`` selects its per-OS backend at import time from the
real ``sys.platform``/``os.environ``, with no injection hook, which is incompatible
with this module's constructor-injectable testing requirement (every OS branch must
be exercisable without actually running on that OS).
"""

from collections.abc import Mapping
from pathlib import Path

from ollama_llm_bench.backend.platform.models import PlatformKind, PlatformProfile

_APP_DIR_NAME = "OllamaLLMBench"

# Substrings of `sys.platform` (or an equivalent injected identifier) that classify
# the host. Checked in order; the first match wins.
_MACOS_MARKERS = ("darwin",)
_WINDOWS_MARKERS = ("win32", "cygwin")
_LINUX_MARKERS = ("linux",)


def _classify(platform_identifier: str) -> PlatformKind:
    """Classify a platform identifier string into one of the four ``PlatformKind``s."""
    lowered = platform_identifier.lower()
    if any(marker in lowered for marker in _MACOS_MARKERS):
        return PlatformKind.MACOS
    if any(marker in lowered for marker in _WINDOWS_MARKERS):
        return PlatformKind.WINDOWS
    if any(marker in lowered for marker in _LINUX_MARKERS):
        return PlatformKind.LINUX
    return PlatformKind.UNKNOWN


def _resolve_app_data_root(
    kind: PlatformKind, *, home_path: Path, environ: Mapping[str, str]
) -> Path:
    """Resolve ``<app-data>`` per the per-OS table (§3), UNKNOWN falling back to Linux."""
    if kind is PlatformKind.MACOS:
        return home_path / "Library" / "Application Support" / _APP_DIR_NAME
    if kind is PlatformKind.WINDOWS:
        local_app_data = environ.get("LOCALAPPDATA", "")
        if local_app_data:
            return Path(local_app_data) / _APP_DIR_NAME
        # §3 documents no fallback for an unset LOCALAPPDATA (real Windows always sets
        # it); this defensive branch only avoids producing a broken relative path in a
        # pathological environment and is not itself spec-mandated.
        return home_path / "AppData" / "Local" / _APP_DIR_NAME
    # LINUX and the UNKNOWN fallback both resolve via Linux conventions (EC-K7).
    xdg_data_home = environ.get("XDG_DATA_HOME", "")
    if xdg_data_home:
        return Path(xdg_data_home) / _APP_DIR_NAME
    return home_path / ".local" / "share" / _APP_DIR_NAME


def _desktop_path(kind: PlatformKind, *, home_path: Path) -> Path:
    """Resolve the user's Desktop directory; UNKNOWN falls back to Linux conventions."""
    del kind  # The Desktop folder name is identical across all four kinds.
    return home_path / "Desktop"


def _path_separator(kind: PlatformKind) -> str:
    """Return the native path separator; UNKNOWN falls back to Linux's ``/``."""
    return "\\" if kind is PlatformKind.WINDOWS else "/"


def _line_ending(kind: PlatformKind) -> str:
    """Return the native text line ending; UNKNOWN falls back to Linux's ``\\n``."""
    return "\r\n" if kind is PlatformKind.WINDOWS else "\n"


def _case_sensitive_fs(kind: PlatformKind) -> bool:
    """Return the platform's default filesystem case-sensitivity (§2).

    Linux ext4 defaults to case-sensitive; Windows NTFS and macOS's default
    APFS/HFS+ volume are case-insensitive by default. UNKNOWN falls back to the
    Linux (case-sensitive) convention per EC-K7.
    """
    return kind in (PlatformKind.LINUX, PlatformKind.UNKNOWN)


def _supports_native_dark_mode(kind: PlatformKind) -> bool:
    """Whether the host exposes a dark-mode signal (§7).

    macOS, Windows, and Linux desktop environments each expose a colour-scheme
    signal per §7's table. ``UNKNOWN`` cannot be probed for a real signal, so it
    falls back to the Linux convention (``True``) per EC-K7 — the theme module
    still defaults to light whenever no usable signal is actually found at runtime.
    """
    del kind  # Every classified kind, and the Linux-convention UNKNOWN fallback, is True.
    return True


def _file_manager_label(kind: PlatformKind) -> str:
    """Return the platform-correct 'reveal in file manager' label (§5)."""
    if kind is PlatformKind.MACOS:
        return "Reveal in Finder"
    if kind is PlatformKind.WINDOWS:
        return "Show in Explorer"
    # LINUX and UNKNOWN (Linux-convention fallback, EC-K7).
    return "Open in file manager"


class InjectablePlatformDetector:
    """A ``PlatformDetector`` whose OS-probe inputs are fully constructor-injected.

    Never reads real ``sys.platform``/``os.environ``/``Path.home()`` itself — every
    input is supplied by the caller, so tests can exercise every classification
    branch (including an unclassifiable host) without running on each OS.
    """

    def __init__(
        self,
        *,
        platform_identifier: str,
        environ: Mapping[str, str],
        home_path: Path,
        os_version: str = "",
    ) -> None:
        """Construct the detector from fully-injected OS-probe inputs.

        Args:
            platform_identifier: A ``sys.platform``-shaped string (or a faked
                equivalent) classified into a ``PlatformKind``.
            environ: The environment mapping consulted for ``XDG_DATA_HOME`` and
                ``LOCALAPPDATA``.
            home_path: The current user's home directory.
            os_version: A human-readable OS version string for diagnostics.
        """
        self._platform_identifier = platform_identifier
        self._environ = environ
        self._home_path = home_path
        self._os_version = os_version

    def detect(self) -> PlatformProfile:
        """Classify the injected host identity and resolve its platform profile.

        fast-synchronous; callable from any thread. Never raises — an
        unclassifiable identifier resolves to ``PlatformKind.UNKNOWN`` with every
        OS-dependent field falling back to Linux conventions (EC-K7).

        Returns:
            The immutable, fully-resolved ``PlatformProfile`` for the injected host.
        """
        kind = _classify(self._platform_identifier)
        return PlatformProfile(
            kind=kind,
            os_version=self._os_version,
            app_data_root=_resolve_app_data_root(
                kind, home_path=self._home_path, environ=self._environ
            ),
            home_path=self._home_path,
            desktop_path=_desktop_path(kind, home_path=self._home_path),
            path_separator=_path_separator(kind),
            line_ending=_line_ending(kind),
            case_sensitive_fs=_case_sensitive_fs(kind),
            supports_native_dark_mode=_supports_native_dark_mode(kind),
            file_manager_label=_file_manager_label(kind),
        )
