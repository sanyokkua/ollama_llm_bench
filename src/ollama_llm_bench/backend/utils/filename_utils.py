"""Filename sanitization utilities."""

import re


def sanitize_filename(name: str) -> str:
    """Replace characters that are illegal in Windows and POSIX filenames with underscores.

    Replaces: < > : " / \\ | ? * and ASCII control characters (0x00-0x1F).

    Args:
        name: Raw filename string (no directory component).

    Returns:
        Sanitized string safe for use as a filename on all major platforms.
    """
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return sanitized or "_"
