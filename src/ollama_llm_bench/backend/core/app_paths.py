"""Platform-specific user data directory resolution for OllamaLLMBench."""

import os
import sys
from pathlib import Path

_APP_NAME: str = "OllamaLLMBench"


def _resolve_data_dir(platform: str) -> Path:
    """Return the platform-specific user data directory without creating it.

    Args:
        platform: A ``sys.platform``-style string (e.g. ``"darwin"``, ``"win32"``,
            ``"linux"``). Stored in a parameter so type checkers cannot collapse the
            non-current branches as unreachable based on the host platform.

    Returns:
        Platform-specific path:
        - macOS:   ~/Library/Application Support/OllamaLLMBench/
        - Windows: %APPDATA%\\OllamaLLMBench\\
        - Linux/other: $XDG_DATA_HOME/OllamaLLMBench/ (default: ~/.local/share/OllamaLLMBench/)
    """
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME
    if platform == "win32":
        app_data = os.environ.get("APPDATA") or str(Path.home())
        return Path(app_data) / _APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / _APP_NAME


def get_user_data_dir() -> Path:
    """Return the OS-specific user data directory for this application.

    Does not create the directory.

    Returns:
        Platform-specific path. See ``_resolve_data_dir`` for the per-OS layout.
    """
    return _resolve_data_dir(sys.platform)


def ensure_user_data_dir() -> Path:
    """Create and return the user data directory.

    Returns:
        Created platform-specific user data directory path.
    """
    data_dir = get_user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir() -> Path:
    """Return the OS-specific log directory (does not create it).

    Returns:
        <user_data_dir>/logs/
    """
    return get_user_data_dir() / "logs"


def ensure_log_dir() -> Path:
    """Create and return the log directory.

    Returns:
        Created log directory path.
    """
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
